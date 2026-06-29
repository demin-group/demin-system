#!/usr/bin/env bash
# Termina el scrape de emails de T4 en SEGUNDO PLANO (las ~359 empresas fit sin
# contacto). Sobrevive a la desconexión SSH (nohup) y no inunda la pantalla:
# todo va a un log. Solo escribe contactos (info@/lo que haya en la web), no
# envía nada. Idempotente.
#
# Uso (en apps/workers):  bash scripts/scrape_t4_bg.sh
#   ver progreso:   tail -f /tmp/scrape_t4.log
#   ver resumen:    tail -25 /tmp/scrape_t4.log
cd "$(dirname "$0")/.." || exit 1   # -> apps/workers
LOG=/tmp/scrape_t4.log
: > "$LOG"
nohup env ENV=prod uv run python -m pipeline.scrape_emails --env prod --tier T4 > "$LOG" 2>&1 &
PID=$!
echo "✅ Scrape T4 corriendo en segundo plano (PID $PID). Log: $LOG"
echo "   Puedes desconectarte; sigue corriendo."
echo "   Progreso:  tail -f $LOG       (Ctrl+C para salir del tail, NO para el scrape)"
echo "   Resumen:   tail -25 $LOG      (cuando veas la línea 'FIN scrape_emails')"
