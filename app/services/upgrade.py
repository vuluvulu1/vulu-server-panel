"""Minecraft sürümünü değiştirme (yükseltme / bilinçli düşürme).

Sıra: (sunucu kapalı) → zorunlu tam yedek → yeni sürümü yükleyicide doğrula → Java'yı yeniden belirle →
eski yükleyici kaydını/jar'ını kaldır (yeni sürüm ilk başlatmada kurulur) → Modrinth modlarını yeni sürüme göre güncelle.
Modpack sunucularında yapılmaz (sürümü modpack belirler). Elle eklenen modlara dokunulmaz (uyarı verilir).
"""
import re
from pathlib import Path

from ..db import get_instance, update_instance
from .jobs import Job, JobError
from .minecraft import McError
from .modrinth import read_mods_info, target_dir
from .paper import INFO_FILE, PaperError
from .profiles import get_profile
from ..i18n import _t

NOTE = "auto:surum-oncesi"


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


class Upgrader:
    def __init__(self, installers: dict, minecraft, backups, mods, jobs, pm) -> None:
        self.installers, self.mc, self.backups, self.mods, self.jobs, self.pm = installers, minecraft, backups, mods, jobs, pm

    def ensure_job(self, inst: dict, new_ver: str) -> Job:
        return self.jobs.start("upgrade", _t('{name}: Minecraft {new_ver} sürümüne geçiliyor', name=inst['name'], new_ver=new_ver), f"upgrade-{inst['id']}",
                               lambda j: self._run(j, inst, new_ver))

    async def check(self, inst: dict, new_ver: str) -> dict:
        """Ön kontrol (hata varsa JobError). Arayüz onay penceresi için özet döndürür."""
        if inst.get("modpack_slug"):
            raise JobError(_t("Bu sunucu bir modpack'ten kuruldu; sürümü modpack belirler, buradan değiştirilemez."))
        loader = inst.get("loader") or "vanilla"
        mgr = self.installers.get(loader)
        if not mgr:
            raise JobError(_t("Bu yükleyici için sürüm değiştirme desteklenmiyor."))
        if not re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", new_ver or ""):
            raise JobError(_t("Geçersiz sürüm."))
        if new_ver == inst.get("mc_version"):
            raise JobError(_t("Sunucu zaten bu sürümde."))
        try:
            known = {v["id"] for v in (await mgr.versions())["versions"]}
        except PaperError as e:
            raise JobError(str(e))
        if new_ver not in known:
            raise JobError(_t('{v0} {new_ver} sürümünü desteklemiyor.', v0=loader.capitalize(), new_ver=new_ver))
        java_major = inst.get("java_major")
        if java_major:                                       # panelin yönettiği Java: yeni sürüme göre belirle
            try:
                java_major = (await self.mc.java_for(new_ver, loader))["major"]
            except McError as e:
                raise JobError(str(e))
        old = inst.get("mc_version") or ""
        folder = Path(inst["path"])
        mods_dir = folder / target_dir(loader)
        info = read_mods_info(folder) or {}
        managed = {m.get("filename") for m in info.get("mods", {}).values()}
        manual = [p.name for p in mods_dir.glob("*.jar")] if mods_dir.is_dir() else []
        manual = [n for n in manual if n not in managed] if loader != "vanilla" else []
        return {"old": old, "new": new_ver, "downgrade": bool(old) and vtuple(new_ver) < vtuple(old),
                "java_major": java_major, "custom_java": not inst.get("java_major"),
                "managed_mods": len(managed), "manual_mods": manual[:50], "manual_count": len(manual)}

    async def _follow(self, job: Job, sub: Job, lo: float, hi: float, prefix: str) -> None:
        async for s in sub.watch():
            job.update(lo + (hi - lo) * (s["percent"] or 0) / 100, s.get("stage") or "", f"{prefix}: {s.get('message') or ''}"[:160])
            if s["status"] != "running":
                break
        if sub.status != "done":
            raise JobError(_t('{prefix} başarısız: {error}', prefix=prefix, error=sub.error))

    async def _run(self, job: Job, inst: dict, new_ver: str) -> dict:
        iid = inst["id"]
        if self.pm.status(iid) not in ("stopped", "crashed"):
            raise JobError(_t("Sürümü değiştirmek için önce sunucuyu durdur."))
        job.update(1, "check", _t("Kontrol ediliyor…"))
        plan = await self.check(inst, new_ver)
        folder = Path(inst["path"])

        # 1) zorunlu tam yedek
        bj = self.backups.ensure_create_job(inst, "full", NOTE)
        await self._follow(job, bj, 2, 60, "Yedek")
        backup_file = bj.result.get("file")

        # 2) eski yükleyici kaydı/jar'ı → yeni sürüm ilk başlatmada kurulur
        job.update(62, "loader", _t("Eski sunucu dosyası kaldırılıyor…"))
        (folder / INFO_FILE).unlink(missing_ok=True)
        if (inst.get("launch_type") or "jar") == "jar":
            jar = folder / inst["jar_file"]
            if jar.is_file() and jar.parent == folder:
                jar.unlink()
        upd = {"mc_version": new_ver}
        if not plan["custom_java"]:
            upd["java_major"] = plan["java_major"]
        update_instance(iid, **upd)

        # 3) Modrinth'ten kurulmuş modlar → yeni sürüme göre
        result = {**plan, "backup": backup_file, "mod_warnings": []}
        info = read_mods_info(folder)
        if info and (info.get("mods") or info.get("extra")):
            prof = get_profile(inst.get("profile_id"))
            slugs = list(prof.mods) if prof and prof.mods else []
            mj = self.mods.ensure_install_job(iid, folder, new_ver, inst.get("loader") or "vanilla", slugs)
            await self._follow(job, mj, 65, 98, _t("Modlar"))
            result["mod_warnings"] = (mj.result or {}).get("warnings", [])
        job.update(99, "done", _t("Tamamlandı"))
        return result
