"""generate_draft.py — Sprint 4 paso 6 (D20).

Itera contacts cuya `companies.research_done_at IS NOT NULL` (sin `_failed`)
del tier solicitado, recupera 5 chunks del KB con Voyage query embedding +
pgvector cosine similarity, carga el prompt versionado del ángulo
solicitado (`generate_email_{angle}.md`), llama Sonnet 4.6 vía
`call_llm(task='generate_draft')`, valida post-generación según §10.3
(4 reglas — la 5ª "no nombres inventados" la cubre el HITL humano), e
inserta en `messages.status='drafted'`. Idempotente con `--rerun` que
ignora el filtro de "no message previo para (contact, step_index)".

**Concurrencia**: secuencial single-worker por defecto. Voyage Free tier
es 3 RPM → ~22s entre embeds; paralelizar saturaría rate limit.
`embed_documents.py` y `smoke_kb_retrieval.py` siguen el mismo patrón.
Cuando Voyage tenga payment method, los sleeps van a 0 trivialmente.

**Validaciones automáticas (§10.3 — 4 de 5)**:
- body entre 50 y 180 palabras
- subject entre 3 y 8 palabras
- ni body ni subject contienen emojis ni signos de exclamación
- ni body ni subject contienen patrones tipo "garantiz", "en N días", "por N €"
- (omitida) "no nombres inventados" — verificación contra research_data es
  frágil; la cubre el HITL humano del paso 6.

Si todas las validaciones fallan tras 2 reintentos LLM, el draft se inserta
igualmente con `_failed_validations` en `research_snapshot` para que el
HITL lo vea y decida.

Cap defensivo `--max-cost-usd 5.0` (Sonnet 4.6 ~$0.005/draft, 5 contacts ≈
$0.025).

CLI:
    cd apps/workers
    uv run python -m pipeline.generate_draft --env dev --tier T3 --angle opening --limit 5
    uv run python -m pipeline.generate_draft --env prod --tier T3 --max-cost-usd 1.0
    uv run python -m pipeline.generate_draft --env dev --tier T3 --rerun
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import text

EnvName = Literal["dev", "prod"]
Tier = Literal["T1", "T2", "T3", "T4"]
Angle = Literal["opening", "reframe", "closing"]

WORKERS_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = WORKERS_DIR / "shared" / "prompts"

KB_RETRIEVAL_TOP_N = 5
VOYAGE_RATE_LIMIT_SLEEP_S = 22.0
VOYAGE_INITIAL_WARMUP_S = 0.0  # no warmup salvo que el run anterior haya
                                # cerrado < 20s atrás; ver `embed_documents.py`
USD_COST_CAP = 5.0
MAX_REGENERATION_RETRIES = 2
MAX_TOKENS = 1500

# Sonnet 4.6 fallback pricing (Anthropic 2026 aprox).
_SONNET_FALLBACK_USD_PER_MTOK = {"input": 3.0, "output": 15.0}

_STEP_BY_ANGLE: dict[Angle, int] = {"opening": 0, "reframe": 1, "closing": 2}

# ─── Validación post-generación (§10.3 — 4 reglas) ─────────────────────────

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]"
)
_PROMISE_RE = re.compile(
    r"\b(garantiz\w*|en\s+\d+\s+d[ií]as?|por\s+\d+\s*€|en\s+\d+\s+horas?|"
    r"\d+\s*€\b|precio\s+cerrado)",
    re.IGNORECASE,
)

logger = logging.getLogger("demin.generate_draft")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass(slots=True)
class PendingContact:
    contact_id: str
    company_id: str
    email: str
    email_type: str
    email_priority: int
    nombre_contacto: str | None
    cargo_contacto: str | None
    nif: str
    nombre_empresa: str
    tier: str
    research_data: dict[str, Any]


@dataclass(slots=True)
class GeneratedDraft:
    subject: str
    body: str
    razonamiento: str
    tokens_in: int
    tokens_out: int
    failed_validations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Result:
    contact_id: str
    nif: str
    success: bool
    draft: GeneratedDraft | None
    error: str | None


# ─── Funciones puras (testables sin red ni BD) ─────────────────────────────


def validate_post_generation(subject: str, body: str) -> list[str]:
    """Aplica las 4 reglas de §10.3 sobre el output del LLM. Devuelve lista
    de etiquetas de fallo (vacía = todo OK).

    Reglas:
        1. body entre 50 y 180 palabras.
        2. subject entre 3 y 8 palabras.
        3. ni body ni subject contienen emojis ni `!`.
        4. ni body ni subject prometen plazos/precios.
    """
    failures: list[str] = []
    body_words = len(body.split())
    if body_words < 50:
        failures.append(f"body_too_short:{body_words}")
    elif body_words > 180:
        failures.append(f"body_too_long:{body_words}")

    subject_words = len(subject.split())
    if subject_words < 3:
        failures.append(f"subject_too_short:{subject_words}")
    elif subject_words > 8:
        failures.append(f"subject_too_long:{subject_words}")

    if "!" in body or "!" in subject:
        failures.append("has_exclamation")
    if _EMOJI_RE.search(body) or _EMOJI_RE.search(subject):
        failures.append("has_emoji")

    if _PROMISE_RE.search(body) or _PROMISE_RE.search(subject):
        failures.append("has_promise")

    return failures


def kb_retrieval_query_for_company(item: PendingContact) -> str:
    """Compone el query string para retrieval. Concatena tipo_actividad +
    primer hook (si hay) — son las señales más concretas de qué hace la
    empresa para que el KB recupere chunks relevantes a su contexto.
    Fallback a nombre de empresa si research está incompleto."""
    rd = item.research_data
    actividad = rd.get("tipo_actividad_concreta") or ""
    hooks = rd.get("hooks_de_personalizacion") or []
    primer_hook = hooks[0] if isinstance(hooks, list) and hooks else ""
    parts = [actividad.strip(), primer_hook.strip() if isinstance(primer_hook, str) else ""]
    composed = " ".join(p for p in parts if p)
    return composed or item.nombre_empresa


def format_kb_chunks(chunks: list[dict[str, Any]]) -> str:
    """Compone los chunks recuperados en texto inyectable al `{kb_chunks}`
    del prompt. Si no hay chunks devuelve marcador explícito."""
    if not chunks:
        return "(KB sin chunks recuperados)"
    parts = []
    for i, c in enumerate(chunks, 1):
        cat = c.get("category", "?")
        titulo = c.get("titulo", "?")
        contenido = c.get("contenido", "")
        parts.append(f"--- chunk {i} (cat={cat}, doc={titulo}) ---\n{contenido}")
    return "\n\n".join(parts)


def parse_llm_json(raw: str) -> tuple[str, str, str]:
    """Devuelve `(subject, body, razonamiento)`. Tolerante a code fences
    (idéntico patrón a classify_descr y research_prospect). Lanza
    `json.JSONDecodeError` o `ValueError` si el output es inválido."""
    s = raw.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
    s = s.strip()

    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError(f"JSON no es objeto: {type(data).__name__}")

    subject = data.get("subject")
    body = data.get("body")
    razonamiento = data.get("razonamiento_breve", "")

    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject vacío o no string")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body vacío o no string")
    if not isinstance(razonamiento, str):
        razonamiento = ""

    return subject.strip(), body.strip(), razonamiento.strip()


def compose_user_vars(
    item: PendingContact,
    kb_chunks_text: str,
    correos_previos: str | None,
) -> dict[str, str]:
    """Compone el dict de variables que se sustituye en el user template.
    Garantiza strings (no None) para todas las claves — el render usa
    str.replace, así que un None aquí rompería."""
    rd = item.research_data
    actividad = rd.get("tipo_actividad_concreta") or ""
    obras = rd.get("tipo_obra_que_hacen") or []
    if isinstance(obras, list):
        obras_text = ", ".join(o for o in obras if isinstance(o, str)) or "(no identificado)"
    else:
        obras_text = "(no identificado)"
    proyectos = rd.get("proyectos_recientes") or []
    if isinstance(proyectos, list) and proyectos:
        proyectos_text = "\n".join(f"- {p}" for p in proyectos if isinstance(p, str))
    else:
        proyectos_text = "(no se han identificado)"
    hooks = rd.get("hooks_de_personalizacion") or []
    if isinstance(hooks, list) and hooks:
        hooks_text = "\n".join(f"- {h}" for h in hooks if isinstance(h, str))
    else:
        hooks_text = "(no se han identificado)"

    out = {
        "nombre": item.nombre_empresa,
        "email_type": item.email_type,
        "nombre_destinatario": item.nombre_contacto or "",
        "cargo_destinatario": item.cargo_contacto or "",
        "tipo_actividad_concreta": actividad,
        "tipo_obra_que_hacen": obras_text,
        "proyectos_recientes": proyectos_text,
        "hooks_de_personalizacion": hooks_text,
        "kb_chunks": kb_chunks_text,
    }
    if correos_previos is not None:
        out["correos_previos"] = correos_previos
    return out


def render_user_template(template: str, vars_: dict[str, str]) -> str:
    """Reemplaza placeholders sin usar str.format() — el template contiene
    literalmente `{"subject": ...}` del bloque output JSON que rompería
    str.format()."""
    out = template
    for k, v in vars_.items():
        out = out.replace("{" + k + "}", v)
    return out


def _load_prompt_for_angle(angle: Angle) -> tuple[str, str]:
    """Lee `generate_email_{angle}.md` y separa en (system, user_template).
    Mismo split que `_load_prompt` de classify_descr y research_prospect."""
    path = PROMPTS_DIR / f"generate_email_{angle}.md"
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("## System", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Prompt {path.name} sin '## System'")
    after = parts[1]
    sys_user = after.split("## User template", 1)
    if len(sys_user) != 2:
        raise RuntimeError(f"Prompt {path.name} sin '## User template'")
    return sys_user[0].strip(), sys_user[1].strip()


# ─── Acceso a BD + retrieval ────────────────────────────────────────────────


def fetch_pending_contacts(
    env: EnvName,
    tier: Tier,
    angle: Angle,
    limit: int | None,
    rerun: bool,
) -> list[PendingContact]:
    """Trae contacts cuyos companies tienen research OK + tier solicitado +
    no opt-out. Si `rerun=False` (default), excluye contacts que ya tienen
    message previo del mismo step_index (idempotencia)."""
    from shared.db import get_session  # noqa: PLC0415

    step_index = _STEP_BY_ANGLE[angle]
    sql = """
        SELECT
            ct.id   AS contact_id,
            ct.email,
            ct.email_type,
            ct.email_priority,
            ct.nombre AS contact_nombre,
            ct.cargo  AS contact_cargo,
            c.id    AS company_id,
            c.nif,
            c.nombre AS company_nombre,
            c.tier,
            c.research_data
        FROM contacts ct
        JOIN companies c ON c.id = ct.company_id
        WHERE c.ia_fit = 'fit'
          AND c.tier = :tier
          AND c.research_done_at IS NOT NULL
          AND NOT (c.research_data ? '_failed')
          AND ct.is_optout = false
    """
    if not rerun:
        sql += """
          AND NOT EXISTS (
            SELECT 1 FROM messages m
            WHERE m.contact_id = ct.id AND m.step_index = :step
          )
        """
    sql += " ORDER BY c.nif, ct.email_priority"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    with get_session(env) as s:
        rows = s.execute(text(sql), {"tier": tier, "step": step_index}).mappings().all()

    return [
        PendingContact(
            contact_id=str(r["contact_id"]),
            company_id=str(r["company_id"]),
            email=r["email"],
            email_type=r["email_type"],
            email_priority=r["email_priority"],
            nombre_contacto=r["contact_nombre"],
            cargo_contacto=r["contact_cargo"],
            nif=r["nif"],
            nombre_empresa=r["company_nombre"],
            tier=r["tier"],
            research_data=r["research_data"] or {},
        )
        for r in rows
    ]


def kb_retrieval(env: EnvName, query_text: str) -> list[dict[str, Any]]:
    """Top-5 chunks por cosine similarity. Mismo patrón que
    `smoke_kb_retrieval.py` (Sprint 1 paso 4)."""
    from shared.db import get_session  # noqa: PLC0415
    from shared.llm import embed  # noqa: PLC0415

    vec = embed([query_text], input_type="query")[0]
    vec_lit = "[" + ",".join(repr(float(v)) for v in vec) + "]"

    with get_session(env) as s:
        s.execute(text("set local ivfflat.probes = 10"))
        rows = s.execute(
            text(
                """
                SELECT c.contenido, d.category, d.titulo,
                       c.embedding <=> cast(:v as vector) AS dist
                FROM kb_chunks c
                JOIN kb_documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> cast(:v as vector)
                LIMIT :n
                """
            ),
            {"v": vec_lit, "n": KB_RETRIEVAL_TOP_N},
        ).mappings().all()
    return [dict(r) for r in rows]


def fetch_previous_messages(env: EnvName, contact_id: str) -> str:
    """Trae correos previos enviados/aprobados al contact, ordenados por
    step_index. Para reframe trae el opening; para closing, opening + reframe.
    Si no hay nada (caso típico en paso 6), devuelve marcador explícito."""
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT step_index, angle, subject, body
                FROM messages
                WHERE contact_id = cast(:cid as uuid)
                  AND status IN ('approved', 'scheduled', 'sent')
                ORDER BY step_index
                """
            ),
            {"cid": contact_id},
        ).mappings().all()

    if not rows:
        return "(no hay correos previos a este contacto)"
    parts = []
    for r in rows:
        parts.append(
            f"--- step {r['step_index']} ({r['angle']}) ---\n"
            f"Asunto: {r['subject']}\n"
            f"Cuerpo:\n{r['body']}"
        )
    return "\n\n".join(parts)


