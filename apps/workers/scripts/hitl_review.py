"""hitl_review.py — Sprint 4 paso 6 (HITL terminal).

Itera `messages.status='drafted'` ordenados por created_at, muestra cada
draft con contexto (empresa, contact, research, ángulo, validaciones
automáticas) y prompt de acción [a/e/r/x/s/q]. NO envía emails — el envío
real es paso 7.

Acciones:
- [a]probar: UPDATE messages SET status='approved', approved_by=:user, approved_at=now()
- [e]ditar+aprobar: edición inline con marcador EOF (multiplataforma —
  no requiere $EDITOR/notepad), marca edited=true + status='approved'
- [r]egenerar: cancela el draft actual (status='cancelled' +
  reason_in_research_snapshot='regenerated_in_hitl'), llama
  generate_draft.process_one_contact() y muestra el nuevo
- [x] rechazar+excluir: cancela el draft, marca contact.is_optout=true
  con reason='rechazado_en_hitl' (regla 2 del Apéndice A — opt-out
  permanente)
- [s]altar: pasa al siguiente sin tocar el draft (queda en 'drafted'
  para revisar después)
- [q]uit: resumen + salir

CLI:
    cd apps/workers
    uv run python -m scripts.hitl_review --env dev
    uv run python -m scripts.hitl_review --env dev --tier T3
    uv run python -m scripts.hitl_review --env prod --user gonzalo.perez@demingroupmadrid.com
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text

EnvName = Literal["dev", "prod"]

DEFAULT_USER = "albertobueno10@gmail.com"
EOF_MARKER = "EOF"

logger = logging.getLogger("demin.hitl_review")
if not logger.handlers:
    logging.basicConfig(
        level="WARNING",  # default WARNING para no contaminar la UI terminal
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass(slots=True)
class DraftRow:
    message_id: str
    contact_id: str
    company_id: str
    nif: str
    nombre_empresa: str
    tier: str
    web: str | None
    email: str
    email_type: str
    email_priority: int
    nombre_contacto: str | None
    cargo_contacto: str | None
    step_index: int
    angle: str
    subject: str
    body: str
    research_snapshot: dict[str, Any]
    research_data: dict[str, Any]


# ─── Funciones puras (testables sin BD ni stdin) ───────────────────────────


def format_draft_for_display(d: DraftRow, idx: int, total: int) -> str:
    """Compone el bloque de texto que se imprime al usuario por cada draft.
    Estructura el resumen + draft + razonamiento + validaciones automáticas."""
    sep = "━" * 76
    razonamiento = d.research_snapshot.get("_razonamiento_breve", "")
    failed = d.research_snapshot.get("_failed_validations") or []
    validation_line = (
        "✅ todas las validaciones automáticas pasan"
        if not failed
        else f"⚠ validaciones fallidas: {', '.join(failed)}"
    )
    razon_line = (
        f"\nRAZONAMIENTO LLM: {razonamiento}\n"
        if razonamiento
        else ""
    )
    contact_line = (
        f"Contacto: {d.email}"
        + (f" ({d.nombre_contacto}" if d.nombre_contacto else "")
        + (f", {d.cargo_contacto}" if d.cargo_contacto else "")
        + (")" if d.nombre_contacto else "")
        + f", email_type={d.email_type}, prio={d.email_priority}"
    )
    return (
        f"\n{sep}\n"
        f"[{idx}/{total}]  {d.nombre_empresa} ({d.nif}, {d.tier})\n"
        f"       {d.web or '(sin web)'}\n"
        f"       {contact_line}\n"
        f"       Ángulo: {d.angle} (step {d.step_index})\n"
        f"\n"
        f"ASUNTO: {d.subject}\n"
        f"CUERPO:\n  {d.body.replace(chr(10), chr(10) + '  ')}\n"
        f"{razon_line}"
        f"\n{validation_line}\n"
        f"{sep}\n"
        f"[a]probar  [e]ditar+aprobar  [r]egenerar  [x] rechazar+excluir contact  "
        f"[s]altar  [q]uit\n"
    )


def parse_eof_input(lines: list[str], marker: str = EOF_MARKER) -> str:
    """Lee líneas hasta toparse con `marker` exacto en una línea sola.
    Devuelve el contenido sin el marcador. Acepta `marker` con
    whitespace alrededor para ser tolerante."""
    out_lines: list[str] = []
    for line in lines:
        if line.strip() == marker:
            break
        out_lines.append(line)
    return "\n".join(out_lines).rstrip()


def normalize_action(raw: str) -> str | None:
    """Normaliza input del usuario a una acción canónica. Devuelve None
    si no matchea ninguna acción válida."""
    s = raw.strip().lower()
    if s in ("a", "aprobar", "approve"):
        return "a"
    if s in ("e", "editar", "edit"):
        return "e"
    if s in ("r", "regenerar", "regen"):
        return "r"
    if s in ("x", "rechazar", "reject", "optout"):
        return "x"
    if s in ("s", "saltar", "skip"):
        return "s"
    if s in ("q", "quit", "exit"):
        return "q"
    return None


# ─── Acceso a BD ───────────────────────────────────────────────────────────


def fetch_drafts(env: EnvName, tier: str | None) -> list[DraftRow]:
    """Trae los messages.status='drafted' con todo el contexto necesario
    para el HITL, ordenados por (company.nif, step_index, created_at)."""
    from shared.db import get_session  # noqa: PLC0415

    sql = """
        SELECT
            m.id          AS message_id,
            m.contact_id,
            m.step_index,
            m.angle,
            m.subject,
            m.body,
            m.research_snapshot,
            ct.email,
            ct.email_type,
            ct.email_priority,
            ct.nombre  AS contact_nombre,
            ct.cargo   AS contact_cargo,
            c.id       AS company_id,
            c.nif,
            c.nombre   AS company_nombre,
            c.tier,
            c.web,
            c.research_data
        FROM messages m
        JOIN contacts ct ON ct.id = m.contact_id
        JOIN companies c ON c.id = ct.company_id
        WHERE m.status = 'drafted'
    """
    params: dict[str, Any] = {}
    if tier:
        sql += " AND c.tier = :tier"
        params["tier"] = tier
    sql += " ORDER BY c.nif, m.step_index, m.created_at"

    with get_session(env) as s:
        rows = s.execute(text(sql), params).mappings().all()
    return [
        DraftRow(
            message_id=str(r["message_id"]),
            contact_id=str(r["contact_id"]),
            company_id=str(r["company_id"]),
            nif=r["nif"],
            nombre_empresa=r["company_nombre"],
            tier=r["tier"],
            web=r["web"],
            email=r["email"],
            email_type=r["email_type"],
            email_priority=r["email_priority"],
            nombre_contacto=r["contact_nombre"],
            cargo_contacto=r["contact_cargo"],
            step_index=r["step_index"],
            angle=r["angle"],
            subject=r["subject"],
            body=r["body"],
            research_snapshot=r["research_snapshot"] or {},
            research_data=r["research_data"] or {},
        )
        for r in rows
    ]


def approve(env: EnvName, message_id: str, user: str, edited: bool = False) -> None:
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages
                SET status='approved', approved_by=:u, approved_at=now(), edited=:e
                WHERE id = cast(:id as uuid)
                """
            ),
            {"u": user, "e": edited, "id": message_id},
        )


