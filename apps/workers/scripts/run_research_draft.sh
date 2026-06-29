#!/usr/bin/env bash
# RESEARCH -> DRAFT. Investiga la web de las empresas fit sin research y luego
# genera los borradores (calidad + info@) → cola de aprobación (HITL, no envía).
#
# - El research es el paso que faltaba: generate_draft exige research hecho.
# - Idempotente y resumible: si se corta el SSH, lo completado se guarda;
#   basta re-lanzar este mismo comando para continuar.
# - Coste LLM capado (~3$/tier en research). Webs muertas/JS fallarán → esas
#   no se podrán dibujar (saldrá un subconjunto, no los 38 enteros).
#
# Uso (en apps/workers):  bash scripts/run_research_draft.sh
cd "$(dirname "$0")/.." || exit 1   # -> apps/workers

for T in T1 T2 T3 T4; do
  echo
  echo "================ RESEARCH $T ================"
  ENV=prod uv run python -m pipeline.research_prospect --env prod --tier "$T" --max-cost-usd 3
done

for T in T1 T2 T3 T4; do
  echo
  echo "================ DRAFT $T (opening, calidad + info@) ================"
  ENV=prod uv run python -m pipeline.generate_draft --env prod --tier "$T" --angle opening
done

echo
echo "================ ESTADO DE LA COLA ================"
ENV=prod uv run python scripts/diag_approval_queue.py
