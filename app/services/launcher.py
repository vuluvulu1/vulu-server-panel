"""Bir instance'ı başlatma akışı. Eksik parçaları (Java, yükleyici jar'ı) sırayla kurar,
ilerlemeyi konsola yayınlar, sonra sunucuyu başlatır."""
import asyncio
from pathlib import Path

from ..db import update_instance
from .java_manager import JavaManager
from .jobs import Job
from .modpack import read_pack_info
from .modrinth import LOADER_FILTER, ModrinthError, read_mods_info
from .paper import PaperError, read_jar_info
from .process import ProcessBackend, ProcessError
from .profiles import get_profile
from .properties import prepare_runtime

BUSY = ("preparing", "starting", "running", "stopping")


class InstanceLauncher:
    def __init__(self, pm: ProcessBackend, java: JavaManager, installers: dict, mods, modpacks) -> None:
        self.pm, self.java, self.installers, self.mods, self.modpacks = pm, java, installers, mods, modpacks
        self._prep: dict[int, asyncio.Task] = {}

    # ---------- ne eksik? ----------
    def _needs_java(self, inst: dict) -> bool:
        major = inst.get("java_major")
        return bool(major) and not self.java.find(major)

    @staticmethod
    def _jar_missing(inst: dict) -> bool:
        return not (Path(inst["path"]) / inst["jar_file"]).is_file()

    def _installer(self, inst: dict):
        """Bu sunucuyu kurabilen yükleyici (yoksa None)."""
        if not inst.get("mc_version"):
            return None
        return self.installers.get(inst.get("loader"))

    def _needs_loader(self, inst: dict, force: bool = False) -> bool:
        mgr = self._installer(inst)
        if not mgr:
            return False
        if force:
            return True
        if getattr(mgr, "kind", "jar") == "installer":       # Forge/NeoForge: kurulu işareti (.vulu-jar.json)
            info = read_jar_info(Path(inst["path"]))
            return not (info and info.get("type") == inst["loader"] and info.get("version") == inst["mc_version"])
        return self._jar_missing(inst)

    @staticmethod
    def _profile_mods(inst: dict):
        """(profil, mod listesi) — yalnızca Modrinth kurulumu desteklenen yükleyicilerde."""
        prof = get_profile(inst.get("profile_id"))
        ok = prof and prof.mods and inst.get("mc_version") and inst.get("loader") in LOADER_FILTER
        return (prof, prof.mods) if ok else (None, [])

    @staticmethod
    def _needs_modpack(inst: dict) -> bool:
        if not inst.get("modpack_slug"):
            return False
        info = read_pack_info(Path(inst["path"]))
        return not (info and info.get("version_id") == inst.get("modpack_version"))

    def _needs_mods(self, inst: dict) -> bool:
        _, mods = self._profile_mods(inst)
        if not mods:
            return False
        info = read_mods_info(Path(inst["path"]))
        return not (info and info.get("requested") == sorted(mods) and info.get("mc") == inst["mc_version"]
                    and info.get("loader") == inst["loader"])

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
        if self.mods.jobs.find_running(f"mods-{iid}"):
            raise ProcessError("Mod kurulumu sürüyor, bitmesini bekle.")
        if not (self._needs_java(inst) or self._needs_loader(inst) or self._needs_mods(inst) or self._needs_modpack(inst)):
            await self._launch(inst)
            return {"preparing": False}
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=True))
        return {"preparing": True}

    async def update_jar(self, inst: dict) -> dict:
        """Jar'ı en yeni build'e günceller (Paper/Fabric). Sunucu kapalıyken çalışır."""
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError("Güncellemek için önce sunucuyu durdur.")
        mgr = self._installer(inst)
        if not mgr:
            raise ProcessError("Bu sunucunun jar'ı panel tarafından yönetilmiyor (yalnızca Paper ve Fabric).")
        try:
            latest = await mgr.resolve(inst["mc_version"])
        except PaperError as e:
            raise ProcessError(str(e))
        cur = read_jar_info(Path(inst["path"]))
        if cur and cur.get("build") == latest["build"] and not self._needs_loader(inst):
            return {"updated": False, "message": f"Zaten güncel ({latest['label']})."}
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=False, force_jar=True))
        return {"updated": True}

    async def update_mods(self, inst: dict) -> dict:
        """Profildeki modları en yeni uyumlu sürümlere günceller. Sunucu kapalıyken çalışır."""
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError("Güncellemek için önce sunucuyu durdur.")
        if not self._profile_mods(inst)[1]:
            raise ProcessError("Bu sunucunun profilinde Modrinth mod listesi yok.")
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=False, force_mods=True))
        return {"updated": True}

    async def _follow(self, iid: int, job: Job) -> None:
        async for snap in job.watch():
            self.pm.emit(iid, snap)
            if snap["status"] != "running":
                break

    async def _prepare(self, inst: dict, *, start: bool, force_jar: bool = False, force_mods: bool = False) -> None:
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

            pack, pin = None, None
            if self._needs_modpack(inst):                      # 1) modpack paketini indir/oku → tam yükleyici sürümü
                try:
                    info = await self.modpacks.version_info(inst["modpack_slug"], inst["modpack_version"])
                except ModrinthError as e:
                    raise ProcessError(str(e))
                pm.log(iid, f"[panel] Modpack indiriliyor: {info['title']} {info['version_number']}…")
                pj = self.modpacks.ensure_pack_job(iid, info)
                await self._follow(iid, pj)
                if pj.status == "error":
                    raise ProcessError(f"Modpack alınamadı: {pj.error}")
                pack = {**info, **pj.result}
                pin = pack["loader_version"]

            mgr = self._installer(inst)
            if mgr and self._needs_loader(inst, force_jar):
                name, v = inst["loader"].capitalize(), inst["mc_version"]
                pm.log(iid, f"[panel] {name} {v} indiriliyor…")
                job = mgr.ensure_cached_job(v, pin)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError(f"{name} indirilemedi: {job.error}")
                info = job.result
                if getattr(mgr, "kind", "jar") == "installer":
                    pm.log(iid, f"[panel] {info['label']} kuruluyor (internetten dosyalar iner, birkaç dakika sürebilir)…")
                    ij = mgr.ensure_install_job(iid, info, Path(inst["path"]), self._with_java(inst)["java_path"])
                    await self._follow(iid, ij)
                    if ij.status == "error":
                        raise ProcessError(f"{name} kurulamadı: {ij.error}")
                    update_instance(iid, **ij.result["db"])
                    inst = {**inst, **ij.result["db"]}
                    pm.log(iid, f"[panel] {info['label']} kuruldu.")
                else:
                    await asyncio.to_thread(mgr.install, info, Path(inst["path"]), inst["jar_file"])
                    pm.log(iid, f"[panel] {info['label']} → {inst['jar_file']} hazır.")
                if not info["stable"]:
                    pm.log(iid, "[panel] Uyarı: bu sürüm için kararlı (STABLE) build yok; deneysel build kullanıldı.")
                if inst["loader"] == "fabric":
                    pm.log(iid, "[panel] Not: Fabric ilk açılışta Minecraft sunucusunu ve kütüphaneleri indirir, bu biraz sürer.")

            if pack:                                           # 3) modpack dosyaları + ayarlar
                pm.log(iid, f"[panel] {pack['title']} dosyaları kuruluyor…")
                ij = self.modpacks.ensure_install_job(iid, Path(inst["path"]), pack)
                await self._follow(iid, ij)
                if ij.status == "error":
                    raise ProcessError(f"Modpack kurulamadı: {ij.error}")
                r = ij.result
                for w in r.get("warnings", []):
                    pm.log(iid, f"[panel] Uyarı: {w}")
                pm.log(iid, f"[panel] {pack['title']} kuruldu: {r['files']} dosya, {r['skipped']} istemci dosyası atlandı, {r['overrides']} ayar dosyası.")

            _, mod_list = self._profile_mods(inst)
            if mod_list and (force_mods or self._needs_mods(inst)):
                kind = "eklenti" if inst["loader"] == "paper" else "mod"
                pm.log(iid, f"[panel] Modrinth'ten {len(mod_list)} {kind} (ve bağımlılıkları) kuruluyor…")
                job = self.mods.ensure_install_job(iid, Path(inst["path"]), inst["mc_version"], inst["loader"], mod_list)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError(f"{kind.capitalize()}lar kurulamadı: {job.error}")
                for w in job.result.get("warnings", []):
                    pm.log(iid, f"[panel] Uyarı: {w}")
                pm.log(iid, f"[panel] {job.result['count']} {kind} hazır.")

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
