#!/usr/bin/env bash
# Деплой стенда одной командой: сборка образа, перезапуск контейнера, проверка здоровья и примера.
#   infra/app/deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

LOCAL=http://127.0.0.1:8098
PUBLIC=https://ltz2026.juri-konoplev.pro/

echo "[deploy] сборка образа"
docker compose build --pull=false

# перезапуск обрывает идущий прогон: ждём, пока закончатся те, что реально считаются (статус обновлялся за 2 минуты);
# зависшие после прошлых перезапусков новый сервис сам поставит в очередь заново. DEPLOY_FORCE=1 — не ждать.
if [ "${DEPLOY_FORCE:-0}" != "1" ] && docker ps --format '{{.Names}}' | grep -qx ltz_app; then
  for i in $(seq 1 180); do
    busy=$(docker exec ltz_app python -c '
import glob, json, os, time
n = 0
for p in glob.glob("/data/runs/*/status.json"):
    try:
        st = json.load(open(p))
    except Exception:
        continue
    if st.get("state") in ("running", "queued") and time.time() - os.path.getmtime(p) < 120:
        n += 1
print(n)' 2>/dev/null || echo 0)
    [ "$busy" = "0" ] && break
    [ "$i" = "1" ] && echo -n "[deploy] ждём окончания прогонов: $busy"
    echo -n "."; sleep 5
  done
  [ "${busy:-0}" = "0" ] || echo " — не дождались, перезапускаем: прогон продолжится с начала после старта"
  [ "${busy:-0}" = "0" ] && [ "${i:-1}" != "1" ] && echo " ok"
fi

echo "[deploy] перезапуск контейнера"
docker compose up -d --remove-orphans

echo -n "[deploy] ожидание сервиса"
for _ in $(seq 1 60); do
  if curl -fsS "$LOCAL/api/health" >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 2
done
curl -fsS "$LOCAL/api/health" >/dev/null || { echo; echo "[deploy] сервис не поднялся"; docker logs --tail 50 ltz_app; exit 1; }

echo -n "[deploy] прогон примера"
for _ in $(seq 1 90); do
  state=$(curl -fsS "$LOCAL/api/runs/example" 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("state"))' 2>/dev/null || true)
  if [ "$state" = "done" ] || [ "$state" = "error" ]; then break; fi
  echo -n "."; sleep 2
done
echo " $state"
[ "$state" = "done" ] || { echo "[deploy] пример не обработался"; docker logs --tail 50 ltz_app; exit 1; }

docker image prune -f >/dev/null 2>&1 || true
echo "[deploy] готово: $PUBLIC"