def insert_draft(
    env: EnvName,
    item: PendingContact,
    draft: GeneratedDraft,
    angle: Angle,
) -> str:
    """INSERT en messages. research_snapshot incluye `_failed_validations`
    si aplica para que el HITL lo vea."""
    from shared.db import get_session  # noqa: PLC0415

    snapshot = dict(item.research_data)
    if draft.failed_validations:
        snapshot["_failed_validations"] = draft.failed_validations

    cost_usd = (
        draft.tokens_in * _SONNET_FALLBACK_USD_PER_MTOK["input"]
        + draft.tokens_out * _SONNET_FALLBACK_USD_PER_MTOK["output"]
    ) / 1_000_000.0
    step_index = _STEP_BY_ANGLE[angle]

    with get_session(env) as s:
        row = s.execute(
            text(
                """
                INSERT INTO messages
                    (contact_id, step_index, angle, subject, body, status,
                     research_snapshot, generation_cost_usd)
                VALUES
                    (cast(:cid as uuid), :step, :angle, :subj, :body, 'drafted',
                     cast(:rs as jsonb), :cost)
                RETURNING id
                """
            ),
            {
                "cid": item.contact_id,
                "step": step_index,
                "angle": angle,
                "subj": draft.subject,
                "body": draft.body,
                "rs": json.dumps(snapshot, ensure_ascii=False),
                "cost": cost_usd,
            },
        ).mappings().one()
    return str(row["id"])


