"""classify_replies.py -- Fase 3 Sprint 5.

Procesa filas en `replies` con `category IS NULL`. Por cada una:
1. Carga contexto del envío original (subject angle, contact cargo, empresa tier).
2. Llama LLM Haiku con prompt `classify_reply.md` (output JSON estructurado).
3. UPDATE reply.category, is_explicit_optout, ai_classification_reason,
   ai_suggested_response.
4. Si `is_explicit_optout=true` -> UPDATE contacts.is_optout=true (Apéndice A
   regla 2). Apéndice A regla 2: nunca ignores opt-out explicito.

Idempotente: solo procesa replies con category IS NULL.

Categorías: interesado | pide_info | no_ahora | no_interesado | rebote |
fuera_oficina | desconocido.

CLI:
    cd apps/workers
    uv run python -m replies.classify_replies --env prod
    uv run python -m replies.classify_replies --env dev --limit 5 --max-cost-usd 0.20

Exit codes:
- 0: OK
- 1: una o mas replies fallaron (no fatal, las marca con category='desconocido'
     + reason='llm_error')
- 2: error config / BD
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import text

from shared.db import get_session
from shared.llm import call_llm

EnvName = Literal["dev", "prod"]

_PROMPT_PATH = (
    Path(__file__).parent.parent / "shared" / "prompts" / "classify_reply.md"
)

USD_COST_CAP_DEFAULT = 1.0
"""Cap LLM por run. Haiku ~$0.001/clasificacion, 1000 replies cabrian dentro."""

VALID_CATEGORIES = (
    "interesado", "pide_info", "no_ahora", "no_interesado",
    "rebote", "fuera_oficina", "desconocido",
)

logger = logging.getLogger("demin.classify_replies")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_prompt() -> tuple[str, str]:
    """Carga system + user template del .md. Formato: separados por '## User'.

    El .md tiene secciones '## System' y '## User template'. Reusamos la misma
    convencion que generate_email_*.md.
    """
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split("## User template")
    if len(parts) < 2:
        # Fallback: si no encuentra el separador, usa todo como system + user
        # template fijo.
        return raw.strip(), "{body}"
    system_chunk = parts[0]
    if "## System" in system_chunk:
        system_chunk = system_chunk.split("## System", 1)[1]
    # User template empieza tras '## User template'
    user_template = parts[1].strip()
    return system_chunk.strip(), user_template


def fetch_pending_replies(
    env: EnvName, limit: int | None
) -> list[dict[str, Any]]:
    """Trae replies con category IS NULL + contexto del message original."""
    sql = """
        SELECT
            r.id::text AS reply_id,
            r.message_id::text AS message_id,
            r.contact_id::text AS contact_id,
            r.received_at,
            r.raw_subject,
            r.raw_body,
            m.subject AS original_subject,
            m.step_index,
            c.cargo AS contact_cargo,
            c.email AS contact_email,
            co.tier,
            co.nombre AS empresa_nombre
        FROM replies r
        LEFT JOIN messages m ON m.id = r.message_id
        LEFT JOIN contacts c ON c.id = r.contact_id
        LEFT JOIN companies co ON co.id = c.company_id
        WHERE r.category IS NULL
        ORDER BY r.received_at ASC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_session(env) as s:
        rows = s.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


def _angle_from_step_index(step_index: int | None) -> str:
    """step_index 0=opening, 1=reframe, 2=closing."""
    if step_index == 0 or step_index is None:
        return "opening"
    if step_index == 1:
        return "reframe"
    if step_index == 2:
        return "closing"
    return "unknown"


