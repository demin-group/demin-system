"""Smoke retrieval del KB embebido contra demin-dev.

Valida que el RAG devuelve chunks **utiles** para responder cada query, no
que coincida con una categoria preasignada por el desarrollador. El criterio
se calibra leyendo lo que el KB realmente contiene (los 6 docs cargados en
sesiones 1+2 con Gonzalo).

ENV=dev hardcodeado. Por cada query:
  1) embeda con Voyage usando ``input_type="query"`` (asimetrico vs los
     chunks indexados con ``"document"``).
  2) recupera top-3 chunks via ``embedding <=> query`` (cosine).
  3) cuenta cuantas ``signals`` (palabras-clave contextuales que cualquier
     respuesta util contendria) aparecen en el contenido del chunk.
  4) imprime preview de cada top-1 + signals matched, para que un humano
     pueda auditar la utilidad sin abrir la BD.

Veredicto:
  VERDE     - los 3 top-1 contienen al menos ``MIN_SIGNALS`` signals.
              El RAG entrega contexto util en la primera posicion.
  AMARILLO  - algun top-1 falla, pero el top-3 contiene un chunk con
              suficientes signals y las distancias top-1 son <0.85
              (el RAG esta cerca, queda margen de afinado).
  ROJO      - ninguna posicion top-3 cubre alguna query, o las 3
              distancias top-1 son >=0.9 (el RAG no discrimina).

Si AMARILLO o ROJO: PARA y NO se aplica embed_documents a prod.
"""
from __future__ import annotations

import os
import sys
import time
import unicodedata
from pathlib import Path

os.environ.setdefault("ENV", "dev")

WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from sqlalchemy import text  # noqa: E402

from shared.config import settings  # noqa: E402
from shared.db import get_session  # noqa: E402
from shared.llm import embed  # noqa: E402

SEP = "=" * 76
SUBSEP = "-" * 76

# Umbral de signals que un chunk debe contener para considerarse util.
MIN_SIGNALS = 2

# Distancia maxima del top-1 para considerar AMARILLO en lugar de ROJO.
DIST_AMARILLO = 0.85

# Distancia minima del top-1 a partir de la cual se declara ROJO directo.
DIST_ROJO = 0.9


# Cada query trae:
#   - q: la query a embedar.
#   - needs: que necesita responder un comercial con esta query, en una frase.
#   - signals: palabras-clave (lowercased, sin acentos) que cualquier chunk
#     util para responder esta query deberia contener. Se han escogido
#     leyendo los 6 documentos del KB cargados en sesiones 1+2 con Gonzalo,
#     no a priori. Mezcla:
#       - terminos especificos del dominio (constructora, vaciado),
#       - nombres geograficos reales del KB (Chamberi, Malasana...),
#       - cifras concretas que solo aparecen en docs operativos
#         (5.000, 100.000, 15%),
#       - prefijos para tolerar variaciones (peque -> pequeña/pequeño).
QUERIES: list[dict[str, object]] = [
    {
        "q": "constructora pequena Madrid reformas integrales",
        "needs": (
            "El comercial respondera con tipo de cliente que encaja "
            "(constructora pequena-mediana), zona, y por que DEMIN encaja "
            "con su modelo de trabajo."
        ),
        "signals": [
            "constructora",
            "peque",
            "mediana",
            "madrid",
            "chamberi",
            "malasana",
            "bernabeu",
            "atocha",
            "rotacion",
            "directo",
        ],
    },
    {
        "q": "que precio tiene una demolicion de 200 metros cuadrados",
        "needs": (
            "El comercial respondera con plazos tipicos por m2, rango de "
            "presupuesto, y procedimiento para presupuestar sin visita."
        ),
        "signals": [
            "presupuesto",
            "precio",
            "m2",
            "metros",
            "plazo",
            "5.000",
            "100.000",
            "match",
            "descuento",
            "vaciado",
            "medicion",
        ],
    },
    {
        "q": "como coordino con arquitectos las obras",
        "needs": (
            "El comercial respondera con el proceso de ejecucion de DEMIN, "
            "limites del scope (no instalaciones), y trato directo con "
            "responsable unico."
        ),
        "signals": [
            "coordin",
            "gremio",
            "directo",
            "responsable",
            "plan",
            "proceso",
            "preparac",
            "limpieza",
            "fase",
            "vaciado",
        ],
    },
]


def _norm(s: str) -> str:
    """Lower + sin acentos. Robusto para comparar signals contra contenido."""
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def _count_signals(content: str, signals: list[str]) -> tuple[int, list[str]]:
    norm_content = _norm(content)
    matched = [s for s in signals if _norm(s) in norm_content]
    return len(matched), matched


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


