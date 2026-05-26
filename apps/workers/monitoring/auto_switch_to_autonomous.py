"""auto_switch_to_autonomous.py -- decide automaticamente cuando activar
modo autonomo (hitl_mode=false) basado en 7 condiciones del Bloque 6.

Fase 5 sesion 2026-05-26. Decision PM: el sistema puede flipar hitl_mode
sin confirmacion manual cuando 7/7 condiciones esten verdes, CON
safeguards (ver Leccion 50):
  1. Email previo 24h.
  2. Toggle auto_switch_enabled en /settings.
  3. Cap envio mantenido 20/dia sin escalar.
  4. Boton rollback "Volver a HITL ahora" en /settings.

Las 7 condiciones (espejo Bloque 6 prompt /goal v4, con ajuste PM L50
threshold pool 100->50):

| # | Condicion | Evidencia BD                                                 |
|---|-----------|---------------------------------------------------------------|
| 1 | Bloques -1 a 5 completados              | Proxy: migration 14, 15, 16 aplicadas. |
| 2 | Aprobaciones acumuladas >= 50           | count messages approved+sent >= 50. |
| 3 | B7 operativo >=1h + >=1 reply real      | mailbox refresh_token present + replies>0. |
| 4 | Cero bounces/spam_complaints 7d         | count events type in ('bounce','spam_complaint') 7d = 0. |
| 5 | Pool virgenes elegibles >= 50 (L50)     | count vírgenes T1+T2+T3+T4 elegibles. |
| 6 | Replenish no reescribe tocados          | Proxy: 0 contacts con >=3 mensajes en 14d. |
| 7 | Lemwarm pausado                         | No verificable desde Code -- asumir true segun L38. |

Logica:
- Cada 6h via demin-auto-switch.timer.
- Lee auto_switch_enabled. Si false: solo evalua y loguea, no programa.
- Evalua 7 condiciones.
- Si 7/7 verdes Y NO hay scheduled_autonomous_switch_at:
    -> set scheduled_autonomous_switch_at = now() + 24h.
    -> email '[DEMIN] Switch a autonomo programado para <fecha>'.
- Si scheduled_autonomous_switch_at NOT NULL Y alguna condicion roja:
    -> NULL el campo + email '[DEMIN] Switch cancelado: condicion <X> roto'.
- Si scheduled_autonomous_switch_at NOT NULL Y now() >= scheduled Y 7/7 verdes:
    -> UPDATE hitl_mode=false + NULL scheduled + email '[DEMIN] AUTONOMO ACTIVADO'.

CLI:
    cd apps/workers
    PYTHONPATH=. python -m monitoring.auto_switch_to_autonomous --env prod
    PYTHONPATH=. python -m monitoring.auto_switch_to_autonomous --env prod --dry-run

Exit codes:
- 0: OK (cualquier action o sin action).
- 2: error config / BD.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import text

from shared.db import get_session
from shared.notifications import send_operational_email

EnvName = Literal["dev", "prod"]

logger = logging.getLogger("demin.auto_switch")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

# Decision PM L50: threshold pool ajustado de 100 a 50.
POOL_VIRGENES_THRESHOLD = 50
# Condicion 2: aprobaciones acumuladas minimas.
APROBACIONES_THRESHOLD = 50
# Ventana 24h del schedule (PM tiene tiempo de cancelar desde /settings).
SCHEDULE_LEAD_HOURS = 24
# Migrations que deben estar aplicadas como proxy de "Bloques -1 a 5 OK".
REQUIRED_MIGRATIONS = (
    "20260525190000_14_message_revisions.sql",
    "20260526200000_15_messages_reply_tracking.sql",
    "20260526230000_16_auto_switch_autonomous.sql",
)
# Destinatarios para safeguards.
NOTIFICATION_RECIPIENTS = (
    "albertobueno10@gmail.com",
    "gonzalo.perez@demingroupmadrid.com",
)


@dataclass(slots=True)
class ConditionResult:
    name: str
    ok: bool
    detail: str  # texto breve con el numero clave.


@dataclass(slots=True)
class Evaluation:
    conditions: list[ConditionResult]

    @property
    def all_green(self) -> bool:
        return all(c.ok for c in self.conditions)

    @property
    def n_green(self) -> int:
        return sum(1 for c in self.conditions if c.ok)


# ─── evaluadores de las 7 condiciones ─────────────────────────────────────


def _eval_cond_1_migrations(env: EnvName) -> ConditionResult:
    """Proxy Bloques -1 a 5 completados: migrations 14+15+16 aplicadas."""
    with get_session(env) as s:
        applied = {
            r[0] for r in s.execute(
                text("select filename from _migrations")
            ).fetchall()
        }
    missing = [m for m in REQUIRED_MIGRATIONS if m not in applied]
    return ConditionResult(
        name="1_migrations",
        ok=not missing,
        detail=f"required={len(REQUIRED_MIGRATIONS)} applied={len(REQUIRED_MIGRATIONS)-len(missing)} missing={missing}",
    )


def _eval_cond_2_aprobaciones(env: EnvName) -> ConditionResult:
    """Aprobaciones acumuladas (approved + sent) >= threshold."""
    with get_session(env) as s:
        n = int(s.execute(
            text("select count(*) from messages where status in ('approved','sent')")
        ).scalar() or 0)
    return ConditionResult(
        name="2_aprobaciones",
        ok=n >= APROBACIONES_THRESHOLD,
        detail=f"acumuladas={n} threshold={APROBACIONES_THRESHOLD}",
    )


def _eval_cond_3_b7_replies(env: EnvName) -> ConditionResult:
    """B7 operativo: mailbox tiene refresh_token presente. Y >=1 reply real."""
    with get_session(env) as s:
        # Tiene mailbox activo con token.
        mb = s.execute(
            text(
                "select count(*) from mailboxes "
                "where status='active' and oauth_refresh_token_encrypted is not null"
            )
        ).scalar()
        replies_count = int(s.execute(
            text("select count(*) from replies")
        ).scalar() or 0)
    token_ok = int(mb or 0) > 0
    return ConditionResult(
        name="3_b7_y_replies",
        ok=token_ok and replies_count >= 1,
        detail=f"mailbox_token={token_ok} replies_count={replies_count}",
    )


def _eval_cond_4_sin_bounces(env: EnvName) -> ConditionResult:
    """Cero events bounce/spam_complaint en 7 dias rolling."""
    with get_session(env) as s:
        n = int(s.execute(
            text(
                "select count(*) from events "
                "where type in ('bounce','spam_complaint') "
                "and created_at >= now() - interval '7 days'"
            )
        ).scalar() or 0)
    return ConditionResult(
        name="4_sin_bounces",
        ok=n == 0,
        detail=f"events_bounce_spam_7d={n}",
    )


def _eval_cond_5_pool_virgenes(env: EnvName) -> ConditionResult:
    """Pool vírgenes elegibles (todos los tiers) >= threshold L50 (50)."""
    with get_session(env) as s:
        n = int(s.execute(
            text(
                """
                select count(distinct c.id)
                from companies c
                join contacts ct on ct.company_id = c.id
                where c.ia_fit='fit' and c.research_done_at is not null
                  and ct.is_primary=true and ct.is_optout=false
                  and not exists (
                    select 1 from messages m
                    where m.contact_id=ct.id
                      and m.status in ('sent','scheduled','drafted','approved')
                  )
                """
            )
        ).scalar() or 0)
    return ConditionResult(
        name="5_pool_virgenes",
        ok=n >= POOL_VIRGENES_THRESHOLD,
        detail=f"virgenes={n} threshold={POOL_VIRGENES_THRESHOLD}",
    )


def _eval_cond_6_no_reescribe(env: EnvName) -> ConditionResult:
    """Proxy de 'replenish no reescribe contactos tocados': 0 contacts
    con >=3 mensajes en ventana 14d."""
    with get_session(env) as s:
        n = int(s.execute(
            text(
                """
                select count(*) from (
                    select contact_id, count(*) as n
                    from messages
                    where created_at >= now() - interval '14 days'
                    group by contact_id
                    having count(*) >= 3
                ) sub
                """
            )
        ).scalar() or 0)
    return ConditionResult(
        name="6_replenish_no_reescribe",
        ok=n == 0,
        detail=f"contacts_con_3+msgs_14d={n}",
    )


def _eval_cond_7_lemwarm(env: EnvName) -> ConditionResult:
    """No verificable desde Code (L38: PM ejecuta pausa en panel Lemwarm
    manualmente). Asumimos true. Si PM no pauso, hay que cambiar esta
    funcion para que sea condicional de configuracion. Por ahora: hardcode
    True con detail explicito para auditoria."""
    return ConditionResult(
        name="7_lemwarm_pausado",
        ok=True,
        detail="hardcoded_true_per_L38 (PM debe confirmar manualmente fuera de sistema)",
    )


def evaluate_all(env: EnvName) -> Evaluation:
    return Evaluation(
        conditions=[
            _eval_cond_1_migrations(env),
            _eval_cond_2_aprobaciones(env),
            _eval_cond_3_b7_replies(env),
            _eval_cond_4_sin_bounces(env),
            _eval_cond_5_pool_virgenes(env),
            _eval_cond_6_no_reescribe(env),
            _eval_cond_7_lemwarm(env),
        ]
    )


# ─── lectura/escritura mailbox state ──────────────────────────────────────


@dataclass(slots=True)
class MailboxState:
    email: str
    hitl_mode: bool
    auto_switch_enabled: bool
    scheduled_at: datetime | None


def fetch_mailbox(env: EnvName) -> MailboxState | None:
    with get_session(env) as s:
        row = s.execute(
            text(
                "select email, hitl_mode, auto_switch_enabled, "
                "scheduled_autonomous_switch_at from mailboxes "
                "where status='active' limit 1"
            )
        ).fetchone()
    if not row:
        return None
    return MailboxState(
        email=row[0], hitl_mode=row[1],
        auto_switch_enabled=row[2],
        scheduled_at=row[3],
    )


def schedule_switch(env: EnvName, email: str, at: datetime) -> None:
    with get_session(env) as s:
        s.execute(
            text(
                "update mailboxes "
                "set scheduled_autonomous_switch_at = :at "
                "where email = :email"
            ),
            {"at": at, "email": email},
        )
        s.commit()


def cancel_schedule(env: EnvName, email: str) -> None:
    with get_session(env) as s:
        s.execute(
            text(
                "update mailboxes "
                "set scheduled_autonomous_switch_at = NULL "
                "where email = :email"
            ),
            {"email": email},
        )
        s.commit()


def execute_switch(env: EnvName, email: str) -> None:
    """UPDATE hitl_mode=false + NULL scheduled. Idempotente."""
    with get_session(env) as s:
        s.execute(
            text(
                "update mailboxes "
                "set hitl_mode = false, scheduled_autonomous_switch_at = NULL "
                "where email = :email"
            ),
            {"email": email},
        )
        s.commit()


# ─── render emails ─────────────────────────────────────────────────────────


def _conditions_html(ev: Evaluation) -> str:
    rows = "".join(
        f"<tr><td>{c.name}</td><td>{'✓' if c.ok else '✗'}</td><td>{c.detail}</td></tr>"
        for c in ev.conditions
    )
    return (
        "<table border='1' cellpadding='6' style='border-collapse:collapse'>"
        f"<thead><tr><th>Condicion</th><th>OK</th><th>Detalle</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _email_schedule(at: datetime, ev: Evaluation) -> tuple[str, str]:
    subject = f"[DEMIN] Switch a autonomo programado para {at.strftime('%Y-%m-%d %H:%M UTC')}"
    cancel_url = "https://demin-system.vercel.app/settings"
    html = (
        f"<p>El sistema ha detectado que las 7 condiciones del Bloque 6 estan verdes.</p>"
        f"<p><strong>Switch programado para:</strong> {at.strftime('%Y-%m-%d %H:%M UTC')} (~24h desde ahora).</p>"
        f"<p><strong>Estado de condiciones:</strong></p>{_conditions_html(ev)}"
        f"<p><strong>Como cancelar:</strong> entra en {cancel_url}, "
        f"seccion 'Modo autonomo', y pulsa 'Cancelar switch programado'. "
        f"Si lo prefieres, desactiva el toggle 'auto-switch' completamente.</p>"
        f"<p>Cap de envio se mantendra en 20/dia tras switch -- sin escalado "
        f"automatico. PM decide subir cap manualmente despues.</p>"
        f"<p>Nota: pool threshold ajustado de 100 a 50 segun decision PM "
        f"sesion 2026-05-26 (L50). 50 virgenes + cadencia D+14/D+28 + 20/dia "
        f"= ~10 dias de operacion autonoma sin intervencion.</p>"
    )
    return subject, html


def _email_cancelled(broken: list[ConditionResult]) -> tuple[str, str]:
    subject = "[DEMIN] Switch a autonomo CANCELADO -- condicion rota"
    rows = "".join(f"<li><strong>{c.name}</strong>: {c.detail}</li>" for c in broken)
    html = (
        f"<p>El switch programado se ha cancelado porque alguna condicion "
        f"dejo de cumplirse:</p><ul>{rows}</ul>"
        f"<p>El sistema sigue en modo HITL (Gonzalo aprueba drafts manualmente "
        f"en /approval-queue). Cuando las condiciones vuelvan a estar verdes "
        f"se programara un nuevo switch automaticamente (con email previo 24h)."
        f"</p>"
    )
    return subject, html


def _email_executed() -> tuple[str, str]:
    subject = "[DEMIN] MODO AUTONOMO ACTIVADO"
    rollback_url = "https://demin-system.vercel.app/settings"
    html = (
        f"<p>El sistema acaba de pasar a modo autonomo: <code>hitl_mode=false</code>.</p>"
        f"<p>Los drafts se aprueban automaticamente sin requerir intervencion "
        f"de Gonzalo en /approval-queue. Cap envio 20/dia.</p>"
        f"<p><strong>Rollback de emergencia:</strong> ve a {rollback_url}, "
        f"seccion 'Modo autonomo', y pulsa 'Volver a HITL ahora'. El cambio "
        f"es inmediato.</p>"
        f"<p>Sistema continua monitoreado por auto_pause (bounce >2% o spam "
        f">0.1% -> pausa enviar). Si auto_pause dispara, recibiras email "
        f"separado.</p>"
    )
    return subject, html


def _email_eval_only(ev: Evaluation) -> tuple[str, str]:
    subject = f"[DEMIN] Condiciones autonomo: {ev.n_green}/7 verdes (auto-switch OFF)"
    html = (
        f"<p>auto_switch_enabled=false. El sistema evalua las condiciones "
        f"pero NO programa switch.</p>"
        f"<p>Si quieres activar autonomo, entra en /settings y activa el "
        f"toggle 'auto-switch' -- cuando las condiciones esten verdes el "
        f"sistema lo programara con email 24h antes.</p>"
        f"<p><strong>Estado actual:</strong></p>{_conditions_html(ev)}"
    )
    return subject, html


# ─── orquestacion ─────────────────────────────────────────────────────────


def run(env: EnvName, dry_run: bool) -> int:
    print("=" * 76)
    print(f"auto_switch_to_autonomous  env={env}  dry_run={dry_run}")
    print("=" * 76)

    mb = fetch_mailbox(env)
    if not mb:
        print("  (sin mailbox activo). Nada que hacer.")
        return 0

    ev = evaluate_all(env)
    print(f"\n  Mailbox: {mb.email}")
    print(f"  hitl_mode={mb.hitl_mode}  auto_switch_enabled={mb.auto_switch_enabled}")
    print(f"  scheduled_at={mb.scheduled_at}")
    print(f"\n  Condiciones ({ev.n_green}/7 verdes):")
    for c in ev.conditions:
        mark = "OK" if c.ok else "NO"
        print(f"    [{mark}] {c.name:30s} {c.detail}")

    # Caso 0: ya en modo autonomo. No hace nada.
    if not mb.hitl_mode:
        print("\n  Ya esta en modo AUTONOMO. Sin accion.")
        return 0

    # Caso 1: auto_switch_enabled=false.
    if not mb.auto_switch_enabled:
        # Si por casualidad hay schedule pendiente (PM puede haber desactivado
        # despues de programar), cancelar.
        if mb.scheduled_at:
            print("\n  auto_switch_enabled=false PERO hay schedule pendiente -> cancelar.")
            if not dry_run:
                cancel_schedule(env, mb.email)
                broken = [ConditionResult(
                    name="auto_switch_enabled",
                    ok=False,
                    detail="PM desactivo toggle en /settings",
                )]
                subject, html = _email_cancelled(broken)
                send_operational_email(
                    to=NOTIFICATION_RECIPIENTS, subject=subject, html=html,
                )
            return 0
        print("\n  auto_switch_enabled=false. Solo evalua, no programa switch.")
        # Email diario solo si condiciones cambian (TODO simple para v1):
        # mandar email solo cuando todas verdes para no spammear.
        if ev.all_green and not dry_run:
            subject, html = _email_eval_only(ev)
            send_operational_email(
                to=NOTIFICATION_RECIPIENTS, subject=subject, html=html,
            )
        return 0

    # Caso 2: hay schedule + alguna condicion rota -> cancelar.
    if mb.scheduled_at is not None:
        broken = [c for c in ev.conditions if not c.ok]
        if broken:
            print(f"\n  Hay schedule {mb.scheduled_at} PERO {len(broken)} condiciones rotas -> cancelar.")
            if not dry_run:
                cancel_schedule(env, mb.email)
                subject, html = _email_cancelled(broken)
                send_operational_email(
                    to=NOTIFICATION_RECIPIENTS, subject=subject, html=html,
                )
            return 0
        # Schedule + todas verdes -> chequear si toca disparar.
        now = datetime.now(timezone.utc)
        if now >= mb.scheduled_at:
            print(f"\n  Schedule {mb.scheduled_at} alcanzado Y 7/7 verdes -> EJECUTAR SWITCH.")
            if not dry_run:
                execute_switch(env, mb.email)
                subject, html = _email_executed()
                send_operational_email(
                    to=NOTIFICATION_RECIPIENTS, subject=subject, html=html,
                )
            return 0
        # Schedule no alcanzado todavia -> wait.
        time_left = mb.scheduled_at - now
        print(f"\n  Schedule {mb.scheduled_at} aun en futuro ({time_left}). Esperar.")
        return 0

    # Caso 3: NO hay schedule. Si todas verdes -> programar.
    if ev.all_green:
        at = datetime.now(timezone.utc) + timedelta(hours=SCHEDULE_LEAD_HOURS)
        print(f"\n  7/7 verdes Y no hay schedule -> PROGRAMAR para {at.isoformat()}")
        if not dry_run:
            schedule_switch(env, mb.email, at)
            subject, html = _email_schedule(at, ev)
            send_operational_email(
                to=NOTIFICATION_RECIPIENTS, subject=subject, html=html,
            )
        return 0

    print(f"\n  {ev.n_green}/7 verdes -- no procede schedule. Sin accion.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="Evalua y reporta sin tocar BD ni enviar email.")
    args = p.parse_args(argv)
    return run(args.env, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