def classify_one_reply(
    system: str, user_template: str, reply: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Llama LLM. Devuelve (parsed_json, meta llm)."""
    angle = _angle_from_step_index(reply.get("step_index"))
    user = user_template.format(
        subject=reply.get("raw_subject", "") or "",
        from_addr=reply.get("contact_email", "") or "",
        body=(reply.get("raw_body") or "")[:8000],  # cap defensivo
        empresa_nombre=reply.get("empresa_nombre", "") or "",
        tier=reply.get("tier", "") or "",
        contact_cargo=reply.get("contact_cargo", "") or "",
        angle=angle,
    )
    text_out, meta = call_llm(
        task="classify_reply",
        system=system,
        user=user,
        max_tokens=800,
        response_format="text",  # parseamos JSON manual con tolerancia
    )
    # Strip code fences si el LLM los añade.
    cleaned = text_out.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[len("json"):].lstrip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    parsed = json.loads(cleaned)

    # Validacion minima.
    cat = parsed.get("category", "desconocido")
    if cat not in VALID_CATEGORIES:
        cat = "desconocido"
        parsed["category"] = cat
    parsed["is_explicit_optout"] = bool(parsed.get("is_explicit_optout", False))
    if not isinstance(parsed.get("reason"), str):
        parsed["reason"] = ""
    sr = parsed.get("suggested_response")
    if sr is not None and not isinstance(sr, str):
        parsed["suggested_response"] = None
    return parsed, meta


def update_reply(
    env: EnvName,
    reply_id: str,
    contact_id: str,
    parsed: dict[str, Any],
) -> None:
    """UPDATE replies + (si opt-out) UPDATE contacts.is_optout=true."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE replies SET
                    category = :category,
                    is_explicit_optout = :is_optout,
                    ai_classification_reason = :reason,
                    ai_suggested_response = :suggested
                WHERE id = cast(:rid as uuid)
                """
            ),
            {
                "category": parsed["category"],
                "is_optout": parsed["is_explicit_optout"],
                "reason": (parsed.get("reason") or "")[:2000],
                "suggested": parsed.get("suggested_response"),
                "rid": reply_id,
            },
        )
        if parsed["is_explicit_optout"]:
            s.execute(
                text(
                    """
                    UPDATE contacts SET is_optout = true
                    WHERE id = cast(:cid as uuid)
                    """
                ),
                {"cid": contact_id},
            )
            logger.info(
                "OPTOUT enforced contact_id=%s (Apendice A regla 2)", contact_id
            )
        s.commit()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--max-cost-usd", type=float, default=USD_COST_CAP_DEFAULT)
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(
        f"classify_replies  env={env}  limit={args.limit}  "
        f"max_cost_usd={args.max_cost_usd}"
    )
    print("=" * 76)

    try:
        system, user_template = load_prompt()
    except FileNotFoundError as e:
        logger.error("prompt no encontrado: %s", e)
        return 2

    pending = fetch_pending_replies(env, args.limit)
    if not pending:
        print("No hay replies pendientes de clasificar. Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} replies a procesar")

    counts: dict[str, int] = {"ok": 0, "failed": 0, "optout": 0}
    cat_counts: dict[str, int] = {}
    total_cost = 0.0
    t0 = time.monotonic()

    for i, reply in enumerate(pending, 1):
        if total_cost > args.max_cost_usd:
            print(f"PARADA: coste {total_cost:.2f} USD > cap {args.max_cost_usd}")
            break

        try:
            parsed, meta = classify_one_reply(system, user_template, reply)
        except json.JSONDecodeError as e:
            logger.warning(
                "JSON decode failed reply=%s, marking desconocido: %s",
                reply["reply_id"], e,
            )
            update_reply(
                env, reply["reply_id"], reply["contact_id"],
                {"category": "desconocido", "is_explicit_optout": False,
                 "reason": f"llm_json_error: {str(e)[:200]}",
                 "suggested_response": None},
            )
            counts["failed"] += 1
            cat_counts["desconocido"] = cat_counts.get("desconocido", 0) + 1
            continue
        except Exception as e:
            logger.exception("classify failed reply=%s: %s", reply["reply_id"], e)
            counts["failed"] += 1
            continue

        cost = meta.get("cost_usd") or 0.0
        total_cost += cost

        try:
            update_reply(env, reply["reply_id"], reply["contact_id"], parsed)
        except Exception as e:
            logger.exception("update failed reply=%s: %s", reply["reply_id"], e)
            counts["failed"] += 1
            continue

        counts["ok"] += 1
        if parsed["is_explicit_optout"]:
            counts["optout"] += 1
        cat_counts[parsed["category"]] = cat_counts.get(parsed["category"], 0) + 1

        print(
            f"  [{i:>3}/{len(pending)}] reply={reply['reply_id'][:8]} "
            f"cat={parsed['category']:<14} optout={parsed['is_explicit_optout']!s:<5} "
            f"cost=${cost:.4f}"
        )

    elapsed = time.monotonic() - t0
    print()
    print("=" * 76)
    print(f"FIN classify_replies  elapsed={elapsed:.1f}s")
    print(f"  ok:     {counts['ok']}")
    print(f"  failed: {counts['failed']}")
    print(f"  optout enforced: {counts['optout']}")
    print(f"  categorias: {cat_counts}")
    print(f"  coste total USD: {total_cost:.4f} (cap {args.max_cost_usd})")
    print("=" * 76)

    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
