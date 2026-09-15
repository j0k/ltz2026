#!/usr/bin/env bash
# Держит брокер вопросов запущенным: перезапуск через 5 секунд после падения. Запускается в окне tmux.
#   tools/run_ask_broker.sh
# Слушает шлюз сети контейнера стенда: доступен контейнеру, но не из интернета.
cd "$(dirname "$0")/.."
NET_GW="${ASK_HOST:-$(docker network inspect app_default --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null)}"
NET_GW="${NET_GW:-172.27.0.1}"
while true; do
  /home/jk/exp/Codellake/.venv/bin/python tools/ask_broker.py --instance LTZ-ASK \
    --workspace /home/jk/exp/ltz2026-workspace --host "$NET_GW" --port "${ASK_PORT:-8099}"
  echo "[run_ask_broker] брокер завершился с кодом $?, перезапуск через 5 с" >&2
  sleep 5
done
