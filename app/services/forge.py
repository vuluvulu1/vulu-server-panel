"""Forge ve NeoForge: resmi Maven'den kurucuyu indirir ve `--installServer` ile sunucu klasörüne kurar.

  Forge:    {maven}/net/minecraftforge/forge/<mc>-<forge>/forge-<mc>-<forge>-installer.jar   (+ .sha1)
  NeoForge: {maven}/net/neoforged/neoforge/<sürüm>/neoforge-<sürüm>-installer.jar            (+ .sha256)
  Sürüm listesi: .../maven-metadata.xml
Kurucu sunucu klasöründe çalışır; yeni sürümlerde libraries/.../{win,unix}_args.txt üretir
(panel bunu `args-file` olarak başlatır), 1.16.5 ve öncesinde forge-<sürüm>.jar üretir (`jar`).
Kurucu resmi kaynaktan gelen üçüncü taraf koddur; panel yalnızca sabit resmi adreslerden indirir ve
sağlama toplamını doğrular. NeoForge yalnızca `neoforge` paketini (MC 1.20.2+) destekler.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager
from .paper import INFO_FILE, PaperError

SAFE = re.compile(r"^[0-9A-Za-z._+-]{1,60}$")
RELEASE_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
UNSTABLE = re.compile(r"alpha|beta|rc|pre", re.I)


class ForgeError(PaperError):
    pass


def _natural(s: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def _tuple(mc: str):
    return tuple(int(x) for x in mc.split("."))


class ForgeManager:
    kind = "installer"        # jar kopyalamaz; kurucuyu çalıştırır

    def __init__(self, flavor: str, maven_base: str, cache_dir: Path, jobs: JobManager) -> None:
        self.flavor, self.base, self.cache, self.jobs = flavor, maven_base.rstrip("/"), cache_dir, jobs
        self.name = "Forge" if flavor == "forge" else "NeoForge"
        self.artifact = "forge" if flavor == "forge" else "neoforge"
        self.group = "net/minecraftforge" if flavor == "forge" else "net/neoforged"
        self._memo: tuple[float, dict] | None = None

    def _url(self, *parts: str) -> str:
        return f"{self.base}/{self.group}/{self.artifact}/" + "/".join(parts)

    def _mc_of(self, v: str) -> str | None:
        if UNSTABLE.search(v) and "alpha" in v.lower():
            return None
        if self.flavor == "forge":
            mc = v.split("-", 1)[0]
            return mc if RELEASE_RE.match(mc) and _tuple(mc) >= (1, 12, 2) else None
        m = re.match(r"^(\d+)\.(\d+)\.", v)
        if not m:
            return None
        a, b = int(m[1]), int(m[2])
        if a >= 26:
            return f"{a}.{b}"                  # yıl bazlı sürümleme (en iyi tahmin)
        if a < 20:
            return None
        return f"1.{a}" if b == 0 else f"1.{a}.{b}"

    async def _metadata(self) -> dict[str, list[str]]:
        if self._memo and time.monotonic() - self._memo[0] < 600:
            return self._memo[1]
        try:
            async with new_client() as c:
                r = await c.get(self._url("maven-metadata.xml"))
                r.raise_for_status()
                text = r.text
        except httpx.HTTPError:
            raise ForgeError(f"{self.name} sürüm listesine ulaşılamadı. İnternet bağlantını kontrol et.")
        by_mc: dict[str, list[str]] = {}
        for v in re.findall(r"<version>([^<]+)</version>", text):
            mc = self._mc_of(v) if SAFE.match(v) else None
            if mc:
                by_mc.setdefault(mc, []).append(v)
        self._memo = (time.monotonic(), by_mc)
        return by_mc

    async def versions(self) -> dict:
        ids = sorted((await self._metadata()), key=_tuple, reverse=True)
        return {"latest": ids[0] if ids else None,
                "versions": [{"id": v, "type": "release", "released": ""} for v in ids]}

    def _tail(self, v: str) -> str:
        return v.split("-", 1)[1] if self.flavor == "forge" and "-" in v else v

    async def resolve(self, mc: str, pin: str | None = None) -> dict:
        vs = (await self._metadata()).get(mc) if re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", mc) else None
        if not vs:
            raise ForgeError(f"{self.name} {mc} sürümünü desteklemiyor.")
        stable = [v for v in vs if not UNSTABLE.search(self._tail(v))]
        if pin:                                            # modpack'in istediği tam yükleyici sürümü
            want = f"{mc}-{pin}" if self.flavor == "forge" else pin
            if want not in vs:
                raise ForgeError(f"{self.name} {pin} sürümü bulunamadı.")
            chosen, stable = want, [want] if not UNSTABLE.search(self._tail(want)) else []
        else:
            chosen = max(stable or vs, key=lambda v: _natural(self._tail(v)))
        name = f"{self.artifact}-{chosen}-installer.jar"
        return {
            "type": self.flavor, "version": mc, "build": chosen, "maven": chosen,
            "channel": "STABLE" if stable else "BETA", "stable": bool(stable),
            "label": f"{self.name} {mc} · {self._tail(chosen)}",
            "name": name, "url": self._url(chosen, name), "size": 0, "sha256": "",
        }

    def is_cached(self, info: dict) -> bool:
        p = self.cache / info["name"]
        return p.is_file() and p.stat().st_size > 10_000

    async def _checksum(self, url: str) -> tuple[str, str]:
        suffix, kind = (".sha1", "sha1") if self.flavor == "forge" else (".sha256", "sha256")
        try:
            async with new_client() as c:
                r = await c.get(url + suffix)
            tok = r.text.split()[0].lower() if r.status_code == 200 and r.text.strip() else ""
        except (httpx.HTTPError, IndexError):
            return kind, ""
        return kind, tok if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tok) else ""

    # ---------- kurucuyu önbelleğe indir ----------
    def ensure_cached_job(self, version: str, pin: str | None = None) -> Job:
        return self.jobs.start(self.flavor, f"{self.name} {version} kurucusu indiriliyor", f"{self.flavor}-dl-{version}-{pin or ''}",
                               lambda j: self._cache(j, version, pin))

    async def _cache(self, job: Job, version: str, pin: str | None = None) -> dict:
        job.update(0, "resolve", f"{self.name} sürüm bilgisi alınıyor…")
        try:
            info = await self.resolve(version, pin)
        except ForgeError as e:
            raise JobError(str(e))
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / info["name"]
        if self.is_cached(info):
            job.update(95, "cache", "Önbellekte hazır")
            return {**info, "path": str(path), "cached": True}
        kind, digest = await self._checksum(info["url"])
        part = self.cache / (info["name"] + ".part")
        try:
            await download_file(job, info["url"], part, start_pct=3, span_pct=92, label=f"{self.name} kurucusu",
                                expected_sha256=digest if kind == "sha256" else "",
                                expected_sha1=digest if kind == "sha1" else "")
            with open(part, "rb") as f:
                magic = f.read(2)
            if magic != b"PK" or part.stat().st_size < 10_000:
                raise JobError(f"{self.name}'dan geçerli bir kurucu gelmedi. Biraz sonra tekrar dene.")
            os.replace(part, path)
        finally:
            part.unlink(missing_ok=True)
        return {**info, "path": str(path), "cached": False}

    # ---------- kurucuyu çalıştır ----------
    def ensure_install_job(self, iid: int, info: dict, folder: Path, java_exe: str) -> Job:
        return self.jobs.start("install", f"{info['label']} kuruluyor", f"{self.flavor}-install-{iid}",
                               lambda j: self._install(j, info, folder, java_exe))

    @staticmethod
    def _run(cmd: list[str], folder: Path, on_line) -> tuple[int, list[str]]:
        proc = subprocess.Popen(
            cmd, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        timer = threading.Timer(1200, proc.kill)          # 20 dk üst sınır
        timer.start()
        tail: deque[str] = deque(maxlen=8)
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    tail.append(line)
                    on_line(line)
            return proc.wait(), list(tail)
        finally:
            timer.cancel()

    async def _install(self, job: Job, info: dict, folder: Path, java_exe: str) -> dict:
        job.update(1, "install", "Kurucu çalıştırılıyor…")
        loop, n = asyncio.get_running_loop(), [0]

        def on_line(line: str) -> None:
            n[0] += 1
            loop.call_soon_threadsafe(job.update, min(95, 2 + n[0] * 0.4), "install", line[:140])

        try:
            code, tail = await asyncio.to_thread(self._run, [java_exe, "-jar", info["path"], "--installServer"], folder, on_line)
        except OSError as e:
            raise JobError(f"Kurucu başlatılamadı: {e}")
        if code != 0:
            raise JobError(f"Kurucu başarısız oldu (çıkış kodu {code}): " + " | ".join(tail[-3:]))
        job.update(97, "finalize", "Başlatma dosyası aranıyor…")
        db = self._detect(info, folder)
        (folder / INFO_FILE).write_text(json.dumps({
            "type": self.flavor, "label": info["label"], "version": info["version"], "build": info["build"],
            "channel": info["channel"], "name": info["name"], "sha256": "",
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }), encoding="utf-8")
        return {"db": db}

    def _detect(self, info: dict, folder: Path) -> dict:
        plat = "win" if os.name == "nt" else "unix"
        vdir = f"libraries/{self.group}/{self.artifact}/{info['maven']}"
        if (folder / vdir / f"{plat}_args.txt").is_file():
            return {"launch_type": "args-file", "args_file": f"{vdir}/{{platform}}_args.txt"}
        if self.flavor == "forge":                       # 1.16.5 ve öncesi: tek jar
            for name in (f"forge-{info['maven']}.jar", f"forge-{info['maven']}-universal.jar"):
                if (folder / name).is_file():
                    return {"launch_type": "jar", "jar_file": name, "args_file": None}
        raise JobError("Kurulum bitti ama başlatma dosyası bulunamadı. Kurucunun çıktısını kontrol et.")
