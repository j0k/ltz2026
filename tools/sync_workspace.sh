#!/usr/bin/env bash
# Папка workspace для вопросов к Claude со стенда: копия проекта без медицинских данных и тяжёлых файлов.
# Отдельно от рабочего репозитория, чтобы вопрос с полными правами (после одобрения админом) менял копию, а не живой проект.
#   tools/sync_workspace.sh [куда]     по умолчанию /home/jk/exp/ltz2026-workspace
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${1:-/home/jk/exp/ltz2026-workspace}"
mkdir -p "$DST"
rsync -a --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' --exclude '.pytest_cache/' \
  --exclude 'data/' --exclude '*.zip' --exclude '*.dcm' \
  --exclude 'films/' --exclude 'results/' --exclude 'web/.server.log' \
  --exclude '.env' --exclude '*.htpasswd' \
  --exclude 'README_WORKSPACE.md' \
  "$SRC/" "$DST/"
cat > "$DST/README_WORKSPACE.md" <<EOF
# Рабочая папка для вопросов к Claude

Копия проекта LTZ2026 (команда «Квантовый Скачок», ЛЦТ 2026, задача 04 ДепЗдрава: контроль качества DXA).
Обновлено: $(date '+%d.%m.%Y %H:%M') скриптом tools/sync_workspace.sh из $SRC.

Здесь нет медицинских данных организатора (data/, архивы, DICOM) и роликов: вопросы уходят в Claude, то есть во внешний сервис.
Правки в этой папке не попадают в рабочий репозиторий и перезаписываются при следующей синхронизации.

- dxaqc/ — сервис: чтение DICOM, анализ, атлас, веб-стенд
- infra/ — контейнеры стенда и трекера
- scripts/, tools/, tests/ — скрипты, утилиты, тесты
- 4. ДепЗдрав.pdf — ТЗ задачи
EOF
echo "workspace: $DST"
du -sh "$DST" | cut -f1
