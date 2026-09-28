#!/usr/bin/env bash
# Сборка Kostik для Windows на Linux (#155–#157): переносимый Python 3.12 + библиотеки win_amd64 + код,
# запускатель «Kostik.exe», установщик .exe (NSIS, для пользователя) и .msi (wixl, на компьютер).
#   packaging/build_windows.sh [папка сборки] [папка результатов]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
BUILD=${1:-$REPO/../build-desktop}
VER=$(sed -n 's/^APP_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
WINVER=$(sed -n 's/^WIN_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
DEBVER=$(sed -n 's/^DEB_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
FVER=$(echo "$VER" | tr 'A-Z' 'a-z')                 # в именах файлов: 1.0-beta
OUT=${2:-$REPO/../dist-desktop/$VER}
PYV=3.12.10
PIP="$REPO/.venv/bin/pip"
STAGE="$BUILD/stage-win/Kostik"
mkdir -p "$BUILD" "$OUT"
echo "[win] версия $VER → $OUT"

# 1) библиотеки под Windows: готовые сборки win_amd64 и чистый Python
cd "$BUILD"
[ -f python-$PYV-embed-amd64.zip ] || curl -fsSL -o python-$PYV-embed-amd64.zip https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip
W="$BUILD/wheels-win"; P="$BUILD/pure"; mkdir -p "$W" "$P"
grep -v '^pywebview' "$REPO/packaging/requirements-desktop.txt" > req-win.txt
$PIP download -q --platform win_amd64 --python-version 3.12 --implementation cp --only-binary=:all: -d "$W" -r req-win.txt
$PIP download -q --platform win_amd64 --python-version 3.12 --implementation cp --only-binary=:all: --no-deps -d "$W" cffi pycparser
$PIP download -q --no-deps -d "$P" pywebview pythonnet clr_loader
$PIP wheel -q --no-deps -w "$P" proxy_tools bottle

# 2) папка приложения
rm -rf "$BUILD/stage-win"; mkdir -p "$STAGE/python" "$STAGE/app"
unzip -q python-$PYV-embed-amd64.zip -d "$STAGE/python"
printf 'python312.zip\n.\n..\\app\nLib\\site-packages\nimport site\n' > "$STAGE/python/python312._pth"
$PIP install -q --no-deps --no-compile --target "$STAGE/python/Lib/site-packages" --platform win_amd64 --python-version 3.12 \
  --implementation cp --only-binary=:all: "$W"/*.whl "$P"/*.whl
find "$STAGE/python/Lib/site-packages" -depth \( -name __pycache__ -o -name tests -o -name testing \) -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$STAGE/python/Lib/site-packages/bin"
rsync -a --exclude __pycache__ --exclude '*.pyc' "$REPO/dxaqc" "$STAGE/app/"
cp "$REPO/dxaqc/desktop/assets/icon.ico" "$STAGE/icon.ico"
printf '%s\r\n' "Kostik $VER — контроль качества денситометрии DXA" "" \
  "© 2026 авторы Kostik: Юрий Коноплёв, Алексей Чуркин; команда «Квантовый Скачок»." \
  "Все права защищены. Программа для контроля качества снимков, не для постановки диагноза." "" \
  "Программа работает на компьютере пользователя и не отправляет снимки в интернет." \
  "Сторонние компоненты и их лицензии — в программе: «О программе»." > "$STAGE/LICENSE.txt"
printf '@echo off\r\nchcp 65001 >nul\r\n"%%~dp0python\\python.exe" -m dxaqc.desktop --selftest\r\necho.\r\npause\r\n' > "$STAGE/selftest.cmd"
printf '@echo off\r\n"%%~dp0python\\python.exe" -m dxaqc.desktop --mcp-stdio\r\n' > "$STAGE/dxaqc-mcp.cmd"

# 3) запускатель и установщики
makensis -V2 -DOUTFILE="$STAGE/Kostik.exe" -DICON="$STAGE/icon.ico" -DVERSION="$WINVER" -DDISPLAYVER="$VER" "$REPO/packaging/windows/launcher.nsi"
makensis -V2 -DOUTFILE="$OUT/Kostik-$FVER-setup.exe" -DICON="$STAGE/icon.ico" -DVERSION="$WINVER" -DDISPLAYVER="$VER" -DSTAGE="$STAGE" \
  -DLICENSE="$STAGE/LICENSE.txt" "$REPO/packaging/windows/installer.nsi"
python3 "$REPO/packaging/windows/make_wxs.py" "$STAGE" "$WINVER" "$BUILD/dxaqc.wxs" "$VER"
wixl -a x64 -o "$OUT/Kostik-$FVER.msi" "$BUILD/dxaqc.wxs"
du -sh "$STAGE" "$OUT"/Kostik-$FVER-setup.exe "$OUT"/Kostik-$FVER.msi
