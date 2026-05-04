"""Smoke E2E del worker `ingest_sabi.py` contra demin-dev.

Pipeline:
  1) wipe inicial de `companies` en dev (si tabla no esta vacia, abortamos:
     no queremos sobrescribir trabajo previo accidentalmente).
  2) ejecutamos ingest -> primera carga.
  3) capturamos distribucion por tier + total.
  4) validamos contra plan §8.2 con tolerancia ±20%.
  5) ejecutamos ingest una segunda vez (idempotencia).
  6) capturamos distribucion otra vez y verificamos que counts NO cambian.

Veredicto:
  VERDE     - ingest limpio, distribucion dentro de tolerancia, idempotente.
  AMARILLO  - ingest limpio pero algun tier se desvia >20%; humano decide.
  ROJO      - error en parse/upsert, o counts cambian al re-ejecutar.

ENV=dev hardcodeado. Si ROJO/AMARILLO: NO se aplica ingest a prod.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("ENV", "dev")

WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from sqlalchemy import text  # noqa: E402

from pipeline.ingest_sabi import (  # noqa: E402
    EXCEL_PATH,
    dedup_by_nif,
    parse_excel,
    upsert_companies,
    verify_distribution,
)
from shared.db import get_session  # noqa: E402

SEP = "=" * 76
ENV = "dev"

# Esperado segun plan §8.2 (pre-dedup; el plan estima estos numeros leyendo
# el export inicial). Tras dedup acordada (Leccion 18) los numeros reales
# pueden variar; tolerancia +-20% es generosa para no falsear el smoke.
EXPECTED = {"T1": 455, "T2": 173, "T3": 252, "T4": 857}
TOLERANCE = 0.20  # 20%


def _within_tolerance(actual: int, expected: int, tol: float) -> bool:
    """True si |actual - expected| / expected <= tol."""
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected <= tol


def _wipe_companies_or_abort() -> int:
    """Vacia `companies` en dev SOLO si esta vacia o solo tiene filas
    insertadas por un smoke previo (sin ia_fit ni research_data). Si hay
    trabajo real (research_done_at != NULL) abortamos para no perderlo.
    """
    with get_session(ENV) as s:
        n = s.execute(text("select count(*) from companies")).scalar() or 0
        if n == 0:
            return 0
        with_research = s.execute(
            text(
                "select count(*) from companies "
                "where research_done_at is not null or ia_fit != 'pendiente'"
            )
        ).scalar() or 0
        if with_research > 0:
            raise RuntimeError(
                f"companies tiene {with_research} filas con research/ia_fit ya calculado. "
                "El smoke aborta para no perder ese trabajo."
            )
        s.execute(text("delete from companies"))
        return int(n)


def _print_dist(label: str, dist: dict[str, int]) -> None:
    total = sum(dist.values())
    print(f"  {label}: total={total}")
    for t in ("T1", "T2", "T3", "T4", "descartado"):
        n = dist.get(t, 0)
        pct = (n / total * 100) if total else 0
        exp = EXPECTED.get(t)
        marker = ""
        if exp is not None:
            ok = _within_tolerance(n, exp, TOLERANCE)
            diff = (n - exp) / exp * 100 if exp else 0
            marker = f"  [esperado~{exp}, diff {diff:+.1f}%, {'OK' if ok else 'FUERA'}]"
        print(f"    {t:<11} {n:>5}  ({pct:5.1f}%){marker}")


def main() -> int:
    t0 = time.monotonic()
    print(SEP)
    print(f"smoke_ingest_sabi  env={ENV}")
    print(SEP)

    # 1) wipe (con guardas)
    print("[1] wipe `companies` en dev (con guardas)")
    wiped = _wipe_companies_or_abort()
    print(f"    {wiped} filas borradas")

    # 2) primera carga
    print("[2] primera carga: parse + dedup + upsert")
    rows, errs = parse_excel(EXCEL_PATH)
    if errs:
        print(f"ROJO: parse devolvio {len(errs)} errores")
        for e in errs[:10]:
            print(f"   - {e}")
        return 2
    deduped, _ = dedup_by_nif(rows)
    n1 = upsert_companies(ENV, deduped)
    print(f"    upsert: {n1} filas")
    dist1 = verify_distribution(ENV)
    print()
    _print_dist("distribucion tras primera carga", dist1)

    # 3) validacion vs plan §8.2 con tolerancia
    print()
    print("[3] validacion contra plan §8.2 (tolerancia ±20%)")
    out_of_tol: list[str] = []
    for tier, expected in EXPECTED.items():
        actual = dist1.get(tier, 0)
        if not _within_tolerance(actual, expected, TOLERANCE):
            out_of_tol.append(f"{tier}: actual={actual} esperado~{expected}")
    if out_of_tol:
        print("AMARILLO: tiers fuera de tolerancia:")
        for o in out_of_tol:
            print(f"    {o}")
        print("PARADA: no se aplica a prod hasta revisar.")
        return 3

    # 4) segunda carga = idempotencia
    print()
    print("[4] segunda carga (idempotencia)")
    n2 = upsert_companies(ENV, deduped)
    print(f"    upsert: {n2} filas")
    dist2 = verify_distribution(ENV)

    if dist1 != dist2:
        print("ROJO: distribucion cambio al re-ejecutar")
        print(f"  dist1={dist1}")
        print(f"  dist2={dist2}")
        return 4

    total_db = sum(dist2.values())
    if total_db != len(deduped):
        print(f"ROJO: count en BD ({total_db}) != filas dedup ({len(deduped)})")
        return 5

    # 5) chequeo extra: nº de NIFs unicos en BD = filas en BD (constraint
    # unique deberia garantizarlo; verificacion barata)
    with get_session(ENV) as s:
        unique_nifs = s.execute(
            text("select count(distinct nif) from companies")
        ).scalar()
    if unique_nifs != total_db:
        print(f"ROJO: NIFs unicos ({unique_nifs}) != total ({total_db})")
        return 6

    print()
    print(SEP)
    print(f"VERDE: ingest_sabi smoke OK en {time.monotonic() - t0:.1f}s")
    print(f"  - {total_db} filas en companies (dev)")
    print(f"  - distribucion estable en re-ejecucion (idempotente)")
    print(f"  - todos los tiers dentro de ±20% del plan §8.2")
    print(SEP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
