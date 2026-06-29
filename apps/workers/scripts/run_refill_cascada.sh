#!/usr/bin/env bash
# CASCADA por defecto (política D20): se esfuerza por el email del RESPONSABLE
# y, si no está, cae a info@ / al email que encuentre. Refresca el pool de
# contactos. NO envía nada (solo escribe contactos). Idempotente: solo toca
# empresas SIN contacto (no re-machaca cadencias en vuelo).
#
# Orden por empresa:
#   1) find_contacts (Hunter Domain Search): decisor > nominal > info@.
#   2) scrape_emails (web propia): para las que Hunter dejó vacías -> info@/lo que haya.
#
# Uso (en apps/workers):  bash scripts/run_refill_cascada.sh
cd "$(dirname "$0")/.." || exit 1   # -> apps/workers
for T in T1 T2 T3 T4; do
  echo
  echo "================ find_contacts $T (Hunter: responsable, si no info@) ================"
  ENV=prod uv run python -m pipeline.find_contacts \
    --env prod --tier "$T" --require-web --max-hunter-calls 80
  echo
  echo "================ scrape_emails $T (fallback web: info@/lo que haya) ================"
  ENV=prod uv run python -m pipeline.scrape_emails --env prod --tier "$T"
done
echo
echo "================ AUDIT pool (virgin = listos para draft) ================"
ENV=prod uv run python -m scripts.audit_pool_contacts --env prod
