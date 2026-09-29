#!/usr/bin/env bash
# Сборка запускателей: Kostik.exe (консольный) и Kostik-app.exe (оконный, для ярлыков).
#   build.sh <папка результата> <icon.ico> <версия 1.0.0> <отображаемая 1.0-Beta>
# Есть mingw на машине — собираем им, нет — в Docker-образе kostik-mingw (собирается один раз).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(cd "$1" && pwd); ICON=$(readlink -f "$2"); VER=$3; DISP=$4
W=$(mktemp -d)
COMMA=$(echo "$VER" | tr . , ); COMMA="$COMMA,0"
cp "$HERE/kostik_launcher.c" "$W/"; cp "$ICON" "$W/icon.ico"
mk_rc() { sed -e "s/@COMMA@/$COMMA/g" -e "s/@VERSION@/$VER/g" -e "s/@DISPLAY@/$DISP/g" -e "s/@NAME@/$1/g" -e "s/@DESC@/$2/g" "$HERE/kostik.rc.in" > "$W/$3"; }
mk_rc Kostik.exe "Kostik — контроль качества денситометрии (командная строка и запуск)" console.rc
mk_rc Kostik-app.exe "Kostik — контроль качества денситометрии" gui.rc
BUILD='set -e; cd /w
 x86_64-w64-mingw32-windres -c 65001 console.rc -O coff -o console.res
 x86_64-w64-mingw32-windres -c 65001 gui.rc -O coff -o gui.res
 x86_64-w64-mingw32-gcc -O2 -municode -mconsole -o Kostik.exe kostik_launcher.c console.res -lshell32 -static
 x86_64-w64-mingw32-gcc -O2 -municode -mwindows -DGUI_BUILD -o Kostik-app.exe kostik_launcher.c gui.res -lshell32 -static
 x86_64-w64-mingw32-strip Kostik.exe Kostik-app.exe'
if command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1; then
  ( cd "$W" && sed "s#cd /w#cd $W#" <<<"$BUILD" | bash )
else
  docker image inspect kostik-mingw >/dev/null 2>&1 || docker build -q -t kostik-mingw "$HERE" >/dev/null
  docker run --rm -u "$(id -u):$(id -g)" -v "$W:/w" kostik-mingw bash -c "$BUILD"
fi
cp "$W/Kostik.exe" "$W/Kostik-app.exe" "$OUT/"
rm -rf "$W"
echo "[launcher] $(ls -la "$OUT/Kostik.exe" | awk '{print $5}') байт Kostik.exe, $(ls -la "$OUT/Kostik-app.exe" | awk '{print $5}') байт Kostik-app.exe"
