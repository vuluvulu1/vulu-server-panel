"""Sistem bakımı: disk kullanımı, kurulu Java sürümleri, indirme önbelleği."""
import os
import re
import shutil
import stat
import sys
from pathlib import Path

from ..config import BACKUPS_DIR, BASE_DIR, CACHE_DIR, INSTANCES_DIR, RUNTIMES_DIR

CACHE_KINDS = {"vanilla": "Vanilla sunucu jar'ları", "paper": "Paper jar'ları", "fabric": "Fabric jar'ları", "forge": "Forge kurucuları",
               "neoforge": "NeoForge kurucuları", "modpacks": "Modpack paketleri (.mrpack)"}


def dir_size(p: Path) -> int:
    total = 0
    if not p.exists():
        return 0
    for root, dirs, files in os.walk(p, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def _force(func, path, *_):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(p: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=_force)
    else:
        shutil.rmtree(p, onerror=_force)


def disk_overview() -> dict:
    du = shutil.disk_usage(BASE_DIR)
    parts = {"instances": dir_size(INSTANCES_DIR), "backups": dir_size(BACKUPS_DIR),
             "runtimes": dir_size(RUNTIMES_DIR), "cache": dir_size(CACHE_DIR)}
    return {"total": du.total, "free": du.free, "used": du.used, "parts": parts}


def cache_overview() -> list[dict]:
    out = []
    for kind, label in CACHE_KINDS.items():
        d = CACHE_DIR / kind
        files = [f for f in d.iterdir() if f.is_file()] if d.is_dir() else []
        out.append({"kind": kind, "label": label, "files": len(files), "size": sum(f.stat().st_size for f in files)})
    return out


def clear_cache(kind: str) -> int:
    if kind not in CACHE_KINDS:
        raise ValueError("Bilinmeyen önbellek türü.")
    d = (CACHE_DIR / kind).resolve()
    if d.parent != CACHE_DIR.resolve() or not d.is_dir():
        return 0
    n = 0
    for f in d.iterdir():
        if f.is_file() and not f.is_symlink():
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def java_dir(major: int) -> Path:
    d = (RUNTIMES_DIR / f"java-{int(major)}").resolve()
    if d.parent != RUNTIMES_DIR.resolve() or not re.fullmatch(r"java-\d{1,3}", d.name):
        raise ValueError("Geçersiz Java sürümü.")
    return d
