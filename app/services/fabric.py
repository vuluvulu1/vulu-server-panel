"""Fabric sunucu jar'ını resmi meta API'den (meta.fabricmc.net) indirir.

  GET {api}/versions/game        -> [{"version": "1.21.1", "stable": true}, ...]
  GET {api}/versions/loader      -> [{"version": "0.16.9", "stable": true}, ...]
  GET {api}/versions/installer   -> [{"version": "1.0.1", "stable": true}, ...]
  GET {api}/versions/loader/<mc>/<loader>/<installer>/server/jar   -> tek dosyalık sunucu başlatıcı jar
API sağlama toplamı vermez; dosyanın jar (zip) olduğu doğrulanır. İlk açılışta Fabric, Minecraft
sunucusunu ve kütüphaneleri kendisi indirir (ilk başlatma uzun sürer).
"""
import os
import re
import time
from pathlib import Path

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager
from .paper import PaperError, PaperManager

RELEASE_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


class FabricError(PaperError):
    pass


class FabricManager:
    install = staticmethod(PaperManager.install)       # jar'ı kopyala + .vulu-jar.json yaz

    def __init__(self, api_base: str, cache_dir: Path, jobs: JobManager) -> None:
        self.api, self.cache, self.jobs = api_base.rstrip("/"), cache_dir, jobs
        self._memo: dict[str, tuple[float, object]] = {}

    async def _get(self, path: str):
        hit = self._memo.get(path)
        if hit and time.monotonic() - hit[0] < 600:
            return hit[1]
        try:
            async with new_client() as c:
                r = await c.get(self.api + path)
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError):
            raise FabricError("Fabric servisine ulaşılamadı. İnternet bağlantını kontrol et.")
        self._memo[path] = (time.monotonic(), data)
        return data

    async def versions(self) -> dict:
        data = await self._get("/versions/game")
        ids = [v["version"] for v in data if v.get("stable") and RELEASE_RE.match(v.get("version", ""))]
        return {"latest": ids[0] if ids else None,
                "versions": [{"id": v, "type": "release", "released": ""} for v in ids]}

    async def resolve(self, mc: str, pin: str | None = None) -> dict:
        if not re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", mc):
            raise FabricError("Geçersiz sürüm.")
        if mc not in {v["id"] for v in (await self.versions())["versions"]}:
            raise FabricError(f"Fabric {mc} sürümünü desteklemiyor.")
        try:
            loaders = await self._get("/versions/loader")
            if pin:
                if pin not in {x["version"] for x in loaders}:
                    raise FabricError(f"Fabric loader {pin} bulunamadı.")
                loader = pin
            else:
                loader = next(x["version"] for x in loaders if x.get("stable"))
            installer = next(x["version"] for x in await self._get("/versions/installer") if x.get("stable"))
        except StopIteration:
            raise FabricError("Fabric kararlı sürüm bilgisi alınamadı.")
        for part in (loader, installer):
            if not re.fullmatch(r"[0-9A-Za-z._+-]{1,30}", part):
                raise FabricError("Fabric sürüm bilgisi beklenmedik biçimde.")
        return {
            "type": "fabric", "version": mc, "build": loader, "channel": "STABLE", "stable": True,
            "label": f"Fabric {mc} · loader {loader}",
            "name": f"fabric-server-mc.{mc}-loader.{loader}-launcher.{installer}.jar",
            "url": f"{self.api}/versions/loader/{mc}/{loader}/{installer}/server/jar",
            "size": 0, "sha256": "",
        }

    def is_cached(self, info: dict) -> bool:
        p = self.cache / info["name"]
        return p.is_file() and p.stat().st_size > 10_000

    def ensure_cached_job(self, version: str, pin: str | None = None) -> Job:
        return self.jobs.start("fabric", f"Fabric {version} indiriliyor", f"fabric-{version}-{pin or ''}",
                               lambda j: self._cache(j, version, pin))

    async def _cache(self, job: Job, version: str, pin: str | None = None) -> dict:
        job.update(0, "resolve", "Fabric sürüm bilgisi alınıyor…")
        try:
            info = await self.resolve(version, pin)
        except FabricError as e:
            raise JobError(str(e))
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / info["name"]
        if self.is_cached(info):
            job.update(95, "cache", "Önbellekte hazır")
            return {**info, "path": str(path), "cached": True}
        part = self.cache / (info["name"] + ".part")
        try:
            await download_file(job, info["url"], part, start_pct=3, span_pct=92, label=f"Fabric {version}")
            with open(part, "rb") as f:
                magic = f.read(2)
            if magic != b"PK" or part.stat().st_size < 10_000:
                raise JobError("Fabric'ten geçerli bir sunucu jar'ı gelmedi. Biraz sonra tekrar dene.")
            os.replace(part, path)
        finally:
            part.unlink(missing_ok=True)
        return {**info, "path": str(path), "cached": False}
