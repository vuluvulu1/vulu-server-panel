"""Java çalışma zamanlarını (JRE) otomatik indirip kurar.

Paket: Eclipse Temurin JRE (Adoptium). JDK'dan çok daha küçük (~40-55 MB indirme),
sunucuyu çalıştırmak için yeterli. Bir sürüm için JRE yoksa JDK'ya düşülür.
Kurulum yeri: runtimes/java-<major>/bin/java(.exe)
"""
import asyncio
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager
from ..i18n import _t

EXE = "java.exe" if os.name == "nt" else "java"
META = ".vulu-java.json"


class JavaError(Exception):
    pass


def platform_names() -> tuple[str, str]:
    """(os, arch) — Adoptium API adlandırmasıyla."""
    system = platform.system().lower()
    os_ = {"windows": "windows", "linux": "linux", "darwin": "mac"}.get(system)
    if not os_:
        raise JavaError(_t('Bu işletim sistemi desteklenmiyor: {v0}', v0=platform.system()))
    if os_ == "linux" and Path("/etc/alpine-release").exists():
        os_ = "alpine-linux"
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "aarch64", "aarch64": "aarch64"}.get(platform.machine().lower())
    if not arch:
        raise JavaError(_t('Bu işlemci mimarisi desteklenmiyor: {v0}', v0=platform.machine()))
    return os_, arch


def _mb(n: float) -> str:
    return f"{n / 1_048_576:.1f}"


