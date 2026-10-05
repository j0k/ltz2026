#!/usr/bin/env bash
# Подготовка данных стенда с сервера-источника: наборы организатора, установщики и ключи подписи.
# Медицинские данные и материалы организатора в git не хранятся (.gitignore: *.dcm, *.zip, data/),
# поэтому при развёртывании с нуля их забирают отдельно этим скриптом.
#
#   scripts/fetch_org_data.sh                          # наборы -> DEST (по умолчанию /srv/ltz2026/datasets)
#   scripts/fetch_org_data.sh --downloads <папка>      # ещё установщики и материалы (том /data/downloads)
#   scripts/fetch_org_data.sh --keys <папка>           # ещё ключ подписи релизов (приватный!)
#   scripts/fetch_org_data.sh --dry-run                # только показать, что будет скачано
#
# Источник и путь задаются переменными окружения:
#   SRC_HOST=jk@194.87.26.51  SRC_ROOT=/home/jk/exp/LTZ2026  SSH_KEY=~/.ssh/id_ed25519  DEST=/srv/ltz2026/datasets
#
# После раскладки наборов запуск стенда — ./serve.sh (или compose-файл infra/app/docker-compose.stand.yml).
set -euo pipefail

SRC_HOST=${SRC_HOST:-jk@194.87.26.51}
SRC_ROOT=${SRC_ROOT:-/home/jk/exp/LTZ2026}
DEST=${DEST:-${DXAQC_DATASETS_DIR:-/srv/ltz2026/datasets}}
SSH_KEY=${SSH_KEY:-}
DRY=""
DL_DIR=""
KEY_DIR=""

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --downloads) DL_DIR=${2:?--downloads требует папку}; shift 2 ;;
    --keys)      KEY_DIR=${2:?--keys требует папку}; shift 2 ;;
    --dry-run)   DRY="-n"; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "неизвестный аргумент: $1" >&2; usage; exit 2 ;;
  esac
done

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o ServerAliveInterval=10)
[ -n "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")
RSH="ssh ${SSH_OPTS[*]}"

pull() { # pull <источник> <приёмник>
  local src="$1" dst="$2" i
  for i in 1 2 3 4 5; do
    if rsync -rlt $DRY --partial --no-owner --no-group --timeout=180 -e "$RSH" "$src" "$dst"; then
      return 0
    fi
    echo "  повтор $i после сбоя связи…" >&2
    sleep 5
  done
  echo "НЕ УДАЛОСЬ забрать: $src" >&2
  return 1
}

echo "[1] наборы организатора -> $DEST"
mkdir -p "$DEST/train" "$DEST/test" "$DEST/tz"
pull "$SRC_HOST:$SRC_ROOT/data/train/Исследования/" "$DEST/train/"
pull "$SRC_HOST:$SRC_ROOT/data/Для теста/"          "$DEST/test/"
pull "$SRC_HOST:$SRC_ROOT/data/labels_clean.csv"    "$DEST/labels_clean.csv"
pull "$SRC_HOST:$SRC_ROOT/Для теста.zip"            "$DEST/Для теста.zip"
pull "$SRC_HOST:$SRC_ROOT/docs/tz/"                 "$DEST/tz/"

if [ -n "$DL_DIR" ]; then
  echo "[2] установщики и материалы -> $DL_DIR"
  mkdir -p "$DL_DIR"
  pull "$SRC_HOST:$SRC_ROOT/dist-desktop/" "$DL_DIR/"
fi

if [ -n "$KEY_DIR" ]; then
  echo "[3] ключ подписи релизов -> $KEY_DIR (приватный, не публиковать)"
  mkdir -p "$KEY_DIR"
  pull "$SRC_HOST:$SRC_ROOT/keys/" "$KEY_DIR/"
  chmod -R go-rwx "$KEY_DIR" 2>/dev/null || true
fi

if [ -z "$DRY" ]; then
  echo "готово:"
  du -sh "$DEST"/* 2>/dev/null || true
fi
