"""Vanilla (resmi Mojang) sunucu jar'ı: sürüm JSON'undaki downloads.server (SHA-1 doğrulamalı)."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager
from .minecraft import McError
from .paper import PaperError, PaperManager

MOJANG_HOSTS = {"piston-data.mojang.com", "launcher.mojang.com", "piston-meta.mojang.com"}


class VanillaError(PaperError):
    pass


class VanillaManager:
    install = staticmethod(PaperManager.install)

    def __init__(self, minecraft, cache_dir: Path, jobs: JobManager, extra_hosts: set[str] | None = None) -> None:
        self.mc, self.cache, self.jobs = minecraft, cache_dir, jobs
        self.hosts = MOJANG_HOSTS | (extra_hosts or set())

    async def versions(self) -> dict:
        try:
            return await self.mc.list_versions()
        except McError as e:
            raise VanillaError(str(e))

    async def resolve(self, mc: str, pin: str | None = None) -> dict:
        if not re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", mc):
            raise VanillaError("Geçersiz sürüm.")
        try:
            entry = next((v for v in (await self.mc.manifest()).get("versions", []) if v.get("id") == mc), None)
        except McError as e:
            raise VanillaError(str(e))
        if not entry:
            raise VanillaError(f"Minecraft {mc} sürümü bulunamadı.")
        try:
            async with new_client() as c:
                r = await c.get(entry["url"])
                r.raise_for_status()
                srv = ((r.json().get("downloads") or {}).get("server")) or {}
        except (httpx.HTTPError, ValueError):
            raise VanillaError("Mojang sürüm bilgisine ulaşılamadı.")
        url, sha1 = srv.get("url", ""), str(srv.get("sha1", "")).lower()
        if not url or not re.fullmatch(r"[0-9a-f]{40}", sha1):
            raise VanillaError(f"Minecraft {mc} için resmi sunucu jar'ı yok.")
        u = urlparse(url)
        if (u.hostname or "") not in self.hosts or (u.scheme != "https" and (u.hostname or "") in MOJANG_HOSTS):
            raise VanillaError("Beklenmeyen indirme adresi reddedildi.")
        return {"type": "vanilla", "version": mc, "build": mc, "channel": "RELEASE", "stable": True,
                "label": f"Vanilla {mc}", "name": f"minecraft_server-{mc}-{sha1[:8]}.jar", "url": url,
                "size": int(srv.get("size") or 0), "sha256": "", "sha1": sha1}

    def is_cached(self, info: dict) -> bool:
        p = self.cache / info["name"]
        return p.is_file() and (not info["size"] or p.stat().st_size == info["size"])

    def ensure_cached_job(self, version: str, pin: str | None = None) -> Job:
        return self.jobs.start("vanilla", f"Minecraft {version} sunucusu indiriliyor", f"vanilla-{version}",
                               lambda j: self._cache(j, version))

    async def _cache(self, job: Job, version: str) -> dict:
        job.update(0, "resolve", "Mojang sürüm bilgisi alınıyor…")
        try:
            info = await self.resolve(version)
        except VanillaError as e:
            raise JobError(str(e))
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / info["name"]
        if self.is_cached(info):
            job.update(95, "cache", "Önbellekte hazır")
            return {**info, "path": str(path), "cached": True}
        part = self.cache / (info["name"] + ".part")
        try:
            await download_file(job, info["url"], part, expected_sha1=info["sha1"], size_hint=info["size"],
                                start_pct=3, span_pct=92, label=f"Minecraft {version} sunucusu")
            os.replace(part, path)
        finally:
            part.unlink(missing_ok=True)
        return {**info, "path": str(path), "cached": False}
