#!/usr/bin/env bash
# Раскладка релиза для сайта (#162): <dist>/latest.json, <dist>/<версия>/{пакеты, SHA256SUMS},
# <dist>/models/{manifest.json, файлы моделей}. Стенд отдаёт <dist> как /downloads (том только на чтение).
#   packaging/publish.sh [папка dist]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
DIST=${1:-$REPO/../dist-desktop}
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/dxaqc/__init__.py")
cd "$DIST/$VER"
sha256sum DXAQC-$VER-setup.exe DXAQC-$VER.msi dxaqc_${VER}_amd64.deb > SHA256SUMS
mkdir -p "$DIST/models"
for f in ru_RU-irina-medium.onnx ru_RU-irina-medium.onnx.json; do
  [ -f "$DIST/models/$f" ] || docker cp "ltz_app:/models/piper/$f" "$DIST/models/$f"
done
python3 - "$DIST" "$VER" <<'PY'
import hashlib, json, os, sys, time
dist, ver = sys.argv[1], sys.argv[2]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
files = [dict(name=n, size=os.path.getsize(os.path.join(dist, ver, n)), sha256=sha(os.path.join(dist, ver, n)))
         for n in (f"DXAQC-{ver}-setup.exe", f"DXAQC-{ver}.msi", f"dxaqc_{ver}_amd64.deb")]
json.dump(dict(version=ver, date=time.strftime("%Y-%m-%d"), files=files), open(os.path.join(dist, "latest.json"), "w"),
          ensure_ascii=False, indent=1)
m = os.path.join(dist, "models")
voice = [dict(name=n, size=os.path.getsize(os.path.join(m, n)), sha256=sha(os.path.join(m, n)),
              url=f"https://ltz2026.ru/downloads/models/{n}") for n in ("ru_RU-irina-medium.onnx", "ru_RU-irina-medium.onnx.json")]
json.dump(dict(models=[dict(key="piper-irina", dir="piper", title="Голос для озвучки пояснений",
                            purpose="Русский голос Piper (Irina, medium): программа читает вслух пояснения к снимку. "
                                    "Работает без интернета после загрузки.", version="1.0", files=voice)]),
          open(os.path.join(m, "manifest.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(json.load(open(os.path.join(dist, "latest.json"))), ensure_ascii=False)[:300])
PY
