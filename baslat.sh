#!/usr/bin/env bash
# ============================================================
#  vulu panel başlatıcı (Linux / macOS)
#  Kullanım:  bash baslat.sh
#  Python'u bulur, gerisini tools/launcher.py yapar:
#  sanal ortam, paket kurulumu, paneli başlatma.
# ============================================================
cd "$(dirname "$0")" || exit 1

if [ -x .venv/bin/python ]; then
    exec .venv/bin/python tools/launcher.py
fi

for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && \
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        exec "$c" tools/launcher.py
    fi
done

echo
echo " [vulu] Python 3.11 ya da daha yeni bir sürüm bulunamadı."
echo "   Debian/Ubuntu:  sudo apt install python3 python3-venv"
echo "   Fedora:         sudo dnf install python3"
echo "   macOS:          brew install python@3.12"
echo
exit 1
