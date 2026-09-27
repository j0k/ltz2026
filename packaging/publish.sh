#!/usr/bin/env bash
# Раскладка релиза для сайта (#162): <dist>/latest.json, <dist>/<версия>/{пакеты, SHA256SUMS},
# <dist>/models/{manifest.json, файлы моделей}. Стенд отдаёт <dist> как /downloads (том только на чтение).
#   packaging/publish.sh [папка dist]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
DIST=${1:-$REPO/../dist-desktop}
VER=$(sed -n 's/^APP_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
WINVER=$(sed -n 's/^WIN_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
DEBVER=$(sed -n 's/^DEB_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
FVER=$(echo "$VER" | tr 'A-Z' 'a-z')                 # в именах файлов: 1.0-beta
cd "$DIST/$VER"
sha256sum DXAQC-$FVER-setup.exe DXAQC-$FVER.msi dxaqc_${FVER}_amd64.deb > SHA256SUMS
mkdir -p "$DIST/models"
for f in ru_RU-irina-medium.onnx ru_RU-irina-medium.onnx.json; do
  [ -f "$DIST/models/$f" ] || docker cp "ltz_app:/models/piper/$f" "$DIST/models/$f"
done
python3 - "$DIST" "$VER" "$FVER" <<'PY'
import hashlib, json, os, sys, time, zlib


def crc(p):
    c = 0
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            c = zlib.crc32(b, c)
    return f"{c & 0xFFFFFFFF:08X}"
dist, ver, fver = sys.argv[1], sys.argv[2], sys.argv[3]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
files = [dict(name=n, size=os.path.getsize(os.path.join(dist, ver, n)), sha256=sha(os.path.join(dist, ver, n)),
              crc32=crc(os.path.join(dist, ver, n)))
         for n in (f"DXAQC-{fver}-setup.exe", f"DXAQC-{fver}.msi", f"dxaqc_{fver}_amd64.deb")]
with open(os.path.join(dist, ver, "CRC32SUMS"), "w") as f:
    f.writelines(f"{x['crc32']}  {x['name']}\n" for x in files)
json.dump(dict(version=ver, date=time.strftime("%Y-%m-%d"), files=files), open(os.path.join(dist, "latest.json"), "w"),
          ensure_ascii=False, indent=1)
m = os.path.join(dist, "models")
voice = [dict(name=n, size=os.path.getsize(os.path.join(m, n)), sha256=sha(os.path.join(m, n)), crc32=crc(os.path.join(m, n)),
              url=f"https://ltz2026.ru/downloads/models/{n}") for n in ("ru_RU-irina-medium.onnx", "ru_RU-irina-medium.onnx.json")]
json.dump(dict(models=[dict(key="piper-irina", dir="piper", title="Голос для озвучки пояснений",
                            purpose="Русский голос Piper (Irina, medium): программа читает вслух пояснения к снимку. "
                                    "Работает без интернета после загрузки.", version="1.0", files=voice)]),
          open(os.path.join(m, "manifest.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(json.load(open(os.path.join(dist, "latest.json"))), ensure_ascii=False)[:300])
PY