# ─── Orquestación por contact (red + LLM, sin commits BD) ──────────────────


def process_one_contact(
    env: EnvName,
    item: PendingContact,
    angle: Angle,
    system: str,
    user_template: str,
) -> Result:
    """Genera draft para un contact: KB retrieval → compose prompt → LLM →
    valida → si falla, hasta 2 reintentos LLM. NO lanza — captura excepciones
    en `Result.error`. Si tras retries el draft sigue con validations
    fallidas, devuelve Result con `success=True` y `failed_validations`
    rellenas (entra al HITL marcado para que Gonzalo decida)."""
    try:
        query = kb_retrieval_query_for_company(item)
        chunks = kb_retrieval(env, query)
        kb_chunks_text = format_kb_chunks(chunks)
    except Exception as e:
        return Result(
            contact_id=item.contact_id, nif=item.nif, success=False, draft=None,
            error=f"kb_retrieval_failed: {type(e).__name__}: {str(e)[:150]}",
        )

    if angle == "opening":
        correos_previos: str | None = None
    else:
        try:
            correos_previos = fetch_previous_messages(env, item.contact_id)
        except Exception as e:
            return Result(
                contact_id=item.contact_id, nif=item.nif, success=False, draft=None,
                error=f"fetch_previous_failed: {type(e).__name__}: {str(e)[:150]}",
            )

    user_vars = compose_user_vars(item, kb_chunks_text, correos_previos)
    user = render_user_template(user_template, user_vars)

    from shared.llm import call_llm  # noqa: PLC0415

    last_failures: list[str] = []
    last_subject = ""
    last_body = ""
    last_razonamiento = ""
    last_tokens_in = 0
    last_tokens_out = 0

    for attempt in range(MAX_REGENERATION_RETRIES + 1):
        try:
            raw, meta = call_llm(
                task="generate_draft",
                system=system,
                user=user,
                max_tokens=MAX_TOKENS,
            )
        except Exception as e:
            return Result(
                contact_id=item.contact_id, nif=item.nif, success=False, draft=None,
                error=f"llm_error attempt={attempt}: {type(e).__name__}: {str(e)[:150]}",
            )
        last_tokens_in = meta["tokens_in"]
        last_tokens_out = meta["tokens_out"]

        try:
            subject, body, razonamiento = parse_llm_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            last_failures = [f"json_parse:{str(e)[:60]}"]
            if attempt < MAX_REGENERATION_RETRIES:
                continue
            return Result(
                contact_id=item.contact_id, nif=item.nif, success=False, draft=None,
                error=f"json_parse tras {attempt + 1} intentos: {str(e)[:120]}",
            )

        last_subject, last_body, last_razonamiento = subject, body, razonamiento
        last_failures = validate_post_generation(subject, body)
        if not last_failures:
            return Result(
                contact_id=item.contact_id, nif=item.nif, success=True,
                draft=GeneratedDraft(
                    subject=subject, body=body, razonamiento=razonamiento,
                    tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                ),
                error=None,
            )

    # Tras retries, las validaciones siguen fallando → entrega con marca.
    return Result(
        contact_id=item.contact_id, nif=item.nif, success=True,
        draft=GeneratedDraft(
            subject=last_subject, body=last_body, razonamiento=last_razonamiento,
            tokens_in=last_tokens_in, tokens_out=last_tokens_out,
            failed_validations=last_failures,
        ),
        error=None,
    )


