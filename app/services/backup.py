"""Yedekleme ve geri yükleme.

Yedekler data/backups/<sunucu adı>/ altında .zip olarak tutulur; zip yorumunda (comment) JSON üst veri bulunur.
- "full": tüm sunucu klasörü (logs, crash-reports, cache ve geçici dosyalar hariç)
- "world": yalnızca dünya klasörleri (server.properties'teki level-name, _nether, _the_end)
Sunucu çalışırken alınırsa önce `save-off` + `save-all flush` gönderilir, bitince `save-on`.
Geri yükleme yalnızca sunucu kapalıyken; önce otomatik bir "geri yükleme öncesi" yedeği alınır.
"""
import asyncio
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

from ..db import get_instance
from .jobs import Job, JobError, JobManager
from .properties import read_properties

EXCLUDE_TOP = {"logs", "crash-reports", "cache", ".fabric", "debug"}
SKIP_SUFFIX = (".part", ".vulu-tmp", ".lck")
FILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}_(full|world)_\d{8}-\d{6}(_[a-z0-9-]{1,20})?(~\d{1,2})?\.zip$")
MAX_TOTAL = 64 * 2**30


class BackupError(Exception):
    pass


def world_dirs(folder: Path) -> list[str]:
    level = read_properties(folder / "server.properties").get("level-name", "world").strip() or "world"
    if not re.fullmatch(r"[^\\/:*?\"<>|\x00-\x1f]{1,80}", level) or level in (".", ".."):
        level = "world"
    return [n for n in (level, f"{level}_nether", f"{level}_the_end") if (folder / n).is_dir()]


def _force(func, path, *_):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(p: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=_force)
    else:
        shutil.rmtree(p, onerror=_force)


