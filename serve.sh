#!/usr/bin/env bash
# Веб-интерфейс и HTTP API на http://localhost:${PORT:-8000}: загрузка снимков, разбор, таблицы, атласы.
#   ./serve.sh            -> запуск в фоне, контейнер dxaqc_web, данные в volume dxaqc_data
#   ./serve.sh stop       -> остановить
#
# На стенде дополнительно подключаются наборы организатора, сид-пример и документы ТЗ, если они
# разложены в DATASETS (по умолчанию /srv/ltz2026/datasets): train/, test/, labels_clean.csv,
# «Для теста.zip», tz/. Медицинские данные и материалы организатора в git не хранятся и готовятся
# отдельно (см. doc/DEPLOY.md, раздел «Стенд с доменом»).
set -euo pipefail
IMAGE=${DXAQC_IMAGE:-dxaqc:latest}
PORT=${PORT:-8000}
NAME=${DXAQC_NAME:-dxaqc_web}
VOL=${DXAQC_VOL:-dxaqc_data}
DATASETS=${DXAQC_DATASETS_DIR:-/srv/ltz2026/datasets}

docker rm -f "$NAME" >/dev/null 2>&1 || true
[ "${1:-}" = "stop" ] && { echo "[serve] остановлен"; exit 0; }

ARGS=(-d --name "$NAME" --restart unless-stopped -p "127.0.0.1:${PORT}:8000" -v "$VOL:/data")
[ -d "$DATASETS/train" ] && ARGS+=(-v "$DATASETS/train:/datasets/train:ro" -e DXAQC_DATASETS=/datasets)
[ -d "$DATASETS/test" ] && ARGS+=(-v "$DATASETS/test:/datasets/test:ro" -e DXAQC_DATASETS=/datasets)
[ -f "$DATASETS/labels_clean.csv" ] && ARGS+=(-v "$DATASETS/labels_clean.csv:/datasets/train_labels.csv:ro")
[ -f "$DATASETS/Для теста.zip" ] && ARGS+=(-v "$DATASETS/Для теста.zip:/seed/Для теста.zip:ro" -e DXAQC_SEED="/seed/Для теста.zip")
[ -d "$DATASETS/tz" ] && ARGS+=(-v "$DATASETS/tz:/tz:ro")

docker run "${ARGS[@]}" "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1 && { echo "[serve] http://localhost:${PORT}/"; exit 0; }
  sleep 1
done
echo "[serve] сервис не ответил за минуту: docker logs $NAME" >&2; exit 1
