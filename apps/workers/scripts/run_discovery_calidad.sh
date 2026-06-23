#!/usr/bin/env bash
# Discovery "solo calidad" (cero info@): busca el email PERSONAL de un
# responsable (decisor/nominal) en empresas FRESCAS con web. NO inserta
# genéricos (info@/contacto@...). NO envía nada — solo escribe contactos.
# Idempotente: ignora empresas que ya tienen contacto (no toca cadencias).
#
# Uso (en apps/workers):  bash scripts/run_discovery_calidad.sh
cd "$(dirname "$0")/.." || exit 1   # -> apps/workers
for T in T1 T2 T3; do
  echo
  echo "================ find_contacts $T (solo-calidad, require-web) ================"
  ENV=prod uv run python -m pipeline.find_contacts \
    --env prod --tier "$T" --require-web --solo-calidad --max-hunter-calls 40
done
echo
echo "================ AUDIT pool (virgin = listos para draft) ================"
ENV=prod uv run python -m scripts.audit_pool_contacts --env prod
