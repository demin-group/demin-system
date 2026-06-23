#!/usr/bin/env bash
# Genera drafts SOLO de calidad (decisor/nominal) para los contactos nuevos
# y los deja en la cola de aprobación (HITL). NO envía nada (hitl_mode + pausa).
# Salta corporativo_pequeno (cero info@).
#
# Uso (en apps/workers):  bash scripts/run_draft_calidad.sh
cd "$(dirname "$0")/.." || exit 1   # -> apps/workers
for T in T1 T2 T3; do
  echo
  echo "================ generate_draft $T (solo-calidad, opening) ================"
  ENV=prod uv run python -m pipeline.generate_draft \
    --env prod --tier "$T" --angle opening --solo-calidad
done
echo
echo "================ estado de la cola de aprobación ================"
ENV=prod uv run python scripts/diag_approval_queue.py
