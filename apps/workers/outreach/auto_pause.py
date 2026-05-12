"""auto_pause.py -- Sprint 4 paso 7. Pausa automatica de buzones por
bounce/spam (§9.4 + Apendice A regla 6).

Para cada mailbox status='active', calcula bounce rate y spam rate en
ventana rolling 7 dias usando `events` table. Si supera threshold,
UPDATE mailbox status='paused' + pause_reason + INSERT event 'mailbox_paused'.

Thresholds (§9.4):
- bounce_rate > 2% en 7d -> pause_reason='auto_bounce_2pct'
- spam_complaints > 0.1% en 7d -> pause_reason='auto_spam_0.1pct'

Sample minimo (`MIN_SAMPLE_FOR_PAUSE` = 50): si el mailbox ha enviado
menos de 50 messages en la ventana, el rate es ruidoso -- NO pausar
aunque el porcentaje aparente supere el threshold. Evita pausa por 1
bounce sobre 10 envios (10% pero estadisticamente irrelevante).

Senal spam:
- Paso 7 NO tiene señal automatica de spam complaints (requiere Postmaster
  Tools API o IMAP poll para detectar FBL reports). El threshold spam
  queda armado en el codigo pero sin entrada real -- la cuenta de
  events.type='spam_complaint' permanece en 0. Activacion real: Fase 3
  cuando poll_imap + Postmaster Tools entren.
- Paso 7 solo opera con bounce events sincronos de Gmail API (send_gmail
  4xx con keywords bounce). Hard bounces invisibles (DSN al buzon sin
  poll_imap) quedan como deuda tecnica conocida.

Decision PM 2026-05-12 (opcion A): auto_pause solo cambia `mailboxes.status`,
NO toca `messages.status`. send_gmail.py comprueba `mailbox.status='active'`
antes de enviar -- los scheduled del mailbox pausado quedan en BD pero
no se procesan hasta que un humano reanuda desde `/settings` (botoon
pausa de emergencia / reanudar).

Politica de reanudacion: NUNCA automatica. Apendice A regla 6: "nunca
desactives auto-pausa sin aprobacion humana explicita".

CLI:
    cd apps/workers
    uv run python -m outreach.auto_pause --env dev --dry-run
    uv run python -m outreach.auto_pause --env dev
    uv run python -m outreach.auto_pause --env prod  (cron cada hora)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text

from shared.config import settings
from shared.db import get_session

EnvName = Literal["dev", "prod"]

BOUNCE_RATE_THRESHOLD = 0.02
"""§9.4: bounce >2% en 7d disparA pausa."""

SPAM_RATE_THRESHOLD = 0.001
"""§9.4: spam complaints >0.1% en 7d disparA pausa. Sin senal real
hasta Fase 3 (Postmaster Tools / IMAP poll); threshold armado pero
inactivo en paso 7."""

MIN_SAMPLE_FOR_PAUSE = 50
"""Sample minimo de envios en ventana para que el rate sea estadisticamente
significativo. Sin ello, 1 bounce sobre 10 envios (10%) pausaria el
mailbox prematuramente."""

WINDOW_INTERVAL = "7 days"

logger = logging.getLogger("demin.auto_pause")
if not logger.handlers:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass(slots=True)
class MailboxStats:
    mailbox_id: str
    mailbox_email: str
    sent_7d: int
    bounces_7d: int
    spam_7d: int

    @property
    def bounce_rate(self) -> float:
        return self.bounces_7d / self.sent_7d if self.sent_7d > 0 else 0.0

    @property
    def spam_rate(self) -> float:
        return self.spam_7d / self.sent_7d if self.sent_7d > 0 else 0.0


def fetch_active_mailbox_stats(env: EnvName) -> list[MailboxStats]:
    """Para cada mailbox active, computa sent/bounces/spam en 7d via events."""
    with get_session(env) as s:
        rows = s.execute(
            text(
                f"""
                SELECT
                    mb.id AS mailbox_id,
                    mb.email,
                    coalesce(sum(case when e.type = 'message_sent' then 1 else 0 end), 0) AS sent_7d,
                    coalesce(sum(case when e.type = 'bounce' then 1 else 0 end), 0) AS bounces_7d,
                    coalesce(sum(case when e.type = 'spam_complaint' then 1 else 0 end), 0) AS spam_7d
                FROM mailboxes mb
                LEFT JOIN messages m ON m.mailbox_id = mb.id
                LEFT JOIN events e ON e.message_id = m.id
                  AND e.created_at > now() - interval '{WINDOW_INTERVAL}'
                WHERE mb.status = 'active'
                GROUP BY mb.id, mb.email
                ORDER BY mb.email
                """
            )
        ).mappings().all()
    return [
        MailboxStats(
            mailbox_id=str(r["mailbox_id"]),
            mailbox_email=r["email"],
            sent_7d=int(r["sent_7d"]),
            bounces_7d=int(r["bounces_7d"]),
            spam_7d=int(r["spam_7d"]),
        )
        for r in rows
    ]


def decide_pause_reason(stats: MailboxStats) -> str | None:
    """Devuelve pause_reason si toca pausar, None si no."""
    if stats.sent_7d < MIN_SAMPLE_FOR_PAUSE:
        return None
    if stats.bounce_rate > BOUNCE_RATE_THRESHOLD:
        return "auto_bounce_2pct"
    if stats.spam_rate > SPAM_RATE_THRESHOLD:
        return "auto_spam_0.1pct"
    return None


def pause_mailbox(env: EnvName, stats: MailboxStats, reason: str) -> None:
    """UPDATE mailboxes SET status='paused' + INSERT event mailbox_paused."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE mailboxes
                SET status = 'paused', pause_reason = :reason
                WHERE id = cast(:mid as uuid)
                """
            ),
            {"reason": reason, "mid": stats.mailbox_id},
        )
        s.execute(
            text(
                """
                INSERT INTO events (type, payload)
                VALUES ('mailbox_paused', cast(:payload as jsonb))
                """
            ),
            {
                "payload": json.dumps({
                    "mailbox_id": stats.mailbox_id,
                    "mailbox_email": stats.mailbox_email,
                    "reason": reason,
                    "sent_7d": stats.sent_7d,
                    "bounces_7d": stats.bounces_7d,
                    "spam_7d": stats.spam_7d,
                    "bounce_rate": round(stats.bounce_rate, 4),
                    "spam_rate": round(stats.spam_rate, 4),
                }),
            },
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(f"auto_pause  env={env}  dry_run={args.dry_run}")
    print("=" * 76)

    stats_list = fetch_active_mailbox_stats(env)
    if not stats_list:
        print("No hay mailboxes activos. Nada que hacer.")
        return 0

    paused = 0
    for stats in stats_list:
        reason = decide_pause_reason(stats)
        rate_str = (
            f"bounce={stats.bounce_rate:.2%} spam={stats.spam_rate:.2%} "
            f"sent_7d={stats.sent_7d} bounces={stats.bounces_7d} spam={stats.spam_7d}"
        )
        if reason is None:
            print(f"  [OK]    {stats.mailbox_email}  {rate_str}")
            continue
        print(f"  [PAUSE] {stats.mailbox_email}  reason={reason}  {rate_str}")
        if not args.dry_run:
            pause_mailbox(env, stats, reason)
            paused += 1

    print()
    print("=" * 76)
    suffix = " (dry-run, sin BD writes)" if args.dry_run else ""
    print(f"FIN auto_pause  env={env}  paused={paused}{suffix}")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
