#!/usr/bin/env bash
# Пакетная проверка качества DXA без сети.
#   ./run.sh <папка с DICOM или архив .zip> <папка результатов> [параметры]
# Результат: results.csv и results.xlsx (строка на снимок), overlays.zip (снимки с разметкой),
# manifest.json (сводка и время). Параметры — см. ./run.sh --help, например --axis-limit-deg 5.
set -euo pipefail
IMAGE=${DXAQC_IMAGE:-dxaqc:latest}
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ $# -lt 2 ]; then
  docker run --rm --network none "$IMAGE" python -m dxaqc.pipeline --help
  [ $# -ge 2 ] || exit 2
  exit 0
fi
IN=$(realpath "$1"); OUT=$(realpath -m "$2"); shift 2
[ -e "$IN" ] || { echo "нет входа: $IN" >&2; exit 2; }
mkdir -p "$OUT"
if [ -d "$IN" ]; then MOUNT=(-v "$IN:/input:ro"); SRC=/input
else MOUNT=(-v "$(dirname "$IN"):/input:ro"); SRC="/input/$(basename "$IN")"; fi
# --network none: снимки не покидают машину; файлы результатов принадлежат запустившему пользователю
docker run --rm --network none --user "$(id -u):$(id -g)" -e HOME=/tmp \
  "${MOUNT[@]}" -v "$OUT:/output" "$IMAGE" python -m dxaqc.pipeline "$SRC" /output "$@"
echo "[run] результаты: $OUT/results.csv, results.xlsx, overlays.zip" >&2