def update_subject_body(env: EnvName, message_id: str, subject: str, body: str) -> None:
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages SET subject=:s, body=:b
                WHERE id = cast(:id as uuid)
                """
            ),
            {"s": subject, "b": body, "id": message_id},
        )


def cancel_draft(env: EnvName, message_id: str, reason: str) -> None:
    """Marca el draft como cancelled. La razón se mete en research_snapshot
    bajo `_cancelled_reason` para auditar."""
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages
                SET status='cancelled',
                    research_snapshot = jsonb_set(
                        coalesce(research_snapshot, '{}'::jsonb),
                        '{_cancelled_reason}',
                        to_jsonb(:r::text)
                    )
                WHERE id = cast(:id as uuid)
                """
            ),
            {"r": reason, "id": message_id},
        )


def optout_contact(env: EnvName, contact_id: str, reason: str) -> None:
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE contacts
                SET is_optout=true, optout_at=now(), optout_reason=:r
                WHERE id = cast(:id as uuid)
                """
            ),
            {"r": reason, "id": contact_id},
        )


# ─── UI / IO ──────────────────────────────────────────────────────────────


def read_eof_block(label: str) -> str:
    """Lee múltiples líneas de stdin hasta una sola línea con `EOF`.
    Multiplataforma — no necesita $EDITOR ni notepad."""
    print(f"\n--- editar {label}: pega/escribe el nuevo texto y termina con una línea con solo `{EOF_MARKER}` ---")
    lines: list[str] = []
    try:
        while True:
            line = input()
            if line.strip() == EOF_MARKER:
                break
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).rstrip()


def _regenerate_draft(env: EnvName, d: DraftRow, user: str) -> DraftRow | None:
    """Cancela el draft actual y genera uno nuevo con generate_draft.
    Devuelve el DraftRow nuevo o None si la regeneración falla."""
    from pipeline.generate_draft import (  # noqa: PLC0415
        PendingContact,
        _load_prompt_for_angle,
        insert_draft,
        process_one_contact,
    )

    cancel_draft(env, d.message_id, reason="regenerated_in_hitl")

    item = PendingContact(
        contact_id=d.contact_id,
        company_id=d.company_id,
        email=d.email,
        email_type=d.email_type,
        email_priority=d.email_priority,
        nombre_contacto=d.nombre_contacto,
        cargo_contacto=d.cargo_contacto,
        nif=d.nif,
        nombre_empresa=d.nombre_empresa,
        tier=d.tier,
        research_data=d.research_data,
    )
    angle = d.angle
    system, user_template = _load_prompt_for_angle(angle)  # type: ignore[arg-type]
    print("  regenerando draft...")
    result = process_one_contact(env, item, angle, system, user_template)  # type: ignore[arg-type]
    if not result.success or result.draft is None:
        print(f"  REGENERACIÓN FALLÓ: {result.error}")
        return None

    new_id = insert_draft(env, item, result.draft, angle)  # type: ignore[arg-type]
    print(f"  draft nuevo: {new_id[:8]}")

    # Recompose DraftRow para mostrar
    snapshot = dict(d.research_data)
    if result.draft.failed_validations:
        snapshot["_failed_validations"] = result.draft.failed_validations
    snapshot["_razonamiento_breve"] = result.draft.razonamiento
    return DraftRow(
        message_id=new_id,
        contact_id=d.contact_id,
        company_id=d.company_id,
        nif=d.nif,
        nombre_empresa=d.nombre_empresa,
        tier=d.tier,
        web=d.web,
        email=d.email,
        email_type=d.email_type,
        email_priority=d.email_priority,
        nombre_contacto=d.nombre_contacto,
        cargo_contacto=d.cargo_contacto,
        step_index=d.step_index,
        angle=d.angle,
        subject=result.draft.subject,
        body=result.draft.body,
        research_snapshot=snapshot,
        research_data=d.research_data,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="hitl_review — auditoría humana de drafts antes de envío (Sprint 4 paso 6)"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--tier", choices=("T1", "T2", "T3", "T4"), default=None,
                   help="Filtra por tier. Default = todos los drafts.")
    p.add_argument("--user", default=DEFAULT_USER,
                   help=f"Email del aprobador (queda en messages.approved_by). Default: {DEFAULT_USER}")
    args = p.parse_args(argv)
    env: EnvName = args.env

    drafts = fetch_drafts(env, args.tier)
    if not drafts:
        print("No hay drafts en status='drafted'. Nada que revisar.")
        return 0

    print(f"[fetch] {len(drafts)} drafts pendientes de revisión "
          f"(env={env}, tier={args.tier or 'todos'}, user={args.user})")

    counts = {"a": 0, "e": 0, "r": 0, "x": 0, "s": 0}
    i = 0
    while i < len(drafts):
        d = drafts[i]
        # res_data del snapshot puede no tener razonamiento si el insert
        # original no lo mete; tomamos del snapshot la versión guardada
        # (que sí lo trae al regenerar) o del research_data como fallback.
        print(format_draft_for_display(d, idx=i + 1, total=len(drafts)))

        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nsalida por interrupción — drafts no procesados quedan en drafted")
            break

        action = normalize_action(raw)
        if action is None:
            print(f"  acción no reconocida: {raw!r}. Opciones: a/e/r/x/s/q")
            continue

        if action == "q":
            print("\nsalida solicitada (q) — drafts no procesados quedan en drafted")
            break

        if action == "a":
            approve(env, d.message_id, args.user)
            counts["a"] += 1
            print(f"  ✓ aprobado {d.message_id[:8]}")
            i += 1
            continue

        if action == "e":
            new_subject = read_eof_block("ASUNTO (deja vacío y EOF para mantener el actual)")
            if not new_subject:
                new_subject = d.subject
            new_body = read_eof_block("CUERPO (deja vacío y EOF para mantener el actual)")
            if not new_body:
                new_body = d.body
            update_subject_body(env, d.message_id, new_subject, new_body)
            approve(env, d.message_id, args.user, edited=True)
            counts["e"] += 1
            print(f"  ✓ editado+aprobado {d.message_id[:8]}")
            i += 1
            continue

        if action == "r":
            new_d = _regenerate_draft(env, d, args.user)
            counts["r"] += 1
            if new_d is None:
                # Regeneración falló — pasar al siguiente
                i += 1
                continue
            # Reemplazar en la lista para mostrar el nuevo
            drafts[i] = new_d
            continue  # NO incrementa i — re-muestra el draft regenerado

        if action == "x":
            cancel_draft(env, d.message_id, reason="rechazado_en_hitl")
            optout_contact(env, d.contact_id, reason="rechazado_en_hitl_por_revisor")
            counts["x"] += 1
            print(f"  ✗ rechazado + opt-out {d.email}")
            i += 1
            continue

        if action == "s":
            counts["s"] += 1
            print(f"  → saltado, queda como drafted")
            i += 1
            continue

    sep = "━" * 76
    print(f"\n{sep}")
    print(f"RESUMEN sesión HITL")
    print(f"  aprobados:           {counts['a']}")
    print(f"  editados+aprobados:  {counts['e']}")
    print(f"  regenerados:         {counts['r']}")
    print(f"  rechazados+opt-out:  {counts['x']}")
    print(f"  saltados:            {counts['s']}")
    print(f"  pendientes (no procesados): {len(drafts) - sum(counts.values())}")
    print(sep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
