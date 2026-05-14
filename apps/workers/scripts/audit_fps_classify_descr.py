"""audit_fps_classify_descr.py -- auditoria FPs detectados Sprint 4 paso 6.

3 candidatos:
- SERVISHOP MANLOGIST (logistica, no construccion)
- SB 63 (pinnea.com, SPA)
- RUTHERFORD ESPAÑOLA

Para cada uno: trae descripcion SABI + ia_fit + ia_fit_reason + research_data.
Decide si fue mal clasificado y propone:
- Si confirma FP -> sugerir ajuste prompt classify_descr.md.
- Si no es FP claro -> documenta dudoso y dejar para revision humana.
"""
import os
import json
from typing import Any

os.environ["ENV"] = "prod"
import psycopg
from shared.config import load_settings

CANDIDATES = [
    "SERVISHOP MANLOGIST",
    "SB 63",
    "RUTHERFORD ESPA",  # prefix para match "RUTHERFORD ESPAÑOLA" sin tildes
]


def main() -> int:
    s = load_settings("prod")
    url = s.DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        for name_prefix in CANDIDATES:
            print("=" * 78)
            print(f"AUDIT: {name_prefix}*")
            print("=" * 78)
            cur.execute(
                """
                select id::text, nif, nombre, tier, ia_fit, ia_fit_reason,
                       descripcion, web, research_data
                from companies
                where nombre ilike %s
                """,
                (f"{name_prefix}%",),
            )
            rows = cur.fetchall()
            if not rows:
                print(f"  NO encontrado en BD prod con prefix {name_prefix!r}")
                print()
                continue
            for row in rows:
                cid, nif, nombre, tier, ia_fit, reason, desc, web, rdata = row
                print(f"  nif:           {nif}")
                print(f"  nombre:        {nombre}")
                print(f"  tier:          {tier}")
                print(f"  ia_fit:        {ia_fit}")
                print(f"  ia_fit_reason: {reason}")
                print(f"  web:           {web}")
                print(f"  descripcion:   {desc}")
                if rdata:
                    if isinstance(rdata, str):
                        try:
                            rdata = json.loads(rdata)
                        except Exception:
                            pass
                    if isinstance(rdata, dict):
                        for k in (
                            "tipo_obra", "tamaño", "lenguaje", "_failed",
                            "personas_extraidas", "hook_principal",
                        ):
                            v = rdata.get(k)
                            if v is not None and v != []:
                                if isinstance(v, str) and len(v) > 100:
                                    v = v[:100] + "..."
                                print(f"  research.{k}: {v}")
                print()

    # Veredictos manuales basados en datos arriba (Code analyza tras print).
    print("=" * 78)
    print("VEREDICTO Code:")
    print("=" * 78)
    print(
        "Tras revisar BD prod, las clasificaciones se evaluan segun:\n"
        "- Descripcion SABI: si menciona logistica/SPA/no-construccion -> FP.\n"
        "- ia_fit_reason: la frase del LLM debe justificar 'fit' con senal\n"
        "  real (constructora/promotora/reformista, no servicio auxiliar).\n"
        "- research_data: si scraping de web confirma actividad ICP, no FP.\n"
        "\n"
        "Detalles por candidato:\n"
        "1. SERVISHOP MANLOGIST: si 'manlogist'/'logistica' en SABI desc o\n"
        "   research -> FP. Sugerencia prompt: anadir 'servicios logisticos,\n"
        "   transporte, almacenaje' a la lista no_fit de classify_descr.md.\n"
        "2. SB 63 (pinnea.com): si la web es SPA o nada extraible y la SABI\n"
        "   desc es vaga -> mantener pendiente (dudoso), no fit ni no_fit.\n"
        "   Sugerencia: classify_descr 'dudoso' por defecto cuando desc\n"
        "   ambigua + thin_html_possibly_spa en research.\n"
        "3. RUTHERFORD ESPAÑOLA: dependiendo de la actividad real, podria\n"
        "   ser FP si es comercio/distribucion sin obra propia.\n"
        "\n"
        "Sin LLM call adicional ($), Code propone: aplicar Lecciones 9-10\n"
        "(exclusiones operativas) mas estrictamente al universo de empresas\n"
        "con descripcion ambigua via classify_descr v2 (Sprint 7+).\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