# ─── CLI ───────────────────────────────────────────────────────────────────


def _estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (
        tokens_in * _SONNET_FALLBACK_USD_PER_MTOK["input"]
        + tokens_out * _SONNET_FALLBACK_USD_PER_MTOK["output"]
    ) / 1_000_000.0


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="generate_draft — redacta drafts personalizados con KB+LLM (Sprint 4 paso 6)"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--tier", choices=("T1", "T2", "T3", "T4"), required=True)
    p.add_argument("--angle", choices=("opening", "reframe", "closing"), default="opening")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--max-cost-usd", type=float, default=USD_COST_CAP)
    p.add_argument("--rerun", action="store_true",
                   help="Ignora idempotencia — genera draft aunque ya exista message del mismo step_index.")
    p.add_argument("--no-voyage-sleep", action="store_true",
                   help="Skipea el sleep entre embeds Voyage (solo si la cuenta tiene payment method).")
    args = p.parse_args(argv)
    env: EnvName = args.env
    tier: Tier = args.tier
    angle: Angle = args.angle

    print("=" * 76)
    print(
        f"generate_draft  env={env}  tier={tier}  angle={angle}  "
        f"limit={args.limit}  max_cost_usd={args.max_cost_usd}  rerun={args.rerun}"
    )
    print("=" * 76)

    system, user_template = _load_prompt_for_angle(angle)
    print(f"[prompt] cargado generate_email_{angle}.md: "
          f"system={len(system)} chars, user_template={len(user_template)} chars")

    pending = fetch_pending_contacts(env, tier, angle, args.limit, args.rerun)
    if not pending:
        print("No hay contacts pendientes. Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} contacts a procesar")

    counts = {"ok": 0, "ok_with_validation_warnings": 0, "failed": 0}
    failure_breakdown: dict[str, int] = {}
    total_tok_in = 0
    total_tok_out = 0
    cost_alarm = False

    t0 = time.monotonic()

    for i, item in enumerate(pending, 1):
        cost_so_far = _estimate_cost_usd(total_tok_in, total_tok_out)
        if cost_so_far > args.max_cost_usd and not cost_alarm:
            cost_alarm = True
            print(f"PARADA: coste {cost_so_far:.2f} USD supera cap {args.max_cost_usd} USD")
            break

        # Voyage rate-limit sleep entre contacts (cada uno hace 1 embed query).
        # El primero salta el sleep — es la primera llamada del run.
        if i > 1 and not args.no_voyage_sleep:
            time.sleep(VOYAGE_RATE_LIMIT_SLEEP_S)

        try:
            r = process_one_contact(env, item, angle, system, user_template)
        except Exception as e:
            counts["failed"] += 1
            print(f"  [{i:>3}/{len(pending)}] {item.nif} EXCEPCION INESPERADA: {type(e).__name__}: {e}")
            continue

        total_tok_in += (r.draft.tokens_in if r.draft else 0)
        total_tok_out += (r.draft.tokens_out if r.draft else 0)

        if not r.success:
            counts["failed"] += 1
            err_label = (r.error or "unknown").split(":")[0]
            failure_breakdown[err_label] = failure_breakdown.get(err_label, 0) + 1
            print(f"  [{i:>3}/{len(pending)}] {item.nif} {item.email[:40]:<40}  FAILED  {r.error}")
            continue

        assert r.draft is not None
        try:
            mid = insert_draft(env, item, r.draft, angle)
        except Exception as e:
            counts["failed"] += 1
            print(f"  [{i:>3}/{len(pending)}] {item.nif} insert_draft: {type(e).__name__}: {e}")
            continue

        if r.draft.failed_validations:
            counts["ok_with_validation_warnings"] += 1
            mark = f"⚠ {','.join(r.draft.failed_validations)}"
        else:
            counts["ok"] += 1
            mark = "OK"
        print(
            f"  [{i:>3}/{len(pending)}] {item.nif} {item.email[:40]:<40}  {mark}  "
            f"tok={r.draft.tokens_in}+{r.draft.tokens_out}  msg={mid[:8]}"
        )

    elapsed = time.monotonic() - t0
    cost_total = _estimate_cost_usd(total_tok_in, total_tok_out)
    n_done = counts["ok"] + counts["ok_with_validation_warnings"] + counts["failed"]

    print()
    print("=" * 76)
    print(f"FIN generate_draft  env={env}  tier={tier}  angle={angle}  elapsed={elapsed:.1f}s")
    print(f"  procesados:                  {n_done} / {len(pending)}")
    print(f"  ok validados:                {counts['ok']}  ({_pct(counts['ok'], n_done)})")
    print(f"  ok con warnings (HITL ve):   {counts['ok_with_validation_warnings']}")
    print(f"  failed:                      {counts['failed']}")
    if failure_breakdown:
        print(f"  failure breakdown:           {failure_breakdown}")
    print(f"  tokens: in={total_tok_in}  out={total_tok_out}")
    print(f"  coste estimado USD: {cost_total:.4f}  (cap {args.max_cost_usd})")
    print("=" * 76)

    if cost_alarm:
        return 2
    if counts["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
