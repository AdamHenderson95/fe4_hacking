#!/bin/bash
# Build BuilderOfTheHolyWar.exe on Linux with Wine.
#   one-time setup:
#     apt-get install wine64
#     python-build-standalone 3.12.7 (x86_64-pc-windows-msvc-install_only) unpacked to $WINPY
#     wine $WINPY/python.exe -m pip install pyinstaller==6.11.1   (needs --cert/--proxy behind a proxy)
#   Python under Wine can't start with stdout redirected to a file: send it to /dev/null.
set -e
WINPY=${WINPY:-/root/winpy/python}
export WINEPREFIX=${WINEPREFIX:-/root/wine/pfx} WINEDEBUG=-all
KIT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$KIT/dist}
B=$(mktemp -d)
cp -r "$KIT"/*.py "$KIT"/studio "$KIT"/dev "$KIT"/README.html "$KIT"/README.md "$KIT"/map_editor.html "$B"/
find "$B" -name __pycache__ -prune -exec rm -rf {} \;
cd "$B"
HI=""
for f in *.py; do m=${f%.py}; [ "$m" != fe4editor ] && HI="$HI --hidden-import $m"; done
wine "$WINPY/python.exe" -m PyInstaller --noconfirm --onefile --windowed --name BuilderOfTheHolyWar \
  --add-data "dev;dev" --add-data "studio;studio" --add-data "README.html;." --add-data "README.md;." \
  --add-data "map_editor.html;." $HI fe4editor.py < /dev/null > /dev/null 2>&1
mkdir -p "$OUT"
cp dist/BuilderOfTheHolyWar.exe "$OUT"/
rm -rf "$B"
echo "built $OUT/BuilderOfTheHolyWar.exe"
