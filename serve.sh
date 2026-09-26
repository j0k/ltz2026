#!/usr/bin/env bash
# Веб-интерфейс и HTTP API на http://localhost:${PORT:-8000}: загрузка снимков, разбор, таблицы, атласы.
#   ./serve.sh            -> запуск в фоне, контейнер dxaqc_web, данные в volume dxaqc_data
#   ./serve.sh stop       -> остановить
set -euo pipefail
IMAGE=${DXAQC_IMAGE:-dxaqc:latest}
PORT=${PORT:-8000}
docker rm -f dxaqc_web >/dev/null 2>&1 || true
[ "${1:-}" = "stop" ] && { echo "[serve] остановлен"; exit 0; }
docker run -d --name dxaqc_web --restart unless-stopped -p "127.0.0.1:${PORT}:8000" \
  -v dxaqc_data:/data "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1 && { echo "[serve] http://localhost:${PORT}/"; exit 0; }
  sleep 1
done
echo "[serve] сервис не ответил за минуту: docker logs dxaqc_web" >&2; exit 1
