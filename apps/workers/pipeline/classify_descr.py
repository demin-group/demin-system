"""Filtro IA por descripción de actividad — §8.3 todo.md.

Itera empresas con `tier in (T1,T2,T3,T4)` e `ia_fit='pendiente'`. Llama a
Claude (Haiku, vía MODEL_FOR_TASK) con el prompt versionado en
`shared/prompts/classify_fit.md` y actualiza `companies.ia_fit` +
`companies.ia_fit_reason`.

Pipeline:
  1. fetch_pending: SELECT nif, nombre, descripcion (orden estable por NIF).
  2. ThreadPoolExecutor con N workers paralelos (default 8).
  3. Por cada empresa: classify_one() → (fit, reason) o fallback ia_fit='dudoso'
     con reason explicando el fallo (LLM no parsea, fit fuera del enum, error de
     red tras retries de tenacity).
  4. UPDATE batch cada `BATCH_SIZE` procesadas (commit incremental — si el proceso
     muere, no se pierde lo ya clasificado).
  5. Cap de coste estimado: si supera USD_COST_CAP, parar y reportar.

CLI:
    cd apps/workers
    uv run python -m pipeline.classify_descr --env dev
    uv run python -m pipeline.classify_descr --env dev --limit 50
    uv run python -m pipeline.classify_descr --env dev --workers 4
    uv run python -m pipeline.classify_descr --env prod --reclassify

Idempotente: el filtro `ia_fit='pendiente'` por defecto. `--reclassify` ignora
el filtro y procesa cualquier accionable, sobrescribiendo decisiones previas.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from sqlalchemy import text

EnvName = Literal["dev", "prod"]

WORKERS_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = WORKERS_DIR / "shared" / "prompts" / "classify_fit.md"

# Pricing local (fallback) para alarma de coste mid-batch. NO se rellena
# `shared/llm.PRICING_USD_PER_MTOKENS` para no contaminar el log oficial; la
# cifra real (cuando se actualice esa tabla) reemplazará a esta. Cifras
# aproximadas de claude-haiku-4-5 (publicadas por Anthropic):
#   input  ~$1 por 1M tokens
#   output ~$5 por 1M tokens
# Solo se usa para decidir si parar el batch antes de superar USD_COST_CAP.
_HAIKU_FALLBACK_USD_PER_MTOK = {"input": 1.0, "output": 5.0}

USD_COST_CAP = 5.0
"""Cap de coste estimado del run completo. Si en mid-batch lo superamos,
paramos y reportamos. Plan §8.3 estima ~$2 para 1.733 empresas; el cap a $5
es 2.5× margen para cubrir descripciones inesperadamente largas."""

BATCH_SIZE = 25
"""Tamaño del batch para UPDATE + commit incremental + log de progreso."""

logger = logging.getLogger("demin.classify_descr")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

_VALID_FITS = {"fit", "no_fit", "dudoso"}


@dataclass(slots=True)
class Pending:
    nif: str
    nombre: str
    descripcion: str | None


@dataclass(slots=True)
class Result:
    nif: str
    fit: str
    reason: str
    tokens_in: int
    tokens_out: int
    error: str | None = None  # llenado si fallback usado


def _load_prompt() -> tuple[str, str]:
    """Lee `classify_fit.md` y separa en (system, user_template).

    Convención del fichero: dos secciones marcadas con `## System` y `## User template`
    (ver `apps/workers/shared/prompts/README.md`).
    """
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split("## System", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Prompt {PROMPT_PATH.name} no contiene '## System'")
    after_system = parts[1]
    sys_user = after_system.split("## User template", 1)
    if len(sys_user) != 2:
        raise RuntimeError(f"Prompt {PROMPT_PATH.name} no contiene '## User template'")
    system = sys_user[0].strip()
    user_template = sys_user[1].strip()
    return system, user_template


def _strip_codefences(s: str) -> str:
    """Si Haiku envuelve la respuesta en ```json ... ```, devuelve el contenido."""
    s = s.strip()
    if s.startswith("```"):
        # quitar primera linea de fence
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


def _parse_llm_json(raw_text: str) -> tuple[str, str]:
    """Devuelve `(fit, reason)`. Lanza ValueError si la respuesta es invalida."""
    cleaned = _strip_codefences(raw_text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError(f"JSON no es objeto: {type(data).__name__}")
    fit = data.get("fit")
    reason = data.get("reason", "")
    if fit not in _VALID_FITS:
        raise ValueError(f"fit inválido: {fit!r} (esperado uno de {sorted(_VALID_FITS)})")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason vacío o no string")
    return fit, reason.strip()


def classify_one(item: Pending, system: str, user_template: str) -> Result:
    """Llama a Claude para una empresa. Captura cualquier excepción y devuelve
    `Result` con `ia_fit='dudoso'` + `error` explicando el fallo. Nunca lanza.
    """
    from shared.llm import call_llm  # noqa: PLC0415  (lazy: evita cargar settings al import)

    descripcion = (item.descripcion or "").strip() or "(sin descripción)"
    # Reemplazo manual (no .format()): el prompt contiene literal {"fit": ...} que
    # str.format() malinterpreta como placeholder.
    user = user_template.replace("{nombre}", item.nombre).replace(
        "{descripcion}", descripcion
    )

    try:
        text_out, meta = call_llm(
            task="classify_descr",
            system=system,
            user=user,
            max_tokens=200,
            response_format="text",  # parsing tolerante a code fences en _parse_llm_json
        )
        fit, reason = _parse_llm_json(text_out)
        return Result(
            nif=item.nif,
            fit=fit,
            reason=reason,
            tokens_in=meta["tokens_in"],
            tokens_out=meta["tokens_out"],
        )
    except json.JSONDecodeError as e:
        return Result(
            nif=item.nif,
            fit="dudoso",
            reason=f"LLM output no parsea JSON: {str(e)[:80]}",
            tokens_in=0,
            tokens_out=0,
            error="json_parse",
        )
    except ValueError as e:
        return Result(
            nif=item.nif,
            fit="dudoso",
            reason=f"LLM output inválido: {str(e)[:120]}",
            tokens_in=0,
            tokens_out=0,
            error="schema",
        )
    except Exception as e:
        # Errores tras retries de tenacity (rate limit persistente, 5xx, network).
        return Result(
            nif=item.nif,
            fit="dudoso",
            reason=f"LLM error: {type(e).__name__}: {str(e)[:100]}",
            tokens_in=0,
            tokens_out=0,
            error="api",
        )


def fetch_pending(env: EnvName, limit: int | None, reclassify: bool) -> list[Pending]:
    """Trae empresas a clasificar. Orden estable por NIF para idempotencia."""
    from shared.db import get_session  # noqa: PLC0415

    where = "tier in ('T1','T2','T3','T4')"
    if not reclassify:
        where += " and ia_fit = 'pendiente'"
    sql = f"select nif, nombre, descripcion from companies where {where} order by nif"
    if limit is not None:
        sql += f" limit {int(limit)}"

    with get_session(env) as s:
        rows = s.execute(text(sql)).all()
    return [Pending(nif=r[0], nombre=r[1], descripcion=r[2]) for r in rows]


_UPDATE_SQL = text(
    "update companies set ia_fit = :fit, ia_fit_reason = :reason where nif = :nif"
)


def write_results(env: EnvName, results: list[Result]) -> int:
    """UPDATE en batch. Devuelve nº de filas escritas."""
    from shared.db import get_session  # noqa: PLC0415

    if not results:
        return 0
    payload = [{"nif": r.nif, "fit": r.fit, "reason": r.reason} for r in results]
    with get_session(env) as s:
        s.execute(_UPDATE_SQL, payload)
    return len(payload)


def _estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (
        tokens_in * _HAIKU_FALLBACK_USD_PER_MTOK["input"]
        + tokens_out * _HAIKU_FALLBACK_USD_PER_MTOK["output"]
    ) / 1_000_000.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="classify_descr — filtro IA Haiku sobre companies")
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--limit", type=int, default=None,
                   help="Procesar solo los primeros N (orden por NIF). Útil para smoke.")
    p.add_argument("--reclassify", action="store_true",
                   help="Ignorar filtro ia_fit='pendiente'. Reclasifica accionables ya etiquetadas.")
    p.add_argument("--workers", type=int, default=8,
                   help="Threads paralelos para llamadas LLM (default 8).")
    args = p.parse_args(argv)
    env: EnvName = args.env  # type: ignore[assignment]

    print("=" * 76)
    print(
        f"classify_descr  env={env}  limit={args.limit}  "
        f"reclassify={args.reclassify}  workers={args.workers}"
    )
    print("=" * 76)

    system, user_template = _load_prompt()
    print(f"[prompt] cargado de {PROMPT_PATH.name}: "
          f"system={len(system)} chars, user_template={len(user_template)} chars")

    pending = fetch_pending(env, args.limit, args.reclassify)
    if not pending:
        print("No hay empresas pendientes. Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} empresas a clasificar")

    t0 = time.monotonic()
    results: list[Result] = []
    counts = {"fit": 0, "no_fit": 0, "dudoso": 0}
    error_counts = {"json_parse": 0, "schema": 0, "api": 0}
    total_tok_in = 0
    total_tok_out = 0
    write_buffer: list[Result] = []
    written = 0
    lock = Lock()  # serializa actualización de contadores compartidos
    cost_alarm_triggered = False

    def _process_done(r: Result) -> None:
        nonlocal total_tok_in, total_tok_out, written, cost_alarm_triggered
        with lock:
            results.append(r)
            counts[r.fit] += 1
            total_tok_in += r.tokens_in
            total_tok_out += r.tokens_out
            if r.error:
                error_counts[r.error] += 1
            write_buffer.append(r)

            if len(write_buffer) >= BATCH_SIZE:
                n = write_results(env, write_buffer)
                written += n
                write_buffer.clear()
                cost = _estimate_cost_usd(total_tok_in, total_tok_out)
                processed = len(results)
                print(
                    f"  [{processed:>4}/{len(pending)}]  "
                    f"fit={counts['fit']:>3}  no_fit={counts['no_fit']:>3}  "
                    f"dudoso={counts['dudoso']:>3}  "
                    f"errs={sum(error_counts.values()):>2}  "
                    f"tok={total_tok_in}+{total_tok_out}  est_usd={cost:.3f}"
                )
                if cost > USD_COST_CAP and not cost_alarm_triggered:
                    cost_alarm_triggered = True
                    print(f"PARADA: coste estimado {cost:.2f} USD supera cap {USD_COST_CAP} USD")

    print(f"[run] {args.workers} threads, batch_size={BATCH_SIZE}")
    print()

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(classify_one, item, system, user_template): item for item in pending}
            for fut in as_completed(futures):
                if cost_alarm_triggered:
                    # Cancelar las que aun no han empezado.
                    for f in futures:
                        f.cancel()
                    break
                try:
                    r = fut.result()
                    _process_done(r)
                except Exception as e:
                    item = futures[fut]
                    print(f"  [worker error] nif={item.nif}: {type(e).__name__}: {e}")
    finally:
        # Flush del buffer final (lo que no haya alcanzado BATCH_SIZE).
        if write_buffer:
            n = write_results(env, write_buffer)
            written += n
            write_buffer.clear()

    elapsed = time.monotonic() - t0
    final_cost = _estimate_cost_usd(total_tok_in, total_tok_out)

    print()
    print("=" * 76)
    print(f"FIN classify_descr  env={env}  elapsed={elapsed:.1f}s")
    print(f"  procesadas: {len(results)} / {len(pending)}")
    print(f"  fit:        {counts['fit']}  ({_pct(counts['fit'], len(results))})")
    print(f"  no_fit:     {counts['no_fit']}  ({_pct(counts['no_fit'], len(results))})")
    print(f"  dudoso:     {counts['dudoso']}  ({_pct(counts['dudoso'], len(results))})")
    print(f"  errores fallback: json_parse={error_counts['json_parse']}, "
          f"schema={error_counts['schema']}, api={error_counts['api']}")
    print(f"  tokens: in={total_tok_in}  out={total_tok_out}")
    print(f"  coste estimado USD: {final_cost:.4f}")
    print(f"  filas escritas: {written}")
    print("=" * 76)

    if cost_alarm_triggered:
        return 2
    return 0


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


if __name__ == "__main__":
    sys.exit(main())