class BackupManager:
    def __init__(self, base: Path, jobs: JobManager, pm) -> None:
        self.base, self.jobs, self.pm = base, jobs, pm

    def dir_for(self, inst: dict) -> Path:
        return self.base / inst["name"]

    def path_for(self, inst: dict, filename: str) -> Path:
        if not FILE_RE.match(filename or ""):
            raise BackupError("Geçersiz yedek adı.")
        p = self.dir_for(inst) / filename
        if not p.is_file():
            raise BackupError("Yedek bulunamadı.")
        return p

    # ---------- listeleme ----------
    def list_backups(self, inst: dict) -> list[dict]:
        d = self.dir_for(inst)
        out = []
        if d.is_dir():
            for p in d.glob("*.zip"):
                if not FILE_RE.match(p.name):
                    continue
                meta = {}
                try:
                    with zipfile.ZipFile(p) as zf:
                        meta = json.loads(zf.comment.decode("utf-8") or "{}")
                except (zipfile.BadZipFile, ValueError, OSError):
                    meta = {"broken": True}
                st = p.stat()
                out.append({"file": p.name, "size": st.st_size, "created": meta.get("created") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                            "mode": meta.get("mode", "?"), "note": str(meta.get("note", ""))[:80], "mc": meta.get("mc_version"),
                            "files": meta.get("files"), "broken": bool(meta.get("broken")), "_t": st.st_mtime_ns})
        out.sort(key=lambda x: (x["created"], x["_t"]), reverse=True)     # yeniden eskiye (aynı saniyede dosya zamanına göre)
        for x in out:
            del x["_t"]
        return out

    # ---------- yedek alma ----------
    def ensure_create_job(self, inst: dict, mode: str, note: str = "") -> Job:
        return self.jobs.start("backup", f"{inst['name']} yedekleniyor", f"backup-{inst['id']}",
                               lambda j: self._create(j, inst, mode, note))

    async def _save_off(self, iid: int, job: Job) -> bool:
        if self.pm.status(iid) != "running":
            return False
        job.update(1, "save", "Sunucu kaydediliyor (save-all)…")
        q = self.pm.subscribe(iid)
        try:
            await self.pm.send_command(iid, "save-off")
            await self.pm.send_command(iid, "save-all flush")
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    m = await asyncio.wait_for(q.get(), timeout=deadline - time.monotonic())
                except asyncio.TimeoutError:
                    break
                if m.get("type") == "log" and re.search(r"Saved the (game|world)", m.get("line", "")):
                    break
        except Exception:
            pass
        finally:
            self.pm.unsubscribe(iid, q)
        return True

    async def _save_on(self, iid: int) -> None:
        try:
            if self.pm.status(iid) == "running":
                await self.pm.send_command(iid, "save-on")
        except Exception:
            pass

    async def _create(self, job: Job, inst: dict, mode: str, note: str) -> dict:
        if mode not in ("full", "world"):
            raise JobError("Geçersiz yedek türü.")
        folder = Path(inst["path"])
        if not folder.is_dir():
            raise JobError("Sunucu klasörü bulunamadı.")
        paused = await self._save_off(inst["id"], job)
        try:
            res = await asyncio.to_thread(self._zip, job, inst, folder, mode, note, asyncio.get_running_loop())
        finally:
            if paused:
                await self._save_on(inst["id"])
        limit = (get_instance(inst["id"]) or {}).get("backup_limit")
        if limit:                                       # otomatik temizleme açık: en eski yedekleri sil
            res["pruned"] = self.prune_all(inst, int(limit), protect=res["file"])
        return res

    def _collect(self, folder: Path, mode: str) -> list[Path]:
        root = folder.resolve()
        tops = [folder / n for n in world_dirs(folder)] if mode == "world" else \
               [p for p in folder.iterdir() if p.name not in EXCLUDE_TOP]
        files = []
        for t in tops:
            it = [t] if t.is_file() else t.rglob("*")
            for p in it:
                if p.is_symlink() or not p.is_file() or p.name.endswith(SKIP_SUFFIX):
                    continue
                if not p.resolve().is_relative_to(root):
                    continue
                files.append(p)
        return files

    def _zip(self, job: Job, inst: dict, folder: Path, mode: str, note: str, loop) -> dict:
        files = self._collect(folder, mode)
        if not files:
            raise JobError("Yedeklenecek dosya yok" + (" (dünya klasörü bulunamadı; sunucu hiç başlatılmamış olabilir)." if mode == "world" else "."))
        total = sum(p.stat().st_size for p in files) or 1
        if total > MAX_TOTAL:
            raise JobError("Sunucu klasörü çok büyük (64 GB üstü).")
        free = shutil.disk_usage(self.base.parent if self.base.parent.exists() else folder).free
        if free < total * 0.6 + 200 * 2**20:
            raise JobError("Diskte yeterli boş alan yok.")
        d = self.dir_for(inst)
        d.mkdir(parents=True, exist_ok=True)
        raw = note[5:] if note.startswith("auto:") else note
        tag = re.sub(r"[^a-z0-9-]", "", raw.lower().replace(" ", "-").replace("ö", "o").replace("ü", "u").replace("ş", "s").replace("ı", "i").replace("ğ", "g").replace("ç", "c"))[:20]
        name = f"{inst['name']}_{mode}_{time.strftime('%Y%m%d-%H%M%S')}" + (f"_{tag}" if tag else "") + ".zip"
        k = 2
        while (d / name).exists() and k < 100:                 # aynı saniyede iki yedek: üzerine yazma
            name = name[:-4].rsplit("~", 1)[0] + f"~{k}.zip"; k += 1
        out, part = d / name, d / (name + ".part")
        done, n = 0, 0
        try:
            with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
                for p in files:
                    arc = p.relative_to(folder).as_posix()
                    try:
                        zf.write(p, arc)
                    except (PermissionError, OSError):
                        if p.name == "session.lock":
                            continue                           # sunucu çalışırken kilitli olabilir, gerekmez
                        raise
                    n += 1
                    done += p.stat().st_size
                    if n % 25 == 0 or n == len(files):
                        loop.call_soon_threadsafe(job.update, 3 + 95 * done / total, "zip", f"[{n}/{len(files)}] {arc[-80:]}")
                zf.comment = json.dumps({"vulu": 1, "instance": inst["name"], "mode": mode, "note": note[:80],
                                         "mc_version": inst.get("mc_version"), "loader": inst.get("loader"),
                                         "created": time.strftime("%Y-%m-%d %H:%M:%S"), "files": n}).encode("utf-8")
            os.replace(part, out)
        except OSError as e:
            raise JobError(f"Yedek yazılamadı: {e}")
        finally:
            part.unlink(missing_ok=True)
        return {"file": name, "size": out.stat().st_size, "files": n}

    # ---------- geri yükleme ----------
    def ensure_restore_job(self, inst: dict, filename: str) -> Job:
        p = self.path_for(inst, filename)
        return self.jobs.start("restore", f"{inst['name']} geri yükleniyor", f"restore-{inst['id']}",
                               lambda j: self._restore(j, inst, p))

    async def _restore(self, job: Job, inst: dict, zpath: Path) -> dict:
        if self.pm.status(inst["id"]) not in ("stopped", "crashed"):
            raise JobError("Geri yüklemek için önce sunucuyu durdur.")
        job.update(1, "check", "Yedek denetleniyor…")
        meta, names = await asyncio.to_thread(self._inspect, zpath)
        mode = meta.get("mode")
        job.update(5, "safety", "Önce mevcut durumun yedeği alınıyor…")
        folder = Path(inst["path"])
        safety = None
        if any(folder.iterdir()):
            safety = await asyncio.to_thread(self._zip, _Quiet(), inst, folder, mode, "auto:geri-yukleme-oncesi",
                                             asyncio.get_running_loop()) if self._collect(folder, mode) else None
        loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._apply, job, folder, zpath, mode, names, loop)
        return {"mode": mode, "safety": safety["file"] if safety else None}

    @staticmethod
    def _inspect(zpath: Path) -> tuple[dict, list[str]]:
        try:
            with zipfile.ZipFile(zpath) as zf:
                meta = json.loads(zf.comment.decode("utf-8") or "{}")
                names = [i.filename for i in zf.infolist() if not i.is_dir()]
                total = sum(i.file_size for i in zf.infolist())
        except (zipfile.BadZipFile, ValueError, OSError):
            raise JobError("Yedek dosyası bozuk ya da okunamıyor.")
        if meta.get("vulu") != 1 or meta.get("mode") not in ("full", "world"):
            raise JobError("Bu dosya panelin oluşturduğu bir yedek değil.")
        if total > MAX_TOTAL:
            raise JobError("Yedek çok büyük.")
        for n in names:
            pp = PurePosixPath(n)
            if pp.is_absolute() or any(x in ("", ".", "..") for x in pp.parts) or ":" in n or "\\" in n:
                raise JobError("Yedek güvensiz dosya yolları içeriyor; geri yüklenmedi.")
        return meta, names

    def _apply(self, job: Job, folder: Path, zpath: Path, mode: str, names: list[str], loop) -> None:
        root = folder.resolve()
        # 1) değiştirilecek içeriği kaldır
        if mode == "world":
            targets = {PurePosixPath(n).parts[0] for n in names} | set(world_dirs(folder))
        else:
            targets = {p.name for p in folder.iterdir() if p.name not in EXCLUDE_TOP}
        for t in targets:
            p = folder / t
            if p.resolve().parent != root:
                continue
            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.is_dir():
                _rmtree(p)
        # 2) çıkar
        with zipfile.ZipFile(zpath) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            for k, i in enumerate(infos, 1):
                dest = (folder / i.filename).resolve()
                if not dest.is_relative_to(root):
                    raise JobError("Güvensiz yol.")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(i) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                if k % 25 == 0 or k == len(infos):
                    loop.call_soon_threadsafe(job.update, 10 + 88 * k / len(infos), "extract", f"[{k}/{len(infos)}] {i.filename[-80:]}")

    def prune_all(self, inst: dict, keep: int, protect: str | None = None) -> int:
        """Sunucunun tüm yedeklerinden en yeni `keep` tanesini bırakıp eskileri siler (az önce alınan yedek korunur)."""
        items = [b for b in self.list_backups(inst) if b["file"] != protect]       # yeniden eskiye
        removed = 0
        for b in items[max(0, keep - (1 if protect else 0)):]:
            try:
                (self.dir_for(inst) / b["file"]).unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def prune(self, inst: dict, note: str, keep: int) -> int:
        """Aynı notla (ör. zamanlanmış) alınmış yedeklerden en yeni `keep` tanesi dışındakileri siler. Elle alınanlara dokunmaz."""
        same = [b for b in self.list_backups(inst) if b["note"] == note and not b["broken"]]
        removed = 0
        for b in same[max(1, keep):]:                   # liste yeniden eskiye sıralı
            try:
                (self.dir_for(inst) / b["file"]).unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def delete(self, inst: dict, filename: str) -> None:
        self.path_for(inst, filename).unlink()


class _Quiet:
    """Güvenlik yedeği sırasında ilerleme çubuğunu karıştırmamak için boş iş nesnesi."""
    def update(self, *a, **k) -> None:
        pass
