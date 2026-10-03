"""Bir instance'ı başlatma akışı. Eksik parçaları (Java, Paper jar'ı) sırayla kurar,
ilerlemeyi konsola yayınlar, sonra sunucuyu başlatır."""
import asyncio
from pathlib import Path

from .java_manager import JavaManager
from .jobs import Job
from .paper import PaperError, PaperManager, read_jar_info
from .properties import prepare_runtime
from .process import ProcessBackend, ProcessError

BUSY = ("preparing", "starting", "running", "stopping")


class InstanceLauncher:
    def __init__(self, pm: ProcessBackend, java: JavaManager, paper: PaperManager) -> None:
        self.pm = pm
        self.java = java
        self.paper = paper
        self._prep: dict[int, asyncio.Task] = {}

    # ---------- ne eksik? ----------
    def _needs_java(self, inst: dict) -> bool:
        major = inst.get("java_major")
        return bool(major) and not self.java.find(major)

    @staticmethod
    def _jar_missing(inst: dict) -> bool:
        return not (Path(inst["path"]) / inst["jar_file"]).is_file()

    def _needs_paper(self, inst: dict) -> bool:
        return inst.get("loader") == "paper" and bool(inst.get("mc_version")) and self._jar_missing(inst)

    def _with_java(self, inst: dict) -> dict:
        major = inst.get("java_major")
        exe = self.java.find(major) if major else None
        return {**inst, "java_path": str(exe)} if exe else inst

    async def _launch(self, inst: dict) -> None:
        try:
            inst = prepare_runtime(inst)      # server-port + RCON'u server.properties'e yazar
        except (OSError, ValueError) as e:
            raise ProcessError(f"server.properties hazırlanamadı: {e}")
        await self.pm.start(self._with_java(inst))

    # ---------- başlat ----------
    async def start(self, inst: dict) -> dict:
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError("Sunucu zaten çalışıyor ya da hazırlanıyor.")
        if not (self._needs_java(inst) or self._needs_paper(inst)):
            await self._launch(inst)
            return {"preparing": False}
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=True))
        return {"preparing": True}

    async def update_jar(self, inst: dict) -> dict:
        """Paper jar'ını en yeni (tercihen STABLE) build'e günceller. Sunucu kapalıyken çalışır."""
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError("Güncellemek için önce sunucuyu durdur.")
        if inst.get("loader") != "paper" or not inst.get("mc_version"):
            raise ProcessError("Bu sunucu Paper olarak ayarlı değil.")
        try:
            latest = await self.paper.resolve(inst["mc_version"])
        except PaperError as e:
            raise ProcessError(str(e))
        cur = read_jar_info(Path(inst["path"]))
        if cur and cur.get("build") == latest["build"] and not self._jar_missing(inst):
            return {"updated": False, "message": f"Zaten güncel (Paper {latest['version']} build #{latest['build']})."}
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=False, force_jar=True))
        return {"updated": True}

    async def _follow(self, iid: int, job: Job) -> None:
        async for snap in job.watch():
            self.pm.emit(iid, snap)
            if snap["status"] != "running":
                break

    async def _prepare(self, inst: dict, *, start: bool, force_jar: bool = False) -> None:
        iid, pm = inst["id"], self.pm
        try:
            pm.emit(iid, {"type": "clear"})

            major = inst.get("java_major")
            if major and not self.java.find(major):
                pm.log(iid, f"[panel] Java {major} kurulu değil, indiriliyor…")
                job = self.java.ensure_job(major)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError(f"Java {major} kurulamadı: {job.error}")
                if not self.java.find(major):
                    raise ProcessError(f"Java {major} kurulumu tamamlandı ama bulunamadı.")
                pm.log(iid, f"[panel] Java {major} hazır.")

            if inst.get("loader") == "paper" and inst.get("mc_version") and (force_jar or self._jar_missing(inst)):
                v = inst["mc_version"]
                pm.log(iid, f"[panel] Paper {v} indiriliyor…")
                job = self.paper.ensure_cached_job(v)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError(f"Paper indirilemedi: {job.error}")
                info = job.result
                await asyncio.to_thread(self.paper.install, info, Path(inst["path"]), inst["jar_file"])
                pm.log(iid, f"[panel] Paper {v} (build #{info['build']}, {info['channel']}) → {inst['jar_file']} hazır.")
                if not info["stable"]:
                    pm.log(iid, "[panel] Uyarı: bu sürüm için kararlı (STABLE) build yok; deneysel build kullanıldı.")

            pm.emit(iid, {"type": "progress_end"})
            if start:
                await self._launch(inst)
            else:
                pm.set_status(iid, "stopped")
        except asyncio.CancelledError:
            pm.emit(iid, {"type": "progress_end"})
            pm.log(iid, "[panel] Hazırlık iptal edildi.")
            pm.set_status(iid, "stopped")
            raise
        except ProcessError as e:
            pm.emit(iid, {"type": "progress_end"})
            pm.notify_error(iid, str(e))
            pm.set_status(iid, "stopped")
        finally:
            self._prep.pop(iid, None)

    # ---------- durdur / öldür / yeniden başlat ----------
    async def stop(self, iid: int, timeout: int = 60) -> None:
        task = self._prep.get(iid)
        if task and not task.done():        # hazırlık sırasında "Durdur" = iptal
            task.cancel()
            await asyncio.wait({task})
            return
        await self.pm.stop(iid, timeout)

    async def kill(self, iid: int) -> None:
        task = self._prep.get(iid)
        if task and not task.done():
            await self.stop(iid)
            return
        await self.pm.kill(iid)

    async def restart(self, inst: dict) -> None:
        await self.stop(inst["id"])
        await self.start(inst)

    async def shutdown(self) -> None:
        for t in list(self._prep.values()):
            t.cancel()
        if self._prep:
            await asyncio.wait(list(self._prep.values()))