def main() -> int:
    if settings.SUPABASE_ENV != "dev":
        print(f"ABORT: SUPABASE_ENV={settings.SUPABASE_ENV!r}, smoke solo dev.")
        return 1

    # Warmup defensivo Voyage free tier 3 RPM.
    print("warmup sleep 22s (Voyage free tier 3 RPM)")
    time.sleep(22)

    summary: list[dict[str, object]] = []

    for q_idx, q in enumerate(QUERIES):
        if q_idx > 0:
            time.sleep(22)

        query = q["q"]
        needs = q["needs"]
        signals = q["signals"]
        assert isinstance(query, str)
        assert isinstance(signals, list)

        print(SEP)
        print(f"query: {query!r}")
        print(f"necesidad: {needs}")
        print(f"signals esperadas ({len(signals)}): {signals}")
        print()

        # input_type="query" para la asimetria correcta vs los chunks
        # indexados con input_type="document" en embed_documents.
        vec = embed([query], input_type="query")[0]
        vec_lit = _vec_literal(vec)

        with get_session("dev") as s:
            s.execute(text("set local ivfflat.probes = 10"))
            rows = s.execute(
                text(
                    """
                    select
                        c.id,
                        c.contenido,
                        c.embedding <=> cast(:v as vector) as dist,
                        d.category,
                        d.titulo
                    from kb_chunks c
                    join kb_documents d on d.id = c.document_id
                    order by c.embedding <=> cast(:v as vector)
                    limit 3
                    """
                ),
                {"v": vec_lit},
            ).mappings().all()

        if not rows:
            print("  ABORT: 0 rows recuperados — index vacio?")
            return 2

        print("  top-3 chunks recuperados:")
        chunks_summary = []
        for i, r in enumerate(rows):
            n_sig, matched = _count_signals(r["contenido"], signals)
            preview = r["contenido"].replace("\n", " ").strip()
            preview = " ".join(preview.split())  # colapsa espacios
            print(SUBSEP)
            print(
                f"  [{i + 1}] dist={float(r['dist']):.4f}  "
                f"cat={r['category']:14s} titulo={r['titulo'][:50]!r}"
            )
            print(f"      signals ({n_sig}/{len(signals)}): {matched}")
            print(f"      preview: {preview[:400]!r}")
            chunks_summary.append(
                {
                    "pos": i + 1,
                    "cat": r["category"],
                    "dist": float(r["dist"]),
                    "n_signals": n_sig,
                    "matched": matched,
                }
            )

        top1 = chunks_summary[0]
        top1_useful = top1["n_signals"] >= MIN_SIGNALS
        any_useful_in_top3 = any(c["n_signals"] >= MIN_SIGNALS for c in chunks_summary)
        print(SUBSEP)
        print(
            f"  -> top-1 utilidad: "
            f"{'OK' if top1_useful else 'FAIL'} "
            f"({top1['n_signals']} signals "
            f"{'>= ' if top1_useful else '< '}{MIN_SIGNALS} threshold)"
        )
        if not top1_useful and any_useful_in_top3:
            print(
                f"  -> top-3 sin embargo CONTIENE algun chunk util "
                f"(positions con >={MIN_SIGNALS} signals)"
            )

        summary.append(
            {
                "q": query,
                "top1": top1,
                "top1_useful": top1_useful,
                "any_useful_in_top3": any_useful_in_top3,
            }
        )

    # Resumen + veredicto
    print(SEP)
    print("RESUMEN:")
    for i, s in enumerate(summary):
        t = s["top1"]
        print(
            f"  q{i + 1}: top-1 cat={t['cat']:14s} dist={t['dist']:.4f}  "
            f"signals={t['n_signals']:>2}  "
            f"{'OK' if s['top1_useful'] else 'FAIL'}"
        )

    n_top1_ok = sum(1 for s in summary if s["top1_useful"])
    all_top1_dist_high = all(s["top1"]["dist"] >= DIST_ROJO for s in summary)
    all_have_useful_in_top3 = all(s["any_useful_in_top3"] for s in summary)
    all_top1_dist_low = all(s["top1"]["dist"] < DIST_AMARILLO for s in summary)

    print(SEP)
    if n_top1_ok == len(summary):
        print(
            f"VEREDICTO: VERDE - los {n_top1_ok}/{len(summary)} top-1 contienen "
            f">= {MIN_SIGNALS} signals contextuales"
        )
        return 0

    dist_str = [f"{s['top1']['dist']:.3f}" for s in summary]

    if all_top1_dist_high or not all_have_useful_in_top3:
        print(
            f"VEREDICTO: ROJO - {n_top1_ok}/{len(summary)} top-1 OK; "
            f"distancias top-1: {dist_str}; "
            f"hay top-3 utiles: {all_have_useful_in_top3}"
        )
        return 2

    if all_top1_dist_low:
        print(
            f"VEREDICTO: AMARILLO - {n_top1_ok}/{len(summary)} top-1 OK; "
            f"distancias razonables (<{DIST_AMARILLO}); top-3 contiene chunks "
            f"utiles para las {len(summary)} queries"
        )
        return 1

    print(
        f"VEREDICTO: AMARILLO - {n_top1_ok}/{len(summary)} top-1 OK; "
        f"top-3 contiene chunks utiles, pero alguna distancia top-1 alta "
        f"({dist_str})"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
