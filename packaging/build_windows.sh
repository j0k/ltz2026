#!/usr/bin/env bash
# Сборка Kostik для Windows на Linux (#155–#157): переносимый Python 3.12 + библиотеки win_amd64 + код,
# запускатели «Kostik.exe» (оконный) и «Kostik-cli.exe» (консольный), установщик .exe (NSIS) и .msi (wixl).
# Нужны: nsis, msitools, wixl, rsync, curl, unzip, .venv с Python 3.12; для запускателей — gcc-mingw-w64-x86-64 или Docker.
#   packaging/build_windows.sh [папка сборки] [папка результатов]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
BUILD=${1:-$REPO/../build-desktop}
VER=$(sed -n 's/^APP_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
WINVER=$(sed -n 's/^WIN_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
DEBVER=$(sed -n 's/^DEB_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
FVER=$(echo "$VER" | tr 'A-Z' 'a-z')                 # в именах файлов: 1.0-beta
STAMP=${BUILD_STAMP:-$(TZ=UTC-3 date +%Y%m%d-%H%M)}  # дата и время сборки по Москве
FULL="$VER-$STAMP"                                   # версия для человека: 1.0-Beta-20260930-0015
OUT=${2:-$REPO/../dist-desktop/$VER}
PYV=3.12.10
PIP="$REPO/.venv/bin/pip"
STAGE="$BUILD/stage-win/Kostik"
mkdir -p "$BUILD" "$OUT"
echo "[win] версия $FULL → $OUT"

# 1) библиотеки под Windows: готовые сборки win_amd64 и чистый Python
cd "$BUILD"
[ -f python-$PYV-embed-amd64.zip ] || curl -fsSL -o python-$PYV-embed-amd64.zip https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip
W="$BUILD/wheels-win"; P="$BUILD/pure-win"; rm -rf "$P"; mkdir -p "$W" "$P"   # чистая папка: старые версии pythonnet ломают подбор
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
# .agents — подсказки для ИИ-агентов внутри библиотек (FastAPI): программе не нужны, а имя с точки ломает установку .msi
find "$STAGE/python/Lib/site-packages" -depth \( -name __pycache__ -o -name tests -o -name testing -o -name .agents \) -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$STAGE/python/Lib/site-packages/bin"
rsync -a --exclude __pycache__ --exclude '*.pyc' "$REPO/dxaqc" "$STAGE/app/"
printf 'BUILD = "%s"\n' "$STAMP" > "$STAGE/app/dxaqc/desktop/_build.py"
cp "$REPO/dxaqc/desktop/assets/icon.ico" "$STAGE/icon.ico"
cp "$REPO/dxaqc/desktop/assets/dcm.ico" "$STAGE/dcm.ico"          # значок файлов .dcm: лист со значком Kostik
# лицензионное соглашение: страница установщика и файл в папке программы; окончания строк — как в Windows
tr -d '\r' < "$REPO/packaging/windows/license.txt" | sed -e "s/{VERSION}/$FULL/g" -e 's/$/\r/' > "$STAGE/LICENSE.txt"
printf '@echo off\r\nchcp 65001 >nul\r\n"%%~dp0python\\python.exe" -m dxaqc.desktop --selftest\r\necho.\r\npause\r\n' > "$STAGE/selftest.cmd"
printf '@echo off\r\n"%%~dp0python\\python.exe" -m dxaqc.desktop --mcp-stdio\r\n' > "$STAGE/dxaqc-mcp.cmd"
printf '@echo off\r\n"%%~dp0Kostik-cli.exe" --verbose\r\necho.\r\necho Журнал сохранён в dxaqc-verbose.log в папке данных (%%LOCALAPPDATA%%\\DXA QC).\r\npause\r\n' > "$STAGE/verbose.cmd"

# 2б) байт-код заранее: в C:\Program Files обычный пользователь не может писать .pyc, без этого каждый запуск — холодный
"$REPO/.venv/bin/python" -m compileall -q -j 2 --invalidation-mode unchecked-hash "$STAGE/app" "$STAGE/python/Lib" 2>/dev/null || \
  "$REPO/.venv/bin/python" -m compileall -q --invalidation-mode unchecked-hash "$STAGE/app" || true
SHORTVER=$(echo "$WINVER" | cut -d. -f1,2)
SIZEKB=$(du -sk "$STAGE" | cut -f1)

# 3) запускатель и установщики
# Kostik.exe — оконный, для ярлыков; Kostik-cli.exe — консольный (--help, --version, --author, --mcp, --verbose, --host)
# KOSTIK_LAUNCHERS — папка с готовыми запускателями: так в установщики попадают уже подписанные Kostik.exe и Kostik-cli.exe
if [ -n "${KOSTIK_LAUNCHERS:-}" ]; then
  cp "$KOSTIK_LAUNCHERS/Kostik.exe" "$KOSTIK_LAUNCHERS/Kostik-cli.exe" "$STAGE/"
  echo "[launcher] готовые запускатели из $KOSTIK_LAUNCHERS"
else
  "$REPO/packaging/windows/launcher/build.sh" "$STAGE" "$STAGE/icon.ico" "$WINVER" "$FULL"
fi
makensis -V2 -DOUTFILE="$OUT/Kostik-$FVER-setup.exe" -DICON="$STAGE/icon.ico" -DVERSION="$WINVER" -DSHORTVER="$SHORTVER" -DSIZEKB="$SIZEKB" -DDISPLAYVER="$FULL" -DSTAGE="$STAGE" \
  -DLICENSE="$STAGE/LICENSE.txt" "$REPO/packaging/windows/installer.nsi"
python3 "$REPO/packaging/windows/make_wxs.py" "$STAGE" "$WINVER" "$BUILD/dxaqc.wxs" "$FULL"
wixl -a x64 -o "$OUT/Kostik-$FVER.msi" "$BUILD/dxaqc.wxs"
du -sh "$STAGE" "$OUT"/Kostik-$FVER-setup.exe "$OUT"/Kostik-$FVER.msi
