#!/usr/bin/env bash
# Сборка образа Kostik. Нужны Linux, Docker 20+ и интернет — только на время сборки
# (пакеты Python, голос Piper и Whisper для веб-интерфейса). Дальше образ работает без сети.
#   ./build.sh            -> образ dxaqc:<версия> и dxaqc:latest
set -euo pipefail
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' dxaqc/__init__.py)
docker build -t "dxaqc:${VERSION}" -t dxaqc:latest -f infra/app/Dockerfile .
echo "[build] готово: dxaqc:${VERSION}"
