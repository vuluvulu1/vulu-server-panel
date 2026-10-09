"""Dosya yöneticisi: tüm işlemler sunucu klasörüne kilitlidir (yol kaçışı, sembolik bağlantı ile dışarı çıkma engellenir)."""
import os
import re
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath


class FileError(Exception):
    pass


BAD = re.compile(r'[\x00-\x1f<>:"|?*\\]')
NAME_OK = re.compile(r'^[^\x00-\x1f<>:"/\\|?*]{1,150}$')
WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
PANEL_FILES = {".vulu-jar.json", ".vulu-mods.json", ".vulu-modpack.json", "user_jvm_args.txt"}   # panel yönetir: salt okunur
UPLOAD_DENY = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".scr", ".com", ".msi", ".sh", ".dll", ".so", ".dylib", ".lnk"}
TEXT_EXT = {".txt", ".properties", ".json", ".json5", ".yml", ".yaml", ".toml", ".cfg", ".conf", ".ini", ".log", ".md",
            ".mcmeta", ".csv", ".snbt", ".js", ".zs", ".secrets", ".list", ".xml", ""}
MAX_EDIT = 2 * 2**20          # metin düzenleyicide en fazla 2 MB
MAX_UPLOAD = 512 * 2**20      # tek dosya yükleme sınırı


def rel_parts(rel: str) -> tuple[str, ...]:
    rel = (rel or "").strip().replace("\\", "/").strip("/")
    if not rel:
        return ()
    if len(rel) > 400 or BAD.search(rel):
        raise FileError("Geçersiz yol.")
    parts = PurePosixPath(rel).parts
    for p in parts:
        if p in ("", ".", "..") or p.rstrip(" .") != p or p.split(".")[0].lower() in WIN_RESERVED:
            raise FileError("Geçersiz yol.")
    return parts


def safe_path(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = root.joinpath(*rel_parts(rel)).resolve()     # resolve sembolik bağlantıları da izler → dışarı çıkan bağlantı yakalanır
    if p != root and not p.is_relative_to(root):
        raise FileError("Yol sunucu klasörünün dışına çıkıyor.")
    return p


def to_rel(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix() if p.resolve() != root.resolve() else ""


def check_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_OK.match(name) or name in (".", "..") or name.rstrip(" .") != name or name.split(".")[0].lower() in WIN_RESERVED:
        raise FileError("Geçersiz ad.")
    return name


def is_text(p: Path) -> bool:
    if p.suffix.lower() not in TEXT_EXT:
        return False
    try:
        with open(p, "rb") as f:
            return b"\x00" not in f.read(4096)
    except OSError:
        return False


def protected(root: Path, p: Path) -> bool:
    return p.resolve() == root.resolve() or (p.parent.resolve() == root.resolve() and p.name in PANEL_FILES)


def listing(root: Path, rel: str) -> dict:
    d = safe_path(root, rel)
    if not d.is_dir():
        raise FileError("Klasör bulunamadı.")
    items = []
    for e in d.iterdir():
        try:
            st = e.stat()
            if e.is_symlink() and not e.resolve().is_relative_to(root.resolve()):
                continue                                        # dışarı işaret eden bağlantıyı gösterme
            is_dir = e.is_dir()
            items.append({"name": e.name, "dir": is_dir, "size": 0 if is_dir else st.st_size, "mtime": int(st.st_mtime),
                          "text": (not is_dir) and is_text(e) and st.st_size <= MAX_EDIT, "locked": protected(root, e)})
        except OSError:
            continue
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return {"path": to_rel(root, d), "items": items}


def read_text(root: Path, rel: str) -> dict:
    p = safe_path(root, rel)
    if not p.is_file():
        raise FileError("Dosya bulunamadı.")
    if p.stat().st_size > MAX_EDIT or not is_text(p):
        raise FileError("Bu dosya metin düzenleyicide açılamaz (çok büyük ya da metin değil). İndirerek açabilirsin.")
    return {"path": to_rel(root, p), "content": p.read_text(encoding="utf-8", errors="replace"), "locked": protected(root, p)}


def write_text(root: Path, rel: str, content: str) -> None:
    p = safe_path(root, rel)
    if protected(root, p):
        raise FileError("Bu dosyayı panel yönetir; elle değiştirilemez.")
    if len(content.encode("utf-8")) > MAX_EDIT:
        raise FileError("İçerik çok büyük (en fazla 2 MB).")
    if p.exists() and not (p.is_file() and is_text(p)):
        raise FileError("Yalnızca metin dosyaları düzenlenebilir.")
    if not p.parent.is_dir():
        raise FileError("Klasör bulunamadı.")
    tmp = p.with_name(p.name + ".vulu-tmp")
    tmp.write_text(content, encoding="utf-8", newline="")
    os.replace(tmp, p)


def make_dir(root: Path, rel: str, name: str) -> None:
    d = safe_path(root, rel)
    if not d.is_dir():
        raise FileError("Klasör bulunamadı.")
    t = d / check_name(name)
    if t.exists():
        raise FileError("Bu adla bir dosya ya da klasör zaten var.")
    t.mkdir()


def rename(root: Path, rel: str, new_name: str) -> None:
    p = safe_path(root, rel)
    if not p.exists() or protected(root, p):
        raise FileError("Bu öğe yeniden adlandırılamaz.")
    t = p.parent / check_name(new_name)
    if t.exists():
        raise FileError("Bu adla bir dosya ya da klasör zaten var.")
    p.rename(t)


def _force(func, path, *_):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def delete(root: Path, rel: str) -> None:
    p = safe_path(root, rel)
    if not p.exists() and not p.is_symlink():
        raise FileError("Bulunamadı.")
    if protected(root, p):
        raise FileError("Bu öğe silinemez.")
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=_force)
    else:
        shutil.rmtree(p, onerror=_force)


def upload_target(root: Path, rel: str, filename: str, overwrite: bool) -> Path:
    d = safe_path(root, rel)
    if not d.is_dir():
        raise FileError("Klasör bulunamadı.")
    name = check_name(Path(filename.replace("\\", "/")).name)
    if Path(name).suffix.lower() in UPLOAD_DENY:
        raise FileError(f"Güvenlik nedeniyle bu dosya türü yüklenemez: {Path(name).suffix}")
    t = d / name
    if protected(root, t):
        raise FileError("Bu dosyayı panel yönetir.")
    if t.exists() and (t.is_dir() or not overwrite):
        raise FileError(f"'{name}' zaten var." + ("" if t.is_dir() else " Üzerine yazmak için kutuyu işaretle."))
    return t
