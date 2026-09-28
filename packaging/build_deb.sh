#!/usr/bin/env bash
# Сборка DXA QC для Linux (#158): .deb для Ubuntu 22.04–26.04 и Debian 12–13. Библиотеки под Python 3.10–3.14 внутри,
# окно — системный WebKitGTK через pywebview; интернет при установке не нужен.
#   packaging/build_deb.sh [папка сборки] [папка результатов]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
BUILD=${1:-$REPO/../build-desktop}
VER=$(sed -n 's/^APP_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
WINVER=$(sed -n 's/^WIN_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
DEBVER=$(sed -n 's/^DEB_VERSION = "\([^"]*\)".*/\1/p' "$REPO/dxaqc/desktop/__init__.py")
FVER=$(echo "$VER" | tr 'A-Z' 'a-z')                 # в именах файлов: 1.0-beta
OUT=${2:-$REPO/../dist-desktop/$VER}
PIP="$REPO/.venv/bin/pip"
PKG="$BUILD/deb/dxaqc_${FVER}_amd64"
mkdir -p "$OUT"; cd "$BUILD"
echo "[deb] версия $VER → $OUT"
grep -v '^pywebview' "$REPO/packaging/requirements-desktop.txt" > req-lin.txt
declare -A NUMPY=([3.10]=2.2.6 [3.11]=2.4.6 [3.12]= [3.13]= [3.14]=)
P="$BUILD/pure"; mkdir -p "$P"
$PIP download -q --no-deps -d "$P" pywebview
$PIP wheel -q --no-deps -w "$P" proxy_tools bottle
rm -rf "$BUILD/deb"; mkdir -p "$PKG/DEBIAN" "$PKG/opt/dxaqc/app" "$PKG/usr/bin" "$PKG/usr/share/applications" \
  "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/doc/dxaqc" "$PKG/usr/share/metainfo"
for v in 3.10 3.11 3.12 3.13 3.14; do
  req=req-lin.txt
  if [ -n "${NUMPY[$v]}" ]; then sed "s/^numpy==.*/numpy==${NUMPY[$v]}/" req-lin.txt > req-lin-$v.txt; req=req-lin-$v.txt; fi
  # pip подбирает зависимости по условиям текущего Python, поэтому нужное только старым версиям — явно
  [ "$v" = "3.10" ] && echo "exceptiongroup" >> $req
  W="$BUILD/wheels-lin/$v"; mkdir -p "$W"
  $PIP download -q --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 \
    --python-version $v --implementation cp --only-binary=:all: -d "$W" -r $req
  $PIP install -q --no-deps --no-compile --target "$PKG/opt/dxaqc/lib/py${v/./}" --platform manylinux_2_28_x86_64 \
    --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --python-version $v --implementation cp \
    --only-binary=:all: "$W"/*.whl "$P"/pywebview-*.whl "$P"/proxy_tools-*.whl "$P"/bottle-*.whl
done
find "$PKG/opt/dxaqc/lib" -depth \( -name __pycache__ -o -name tests -o -name testing \) -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "$PKG"/opt/dxaqc/lib/*/bin
rsync -a --exclude __pycache__ --exclude '*.pyc' "$REPO/dxaqc" "$PKG/opt/dxaqc/app/"
python3 "$REPO/packaging/linux/dedupe.py" "$PKG/opt/dxaqc/lib"
cat > "$PKG/usr/bin/dxaqc" <<'SH'
#!/bin/sh
# DXA QC — контроль качества денситометрии DXA: окно приложения, --selftest, --mcp-stdio
V=$(python3 -c 'import sys; print("%d%d" % sys.version_info[:2])' 2>/dev/null)
LIB=/opt/dxaqc/lib/py$V
if [ ! -d "$LIB" ]; then
  echo "DXA QC: системный Python 3.${V#3} не поддерживается этим пакетом — нужен Python от 3.10 до 3.14" >&2
  exit 1
fi
export PYTHONPATH="/opt/dxaqc/app:$LIB${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -m dxaqc.desktop "$@"
SH
chmod 755 "$PKG/usr/bin/dxaqc"
cat > "$PKG/usr/share/applications/dxaqc.desktop" <<'DT'
[Desktop Entry]
Type=Application
Name=DXA QC
GenericName=Контроль качества денситометрии
Comment=Проверка качества снимков денситометрии DXA без интернета
Exec=dxaqc %F
Icon=dxaqc
Terminal=false
Categories=Science;MedicalSoftware;Graphics;
MimeType=application/dicom;
Keywords=DXA;DICOM;densitometry;денситометрия;остеопороз;
DT
cp "$REPO/dxaqc/desktop/assets/icon.png" "$PKG/usr/share/icons/hicolor/256x256/apps/dxaqc.png"
cat > "$PKG/usr/share/doc/dxaqc/copyright" <<CP
DXA QC $VER — контроль качества денситометрии DXA
© 2026 авторы DXA QC: Юрий Коноплёв, Алексей Чуркин; команда «Квантовый Скачок». Все права защищены.
Программа для контроля качества снимков, не для постановки диагноза. Сайт: https://ltz2026.ru
Сторонние компоненты и их лицензии — в программе, раздел «О программе».
CP
cat > "$PKG/usr/share/metainfo/ru.ltz2026.dxaqc.metainfo.xml" <<MI
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>ru.ltz2026.dxaqc</id>
  <launchable type="desktop-id">dxaqc.desktop</launchable>
  <name>DXA QC</name>
  <name xml:lang="ru">DXA QC</name>
  <summary>Quality control of DXA densitometry images</summary>
  <summary xml:lang="ru">Контроль качества снимков денситометрии DXA</summary>
  <developer id="ru.ltz2026"><name>Алексей Чуркин и Юрий Коноплёв</name></developer>
  <developer_name>Алексей Чуркин и Юрий Коноплёв</developer_name>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>LicenseRef-proprietary</project_license>
  <description>
    <p>Checks DICOM images of lumbar spine and hip against DXA quality criteria. Works offline.</p>
    <p xml:lang="ru">Проверяет снимки денситометрии DXA поясничного отдела и бедра по критериям ТЗ Департамента здравоохранения Москвы: область, вердикт и причина брака, разметка на атласе, пояснение решения, выгрузка таблиц CSV и XLSX.</p>
    <p xml:lang="ru">Работает без интернета — снимки не покидают компьютер. Встроенная справка и локальный MCP-сервер для ИИ-ассистентов.</p>
  </description>
  <url type="homepage">https://ltz2026.ru</url>
  <categories><category>Science</category><category>MedicalSoftware</category></categories>
  <releases><release version="$DEBVER" date="$(date +%F)"/></releases>
  <content_rating type="oars-1.1"/>
</component>
MI
SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CT
Package: dxaqc
Version: $DEBVER
Architecture: amd64
Maintainer: Alexey Churkin and Yuri Konoplev <support@ltz2026.ru>
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3 (<< 3.15), python3-gi, ca-certificates, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0
Recommends: xdg-utils
Section: science
Priority: optional
Homepage: https://ltz2026.ru
Description: DXA QC - quality control of DXA densitometry images
 Checks DICOM images of lumbar spine and hip against the quality criteria
 of the Moscow Healthcare Department: region, verdict, reason of rejection,
 annotated atlas, explanation graph, CSV/XLSX export. Works offline: images
 never leave the computer. Built-in help and a local MCP server.
 Authors: Alexey Churkin, Yuri Konoplev (team Quantum Leap, LCT 2026).
 Interface language: Russian.
CT
cat > "$PKG/DEBIAN/postinst" <<'PI'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
PI
cp "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
dpkg-deb --root-owner-group -Zxz -b "$PKG" "$OUT/dxaqc_${FVER}_amd64.deb" >/dev/null
du -sh "$PKG" "$OUT/dxaqc_${FVER}_amd64.deb"
