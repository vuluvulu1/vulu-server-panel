"""Release paketi oluşturur:  python tools/build_release.py [v0.1.0]

dist/vulu-panel-v<sürüm>.zip dosyasını üretir. İçinde yalnızca kullanıcının ihtiyaç duyduğu dosyalar
vardır (geliştirme dosyaları, data/, instances/, runtimes/, .env ve .venv asla girmez).
Etiket verilirse app/__init__.py'deki sürümle aynı olmalıdır; GitHub Actions bunu her release'te çalıştırır.
"""
from __future__ import annotations

import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "vulu-panel"                                   # zip içindeki klasör adı

INCLUDE_FILES = ["baslat.bat", "baslat.sh", "run.py", "requirements.txt", ".env.example", "README.md", "LICENSE",
                 "tools/launcher.py"]
INCLUDE_DIRS = ["app", "profiles"]
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIX = {".pyc", ".pyo", ".log"}


def version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "app" / "__init__.py").read_text(encoding="utf-8"))
    if not m:
        sys.exit("app/__init__.py içinde __version__ bulunamadı.")
    return m.group(1)


def files() -> list[Path]:
    out = [ROOT / f for f in INCLUDE_FILES]
    for d in INCLUDE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and not (SKIP_PARTS & set(p.parts)) and p.suffix not in SKIP_SUFFIX:
                out.append(p)
    missing = [str(p.relative_to(ROOT)) for p in out if not p.is_file()]
    if missing:
        sys.exit("Eksik dosyalar: " + ", ".join(missing))
    return out


def main() -> None:
    ver = version()
    if len(sys.argv) > 1:
        tag = sys.argv[1].strip()
        if tag.lstrip("vV") != ver:
            sys.exit(f"Etiket ({tag}) ile app/__init__.py'deki sürüm ({ver}) uyuşmuyor. "
                     f"__version__'ı güncelleyip commit'le ya da etiketi v{ver} yap.")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / f"vulu-panel-v{ver}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files():
            rel = p.relative_to(ROOT).as_posix()
            data = p.read_bytes()
            if p.suffix == ".bat":                   # Windows betiği CRLF olmalı
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            elif p.suffix == ".sh":                  # kabuk betiği LF olmalı
                data = data.replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo(f"{TOP}/{rel}", date_time=time.localtime()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if p.suffix == ".sh" else 0o644) << 16
            z.writestr(info, data)
    print(f"{target.relative_to(ROOT)}  ({target.stat().st_size / 1048576:.2f} MB)")


if __name__ == "__main__":
    main()