class JavaManager:
    def __init__(self, runtimes_dir: Path, api_base: str, jobs: JobManager) -> None:
        self.runtimes = runtimes_dir
        self.api = api_base.rstrip("/")
        self.jobs = jobs
        self._pkg_cache: dict[int, tuple[float, dict]] = {}

    # ---------- kurulu mu? ----------
    def _dir(self, major: int) -> Path:
        return self.runtimes / f"java-{major}"

    def find(self, major: int) -> Path | None:
        p = self._dir(major) / "bin" / EXE
        return p if p.is_file() else None

    def _meta(self, major: int) -> dict:
        try:
            return json.loads((self._dir(major) / META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def installed(self) -> list[dict]:
        out = []
        for d in sorted(self.runtimes.glob("java-*")):
            m = re.fullmatch(r"java-(\d+)", d.name)
            if m and self.find(int(m[1])):
                out.append({"major": int(m[1]), "path": str(self.find(int(m[1]))), **self._meta(int(m[1]))})
        return out

    # ---------- paket bilgisi ----------
    async def resolve_package(self, major: int) -> dict:
        cached = self._pkg_cache.get(major)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        os_, arch = platform_names()
        try:
            async with new_client() as c:
                for image in ("jre", "jdk"):
                    r = await c.get(
                        f"{self.api}/assets/latest/{major}/hotspot",
                        params={"image_type": image, "vendor": "eclipse", "architecture": arch, "os": os_},
                    )
                    if r.status_code == 404:
                        continue
                    r.raise_for_status()
                    for item in r.json():
                        b = item.get("binary", {})
                        pkg = b.get("package") or {}
                        if pkg.get("link") and b.get("heap_size", "normal") == "normal":
                            result = {
                                "name": pkg["name"], "link": pkg["link"],
                                "size": int(pkg.get("size") or 0),
                                "checksum": (pkg.get("checksum") or "").lower(),
                                "version": (item.get("version") or {}).get("openjdk_version", ""),
                                "image_type": image,
                            }
                            self._pkg_cache[major] = (time.monotonic(), result)
                            return result
        except (httpx.HTTPError, ValueError):
            raise JavaError(_t("Adoptium'a ulaşılamadı. İnternet bağlantını kontrol et."))
        raise JavaError(_t('Java {major} için bu sistemde indirilebilir paket bulunamadı.', major=major))

    async def info(self, major: int) -> dict:
        out: dict = {"major": major, "installed": False, "path": None, "version": None, "package": None, "error": None}
        path = self.find(major)
        if path:
            out.update(installed=True, path=str(path), version=self._meta(major).get("version"))
            return out
        try:
            pkg = await self.resolve_package(major)
            out["package"] = {k: pkg[k] for k in ("name", "size", "version", "image_type")}
        except JavaError as e:
            out["error"] = str(e)
        return out

    # ---------- kurulum işi ----------
    def ensure_job(self, major: int) -> Job:
        return self.jobs.start("java", _t('Java {major} kuruluyor', major=major), f"java-{major}", lambda j: self._install(j, major))

    async def _install(self, job: Job, major: int) -> dict:
        job.update(0, "resolve", _t("Paket bilgisi alınıyor…"))
        try:
            pkg = await self.resolve_package(major)
        except JavaError as e:
            raise JobError(str(e))

        self.runtimes.mkdir(parents=True, exist_ok=True)
        dl_dir = self.runtimes / ".downloads"
        dl_dir.mkdir(exist_ok=True)
        archive = dl_dir / pkg["name"]
        part = dl_dir / (pkg["name"] + ".part")
        tmp = Path(tempfile.mkdtemp(prefix=f".tmp-java{major}-", dir=self.runtimes))
        loop = asyncio.get_running_loop()

        try:
            await self._download(job, pkg, part)
            part.replace(archive)

            def on_extract(fraction: float) -> None:
                loop.call_soon_threadsafe(job.update, 82 + 14 * fraction, "extract", _t('Çıkarılıyor… %{v0}', v0=int(fraction * 100)))

            job.update(82, "extract", _t("Çıkarılıyor…"))
            await asyncio.to_thread(self._extract, archive, tmp, on_extract)
            home = self._find_home(tmp)

            job.update(96, "check", _t("Java test ediliyor…"))
            version = await asyncio.to_thread(self._probe, home, major)

            job.update(99, "finalize", _t("Yerleştiriliyor…"))
            await asyncio.to_thread(self._place, home, self._dir(major))
            (self._dir(major) / META).write_text(json.dumps({
                "version": version, "vendor": "Eclipse Temurin", "image_type": pkg["image_type"],
                "package": pkg["name"], "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }), encoding="utf-8")
            return {"path": str(self.find(major)), "version": version}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            archive.unlink(missing_ok=True)
            part.unlink(missing_ok=True)

    async def _download(self, job: Job, pkg: dict, dest: Path) -> None:
        await download_file(
            job, pkg["link"], dest, expected_sha256=pkg["checksum"], size_hint=pkg["size"],
            start_pct=3, span_pct=77, label=_t("İndiriliyor"),
        )

    # ---------- arşivden çıkarma (thread içinde) ----------
    @staticmethod
    def _extract(archive: Path, dest: Path, progress) -> None:
        name = archive.name.lower()
        dest = dest.resolve()
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                infos = zf.infolist()
                total = sum(i.file_size for i in infos) or 1
                done = 0
                for info in infos:
                    target = (dest / info.filename).resolve()
                    if not target.is_relative_to(dest):
                        raise JobError(_t("Arşiv güvenli değil (geçersiz dosya yolu)."))
                    zf.extract(info, dest)
                    done += info.file_size
                    progress(min(done / total, 1.0))
        elif name.endswith((".tar.gz", ".tgz")):
            size = archive.stat().st_size or 1
            with open(archive, "rb") as raw, tarfile.open(fileobj=raw, mode="r|gz") as tf:
                for member in tf:
                    if hasattr(tarfile, "data_filter"):
                        tf.extract(member, dest, filter="data")   # mutlak/kaçan yolları ve tehlikeli izinleri engeller
                    else:
                        target = (dest / member.name).resolve()
                        if not target.is_relative_to(dest) or member.issym() or member.islnk():
                            raise JobError(_t("Arşiv güvenli değil (geçersiz dosya yolu)."))
                        tf.extract(member, dest)
                    progress(min(raw.tell() / size, 1.0))
        else:
            raise JobError(_t('Desteklenmeyen arşiv türü: {name}', name=archive.name))

    @staticmethod
    def _find_home(root: Path) -> Path:
        for exe in root.rglob(f"bin/{EXE}"):
            return exe.parent.parent
        raise JobError(_t("Arşivin içinde java bulunamadı."))

    @staticmethod
    def _probe(home: Path, major: int) -> str:
        exe = home / "bin" / EXE
        try:
            r = subprocess.run(
                [str(exe), "-version"], capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise JobError(_t('Kurulan Java çalıştırılamadı: {e}', e=e))
        m = re.search(r'version "([^"]+)"', r.stderr + r.stdout)
        if not m:
            raise JobError(_t("Kurulan Java'nın sürümü okunamadı."))
        v = m[1]
        got = int(v.split(".")[1]) if v.startswith("1.") else int(re.match(r"\d+", v)[0])
        if got != major:
            raise JobError(_t('Beklenen Java {major} yerine Java {got} kuruldu.', major=major, got=got))
        return v

    @staticmethod
    def _place(home: Path, target: Path) -> None:
        if target.exists():
            shutil.rmtree(target)
        for attempt in range(6):   # Windows'ta antivirüs geçici kilit koyabilir
            try:
                os.replace(home, target)
                return
            except PermissionError:
                if attempt == 5:
                    raise JobError(_t("Java klasörü yerleştirilemedi (dosya kilitli). Birkaç saniye sonra tekrar dene."))
                time.sleep(0.5)
