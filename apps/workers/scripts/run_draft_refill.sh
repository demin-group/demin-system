#!/usr/bin/env bash
# Genera drafts (apertura) para TODOS los contactos primarios nuevos —
# cascada por defecto: responsable si lo hay, info@ si no. Van a la cola de
# aprobación (HITL). NO envía nada (hitl_mode + bandeja en pausa).
# El coste LLM va capado por --max-cost-usd interno de generate_draft.
#
# Uso (en apps/workers):  bash scripts/run_draft_refill.sh
cd "$(dirname "$0")/.." || exit 1   # -> apps/workers
for T in T1 T2 T3 T4; do
  echo
  echo "================ generate_draft $T (opening, cascada) ================"
  ENV=prod uv run python -m pipeline.generate_draft \
    --env prod --tier "$T" --angle opening
done
echo
echo "================ estado de la cola de aprobación ================"
ENV=prod uv run python scripts/diag_approval_queue.py
