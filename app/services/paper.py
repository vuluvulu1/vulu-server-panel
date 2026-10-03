"""PaperMC jar'larını resmi indirme servisinden (Fill API v3) indirir.

- Sürümler:  GET {api}/projects/paper            -> {"versions": {"<grup>": ["1.21.1", ...], ...}}
- Buildler:  GET {api}/projects/paper/versions/<v>/builds
             -> [{"id": 130, "channel": "STABLE",
                  "downloads": {"server:default": {"name","url","size","checksums":{"sha256"}}}}, ...]
Jar'lar data/cache/paper/ altında önbelleğe alınır (aynı build'i iki sunucu için tekrar indirmez).
"""
import asyncio
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager

CHANNEL_ORDER = ["RECOMMENDED", "STABLE", "BETA", "ALPHA"]
RELEASE_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
INFO_FILE = ".vulu-jar.json"


class PaperError(Exception):
    pass


def read_jar_info(folder: Path) -> dict | None:
    try:
        return json.loads((folder / INFO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class PaperManager:
    def __init__(self, api_base: str, cache_dir: Path, jobs: JobManager) -> None:
        self.api = api_base.rstrip("/")
        self.cache = cache_dir
        self.jobs = jobs
        self._versions: tuple[float, dict] | None = None

    async def _get(self, path: str):
        try:
            async with new_client() as c:
                r = await c.get(self.api + path)
        except httpx.HTTPError:
            raise PaperError("PaperMC'ye ulaşılamadı. İnternet bağlantını kontrol et.")
        if r.status_code == 403:
            raise PaperError("PaperMC isteği reddetti (403). .env dosyana PANEL_CONTACT=<e-posta veya site adresin> ekleyip paneli yeniden başlat.")
        if r.status_code == 404:
            raise PaperError("PaperMC'de bu sürüm bulunamadı.")
        try:
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            raise PaperError("PaperMC yanıtı okunamadı.")

    # ---------- sürümler ----------
    async def versions(self) -> dict:
        if self._versions and time.monotonic() - self._versions[0] < 600:
            return self._versions[1]
        data = await self._get("/projects/paper")
        groups = (data or {}).get("versions") if isinstance(data, dict) else None
        if not isinstance(groups, dict):
            raise PaperError("PaperMC sürüm listesi okunamadı.")
        ids = [v for vs in groups.values() for v in vs if RELEASE_RE.match(v)]   # en yeni başta; -pre/-rc elenir
        result = {"latest": ids[0] if ids else None,
                  "versions": [{"id": v, "type": "release", "released": ""} for v in ids]}
        self._versions = (time.monotonic(), result)
        return result

    # ---------- build seçimi ----------
    async def resolve(self, version: str) -> dict:
        if not re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", version):
            raise PaperError("Geçersiz sürüm.")
        data = await self._get(f"/projects/paper/versions/{version}/builds")
        if isinstance(data, dict):                       # {"ok": false, "message": ...}
            raise PaperError(str(data.get("message") or "PaperMC bu sürüm için build vermedi."))
        if not isinstance(data, list) or not data:
            raise PaperError(f"Paper {version} için build bulunamadı.")

        def rank(b: dict) -> tuple[int, int]:
            ch = b.get("channel", "")
            return (CHANNEL_ORDER.index(ch) if ch in CHANNEL_ORDER else 99, -int(b.get("id", 0)))

        best = min(data, key=rank)                       # en iyi kanal, o kanalın en yeni build'i
        dls = best.get("downloads") or {}
        dl = dls.get("server:default") or next((d for d in dls.values() if str(d.get("name", "")).endswith(".jar")), None)
        if not dl or not dl.get("url"):
            raise PaperError(f"Paper {version} build #{best.get('id')} için indirme bağlantısı yok.")
        channel = best.get("channel", "?")
        return {
            "version": version, "build": int(best["id"]), "channel": channel,
            "stable": channel in ("STABLE", "RECOMMENDED"),
            "name": dl["name"], "url": dl["url"], "size": int(dl.get("size") or 0),
            "sha256": ((dl.get("checksums") or {}).get("sha256") or "").lower(),
        }

    def is_cached(self, info: dict) -> bool:
        p = self.cache / info["name"]
        return p.is_file() and (not info["size"] or p.stat().st_size == info["size"])

    # ---------- önbelleğe indirme işi ----------
    def ensure_cached_job(self, version: str) -> Job:
        return self.jobs.start("paper", f"Paper {version} indiriliyor", f"paper-{version}",
                               lambda j: self._cache(j, version))

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    async def _cache(self, job: Job, version: str) -> dict:
        job.update(0, "resolve", "Paper build bilgisi alınıyor…")
        try:
            info = await self.resolve(version)
        except PaperError as e:
            raise JobError(str(e))
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / info["name"]

        if self.is_cached(info) and (not info["sha256"] or await asyncio.to_thread(self._sha256, path) == info["sha256"]):
            job.update(95, "cache", "Önbellekte hazır")
            return {**info, "path": str(path), "cached": True}

        part = self.cache / (info["name"] + ".part")
        try:
            await download_file(job, info["url"], part, expected_sha256=info["sha256"], size_hint=info["size"],
                                start_pct=3, span_pct=92, label=f"Paper {version} build #{info['build']}")
            os.replace(part, path)
        finally:
            part.unlink(missing_ok=True)
        return {**info, "path": str(path), "cached": False}

    # ---------- sunucu klasörüne yerleştirme ----------
    @staticmethod
    def install(info: dict, folder: Path, jar_name: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / (jar_name + ".part")
        try:
            shutil.copyfile(info["path"], tmp)
            os.replace(tmp, folder / jar_name)
        finally:
            tmp.unlink(missing_ok=True)
        (folder / INFO_FILE).write_text(json.dumps({
            "type": "paper", "version": info["version"], "build": info["build"], "channel": info["channel"],
            "name": info["name"], "sha256": info["sha256"], "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }), encoding="utf-8")
