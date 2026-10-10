"""Bir instance'ı başlatma akışı. Eksik parçaları (Java, yükleyici jar'ı) sırayla kurar,
ilerlemeyi konsola yayınlar, sonra sunucuyu başlatır."""
import asyncio
from pathlib import Path

import psutil

from ..db import update_instance
from .java_manager import JavaManager
from .jobs import Job
from .modpack import read_pack_info
from .modcheck import check_mods, summary_lines
from .modrinth import LOADER_FILTER, ModrinthError, read_mods_info, target_dir
from .paper import PaperError, read_jar_info
from .process import ProcessBackend, ProcessError
from .profiles import get_profile
from .properties import prepare_runtime
from ..i18n import _t

BUSY = ("preparing", "starting", "running", "stopping")


class InstanceLauncher:
    def __init__(self, pm: ProcessBackend, java: JavaManager, installers: dict, mods, modpacks, minecraft=None) -> None:
        self.pm, self.java, self.installers, self.mods, self.modpacks = pm, java, installers, mods, modpacks
        self.minecraft = minecraft
        self._prep: dict[int, asyncio.Task] = {}
        self._notes: dict[int, str] = {}     # hazırlık başlarken konsola yazılacak panel notu

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
            raise ProcessError(_t('server.properties hazırlanamadı: {e}', e=e))
        warn: list[str] = []
        if inst.get("loader") in ("fabric", "quilt", "forge", "neoforge"):     # eksik bağımlılık / istemci modu uyarısı
            try:
                res = await asyncio.to_thread(check_mods, Path(inst["path"]) / target_dir(inst["loader"]))
                warn = summary_lines(res)
            except Exception:
                warn = []                                                       # denetim başlatmayı asla engellemez
        await self.pm.start(self._with_java(inst))
        for line in warn:
            self.pm.log(inst["id"], line)

    # ---------- başlat ----------
    async def start(self, inst: dict) -> dict:
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError(_t("Sunucu zaten çalışıyor ya da hazırlanıyor."))
        if self.mods.jobs.find_running(f"restore-{iid}"):
            raise ProcessError(_t("Geri yükleme sürüyor, bitmesini bekle."))
        if self.mods.jobs.find_running(f"upgrade-{iid}"):
            raise ProcessError(_t("Sürüm değiştirme sürüyor, bitmesini bekle."))
        if self.mods.jobs.find_running(f"mods-{iid}"):
            raise ProcessError(_t("Mod kurulumu sürüyor, bitmesini bekle."))
        self._check_memory(inst)
        inst = await self._fix_java(inst)
        if iid not in self._notes and not (self._needs_java(inst) or self._needs_loader(inst) or self._needs_mods(inst) or self._needs_modpack(inst)):
            await self._launch(inst)
            return {"preparing": False}
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=True))
        return {"preparing": True}

    async def _fix_java(self, inst: dict) -> dict:
        """Panelin yönettiği Java, Minecraft sürümünün istediğinden eskiyse sunucu hiç açılmaz
        (UnsupportedClassVersionError). Bu durumda gereken sürüme geçeriz. Özel Java yoluna dokunulmaz."""
        major, ver = inst.get("java_major"), inst.get("mc_version")
        if not (major and ver and self.minecraft):
            return inst
        try:
            need = (await self.minecraft.java_for(ver, inst.get("loader") or "vanilla"))["major"]
        except Exception:
            return inst                                      # belirlenemedi: olduğu gibi dene
        if int(major) >= need:
            return inst
        update_instance(inst["id"], java_major=need)
        self._notes[inst["id"]] = (_t("[panel] Minecraft {ver} en az Java {need} istiyor; sunucu Java {major} ile ayarlıydı. Java {need}'e geçildi.", ver=ver, need=need, major=major))
        return {**inst, "java_major": need}

    @staticmethod
    def _check_memory(inst: dict) -> None:
        """Java, -Xms = -Xmx ve AlwaysPreTouch ile belleğin tamamını başta ister; yetmezse hemen çöker.
        Başlatmadan önce boş belleği denetleyip anlaşılır bir mesaj veririz."""
        need_mb = int(inst["ram_mb"]) + 512                     # yığın + Java'nın kendi payı (kaba alt sınır)
        free_mb = psutil.virtual_memory().available // (1024 * 1024)
        if free_mb < need_mb:
            raise ProcessError(
                _t('Bilgisayarda yeterli boş bellek yok: {v0:.1f} GB boş, bu sunucu en az {v1:.1f} GB istiyor (RAM ayarı {v2:.0f} GB + Java payı). Diğer programları kapat ya da sunucunun RAM ayarını düşür.', v0=free_mb / 1024, v1=need_mb / 1024, v2=int(inst['ram_mb']) / 1024)
            )

    async def update_jar(self, inst: dict) -> dict:
        """Jar'ı en yeni build'e günceller (Paper/Fabric). Sunucu kapalıyken çalışır."""
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError(_t("Güncellemek için önce sunucuyu durdur."))
        mgr = self._installer(inst)
        if not mgr:
            raise ProcessError(_t("Bu sunucunun jar'ı panel tarafından yönetilmiyor (yalnızca Paper ve Fabric)."))
        try:
            latest = await mgr.resolve(inst["mc_version"])
        except PaperError as e:
            raise ProcessError(str(e))
        cur = read_jar_info(Path(inst["path"]))
        if cur and cur.get("build") == latest["build"] and not self._needs_loader(inst):
            return {"updated": False, "message": _t('Zaten güncel ({label}).', label=latest['label'])}
        self.pm.set_status(iid, "preparing")
        self._prep[iid] = asyncio.create_task(self._prepare(inst, start=False, force_jar=True))
        return {"updated": True}

    async def update_mods(self, inst: dict) -> dict:
        """Profildeki modları en yeni uyumlu sürümlere günceller. Sunucu kapalıyken çalışır."""
        iid = inst["id"]
        if self.pm.status(iid) in BUSY:
            raise ProcessError(_t("Güncellemek için önce sunucuyu durdur."))
        if not self._profile_mods(inst)[1]:
            raise ProcessError(_t("Bu sunucunun profilinde Modrinth mod listesi yok."))
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
            if note := self._notes.pop(iid, None):
                pm.log(iid, note)
                pm.emit(iid, {"type": "meta", "java_major": int(inst["java_major"])})   # sayfa başlığındaki Java bilgisi

            major = inst.get("java_major")
            if major and not self.java.find(major):
                pm.log(iid, _t('[panel] Java {major} kurulu değil, indiriliyor…', major=major))
                job = self.java.ensure_job(major)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError(_t('Java {major} kurulamadı: {error}', major=major, error=job.error))
                if not self.java.find(major):
                    raise ProcessError(_t('Java {major} kurulumu tamamlandı ama bulunamadı.', major=major))
                pm.log(iid, _t('[panel] Java {major} hazır.', major=major))

            pack, pin = None, None
            if self._needs_modpack(inst):                      # 1) modpack paketini indir/oku → tam yükleyici sürümü
                try:
                    info = await self.modpacks.version_info(inst["modpack_slug"], inst["modpack_version"])
                except ModrinthError as e:
                    raise ProcessError(str(e))
                pm.log(iid, _t('[panel] Modpack indiriliyor: {title} {version_number}…', title=info['title'], version_number=info['version_number']))
                pj = self.modpacks.ensure_pack_job(iid, info)
                await self._follow(iid, pj)
                if pj.status == "error":
                    raise ProcessError(_t('Modpack alınamadı: {error}', error=pj.error))
                pack = {**info, **pj.result}
                pin = pack["loader_version"]

            mgr = self._installer(inst)
            if mgr and self._needs_loader(inst, force_jar):
                name, v = inst["loader"].capitalize(), inst["mc_version"]
                pm.log(iid, _t('[panel] {name} {v} indiriliyor…', name=name, v=v))
                job = mgr.ensure_cached_job(v, pin)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError(_t('{name} indirilemedi: {error}', name=name, error=job.error))
                info = job.result
                if getattr(mgr, "kind", "jar") == "installer":
                    pm.log(iid, _t('[panel] {label} kuruluyor (internetten dosyalar iner, birkaç dakika sürebilir)…', label=info['label']))
                    ij = mgr.ensure_install_job(iid, info, Path(inst["path"]), self._with_java(inst)["java_path"])
                    await self._follow(iid, ij)
                    if ij.status == "error":
                        raise ProcessError(_t('{name} kurulamadı: {error}', name=name, error=ij.error))
                    update_instance(iid, **ij.result["db"])
                    inst = {**inst, **ij.result["db"]}
                    pm.log(iid, _t('[panel] {label} kuruldu.', label=info['label']))
                else:
                    await asyncio.to_thread(mgr.install, info, Path(inst["path"]), inst["jar_file"])
                    pm.log(iid, _t('[panel] {label} → {jar_file} hazır.', label=info['label'], jar_file=inst['jar_file']))
                if not info["stable"]:
                    pm.log(iid, _t("[panel] Uyarı: bu sürüm için kararlı (STABLE) build yok; deneysel build kullanıldı."))
                if inst["loader"] == "fabric":
                    pm.log(iid, _t("[panel] Not: Fabric ilk açılışta Minecraft sunucusunu ve kütüphaneleri indirir, bu biraz sürer."))

            if pack:                                           # 3) modpack dosyaları + ayarlar
                pm.log(iid, _t('[panel] {title} dosyaları kuruluyor…', title=pack['title']))
                ij = self.modpacks.ensure_install_job(iid, Path(inst["path"]), pack)
                await self._follow(iid, ij)
                if ij.status == "error":
                    raise ProcessError(_t('Modpack kurulamadı: {error}', error=ij.error))
                r = ij.result
                for w in r.get("warnings", []):
                    pm.log(iid, _t('[panel] Uyarı: {w}', w=w))
                pm.log(iid, _t('[panel] {title} kuruldu: {files} dosya, {skipped} istemci dosyası atlandı, {overrides} ayar dosyası.', title=pack['title'], files=r['files'], skipped=r['skipped'], overrides=r['overrides']))

            _, mod_list = self._profile_mods(inst)
            if mod_list and (force_mods or self._needs_mods(inst)):
                paper = inst["loader"] == "paper"
                pm.log(iid, (_t("[panel] Modrinth'ten {n} eklenti (ve bağımlılıkları) kuruluyor…", n=len(mod_list)) if paper
                             else _t("[panel] Modrinth'ten {n} mod (ve bağımlılıkları) kuruluyor…", n=len(mod_list))))
                job = self.mods.ensure_install_job(iid, Path(inst["path"]), inst["mc_version"], inst["loader"], mod_list)
                await self._follow(iid, job)
                if job.status == "error":
                    raise ProcessError((_t('Eklentiler kurulamadı: {error}', error=job.error) if paper else _t('Modlar kurulamadı: {error}', error=job.error)))
                for w in job.result.get("warnings", []):
                    pm.log(iid, _t('[panel] Uyarı: {w}', w=w))
                pm.log(iid, (_t('[panel] {count} eklenti hazır.', count=job.result['count']) if paper else _t('[panel] {count} mod hazır.', count=job.result['count'])))

            pm.emit(iid, {"type": "progress_end"})
            if start:
                await self._launch(inst)
            else:
                pm.set_status(iid, "stopped")
        except asyncio.CancelledError:
            pm.emit(iid, {"type": "progress_end"})
            pm.log(iid, _t("[panel] Hazırlık iptal edildi."))
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
        iid = inst["id"]
        await self.stop(iid)
        for _ in range(100):                     # süreç bitti ama "durdu" durumu bir an sonra yazılıyor: bekle
            if self.pm.status(iid) in ("stopped", "crashed"):
                break
            await asyncio.sleep(0.1)
        await self.start(inst)

    async def shutdown(self) -> None:
        for t in list(self._prep.values()):
            t.cancel()
        if self._prep:
            await asyncio.wait(list(self._prep.values()))
