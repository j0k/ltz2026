#!/bin/sh
# Entrypoint Trac для ЛЦТ 2026. Основан на параметризованном entrypoint zhelicore:
# base-path/base_url/repo из переменных окружения. Дополнительно при первой инициализации
# убирает демо-компоненты и демо-вехи и заводит компоненты проекта.
# Эпики ведутся вехами (milestone), задачи и дефекты — тикетами.
set -e

ENVDIR=/trac/env
REPO=/repo
PROJECT="${TRAC_PROJECT:-Project}"
BASE_PATH="${TRAC_BASE_PATH:-/}"
BASE_URL="${TRAC_BASE_URL:-}"
REPO_NAME="${TRAC_REPO_NAME:-repo}"

git config --global --add safe.directory '*' || true

if [ ! -f "$ENVDIR/VERSION" ]; then
  echo "[trac] initializing environment ($PROJECT)..."
  trac-admin "$ENVDIR" initenv "$PROJECT" sqlite:db/trac.db
  trac-admin "$ENVDIR" config set project descr "$PROJECT"

  trac-admin "$ENVDIR" config set components "tracopt.versioncontrol.git.*" enabled
  trac-admin "$ENVDIR" config set git cached_repository true
  trac-admin "$ENVDIR" config set git persistent_cache true

  # демо-данные Trac нам не нужны
  for m in milestone1 milestone2 milestone3 milestone4; do trac-admin "$ENVDIR" milestone remove "$m" || true; done
  for c in component1 component2; do trac-admin "$ENVDIR" component remove "$c" || true; done
  for v in 1.0 2.0; do trac-admin "$ENVDIR" version remove "$v" || true; done

  # компоненты проекта
  trac-admin "$ENVDIR" component add "Данные"          || true
  trac-admin "$ENVDIR" component add "Модель"          || true
  trac-admin "$ENVDIR" component add "Правила и геометрия" || true
  trac-admin "$ENVDIR" component add "Пайплайн и API"  || true
  trac-admin "$ENVDIR" component add "Контейнер"       || true
  trac-admin "$ENVDIR" component add "Метрики"         || true
  trac-admin "$ENVDIR" component add "Документация"    || true
  trac-admin "$ENVDIR" component add "Презентация"     || true
  trac-admin "$ENVDIR" component add "Веб и телемедицина" || true

  trac-admin "$ENVDIR" config set ticket default_type task
  trac-admin "$ENVDIR" config set ticket default_component "Пайплайн и API"

  # анонимам только просмотр (права по умолчанию); права администратора у команды после входа
  trac-admin "$ENVDIR" permission add ltz TRAC_ADMIN || true
fi

if [ -n "$BASE_URL" ]; then
  trac-admin "$ENVDIR" config set trac base_url "$BASE_URL"
  trac-admin "$ENVDIR" config set trac use_base_url_for_redirect true
fi

# репозиторий может быть ещё без коммитов — это не должно ронять старт
if [ -d "$REPO/.git" ]; then
  trac-admin "$ENVDIR" repository add "$REPO_NAME" "$REPO" git 2>/dev/null || true
  trac-admin "$ENVDIR" repository resync "$REPO_NAME" 2>/dev/null || true
fi

# вход команды: tracd сам проверяет пароль на /login по хешу из $ENVDIR/htpasswd;
# просмотр открыт всем без пароля
AUTH=""
if [ -f "$ENVDIR/htpasswd" ]; then
  AUTH="--basic-auth=*,$ENVDIR/htpasswd,LTZ2026"
fi

echo "[trac] starting tracd on :8000 base-path=$BASE_PATH ${AUTH:+(login enabled)}"
exec tracd --port 8000 -b 0.0.0.0 --base-path="$BASE_PATH" $AUTH -s "$ENVDIR"
