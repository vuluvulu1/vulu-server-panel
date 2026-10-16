"""Panelin kendini güncellemesi.

Denetim: GitHub'daki son release'in sürümü, kurulu sürümle (app.__version__) karşılaştırılır. Panel açıkken
birkaç saatte bir, ayrıca istenince yapılır.

Kurulum (yalnızca imzalı release'ler):
  1. panel-release.json ve imzası indirilir; imza vulu release anahtarıyla doğrulanır. Bu dosya zip'in
     sürümünü, boyutunu ve SHA-256'sını taşır.
  2. Zip indirilir, boyutu ve SHA-256'sı denetlenir; içindeki her yol beyaz listeden geçer.
  3. Mevcut dosyalar data/update/backup/'a yedeklenir, yenileri yazılır, app/ altında artık kullanılmayan
     dosyalar silinir. data/, instances/, runtimes/, .env ve .venv'e asla dokunulmaz.
  4. requirements.txt değiştiyse paketler kurulur; kurulamazsa yedek geri yüklenir.
  5. Sunucular düzgünce durdurulur ve panel yeni kodla yeniden başlar (run.py gözetiminde).

Git ile kurulmuş (geliştirme) kopyalarda kurulum yapılmaz; yalnızca yeni sürüm haber verilir.
Otomatik güncelleme açıksa yeni sürüm, çalışan sunucu yokken kendiliğinden kurulur.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import httpx

from .. import __version__
from ..config import BASE_DIR, DATA_DIR, PANEL_RELEASES_API, PANEL_UPDATE_HOSTS
from ..i18n import _t
from .http import new_client
from .restart import can_restart, request_restart
from .signature import verify

log = logging.getLogger("vulu.updater")

UPDATE_DIR = DATA_DIR / "update"
SETTINGS_FILE = DATA_DIR / "update-settings.json"
MANIFEST, SIGNATURE = "panel-release.json", "panel-release.json.sig"
CHECK_EVERY = 6 * 3600                 # saniye
AUTO_RETRY = 15 * 60                   # çalışan sunucu varken otomatik kurulum bu aralıkla yeniden denenir
MAX_ZIP = 50 * 1048576
MAX_SMALL = 64 * 1024

# Zip'te bulunabilecek yollar (tools/build_release.py ile aynı)
ROOT_FILES = {"baslat.bat", "baslat.sh", "run.py", "requirements.txt", ".env.example", "README.md", "LICENSE",
              "tools/launcher.py"}
ROOT_DIRS = ("app/", "profiles/")
_SAFE_PART = re.compile(r"^[A-Za-z0-9_.\-]+$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class UpdateError(Exception):
    """Kullanıcıya gösterilebilir hata."""


def _ver(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    if not _VERSION.match(v):
        raise ValueError(v)
    return tuple(int(x) for x in v.split("."))


def git_checkout() -> bool:
    return (BASE_DIR / ".git").exists()


def _safe_member(name: str) -> bool:
    if name in ROOT_FILES:
        return True
    if not name.startswith(ROOT_DIRS) or name.endswith("/"):
        return False
    return all(_SAFE_PART.match(p) and p not in (".", "..") for p in name.split("/"))


class Updater:
    def __init__(self) -> None:
        self.state: dict = {"current": __version__, "latest": None, "available": False, "notes": "", "url": "",
                            "checked_at": None, "error": "", "phase": "", "message": ""}
        self._release: dict | None = None
        self._task: asyncio.Task | None = None
        self._busy = asyncio.Lock()

    # ---------- ayarlar ----------
    @staticmethod
    def auto_enabled() -> bool:
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("auto", True) is not False
        except (OSError, ValueError, AttributeError):
            return True

    @staticmethod
    def set_auto(enabled: bool) -> None:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps({"auto": bool(enabled)}), encoding="utf-8")

    def snapshot(self) -> dict:
        return {**self.state, "auto": self.auto_enabled(), "git": git_checkout(), "supervised": can_restart(),
                "installing": self._busy.locked()}

    # ---------- denetim ----------
    async def check(self) -> dict:
        try:
            async with new_client() as c:
                r = await c.get(PANEL_RELEASES_API, headers={"Accept": "application/vnd.github+json"}, timeout=20)
            if r.status_code == 404:
                raise UpdateError(_t("Henüz yayımlanmış bir sürüm yok."))
            r.raise_for_status()
            rel = r.json()
            latest = str(rel.get("tag_name") or "").lstrip("vV")
            assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets") or []
                      if isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("browser_download_url"), str)}
            newer = _ver(latest) > _ver(__version__)
        except UpdateError as e:
            self.state.update(error=str(e), checked_at=time.time())
            return self.snapshot()
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            self.state.update(error=_t("GitHub'a ulaşılamadı; sürüm denetlenemedi."), checked_at=time.time())
            return self.snapshot()

        signed = MANIFEST in assets and SIGNATURE in assets
        self._release = {"version": latest, "assets": assets} if newer and signed else None
        self.state.update(latest=latest, available=bool(self._release), notes=str(rel.get("body") or "")[:5000],
                          url=str(rel.get("html_url") or ""), checked_at=time.time(),
                          error="" if signed or not newer else _t("Yeni sürüm imzasız yayımlanmış; otomatik kurulamaz."))
        return self.snapshot()

    # ---------- kurulum ----------
    def blocked_reason(self) -> str:
        if git_checkout():
            return _t("Panel git ile kurulmuş; güncellemek için klasörde 'git pull' çalıştırıp paneli yeniden başlat.")
        if not can_restart():
            return _t("Panel 'python run.py' (ya da baslat) ile başlatılmadığı için kendini güncelleyemiyor.")
        if not self._release:
            return _t("Kurulacak yeni bir sürüm yok.")
        return ""

    def _phase(self, phase: str, message: str) -> None:
        self.state.update(phase=phase, message=message)

    async def _download(self, client: httpx.AsyncClient, url: str, limit: int) -> bytes:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            if (r.url.host or "").lower() not in PANEL_UPDATE_HOSTS:
                raise UpdateError(_t("Güncelleme beklenmeyen bir adresten geldi; kurulmadı."))
            buf = io.BytesIO()
            async for chunk in r.aiter_bytes(65536):
                buf.write(chunk)
                if buf.tell() > limit:
                    raise UpdateError(_t("Güncelleme dosyası beklenenden büyük; kurulmadı."))
            return buf.getvalue()

    async def install(self) -> None:
        """Yeni sürümü kurar ve paneli yeniden başlatır. Hata olursa UpdateError (dosyalar eski hâlinde kalır)."""
        if self._busy.locked():
            raise UpdateError(_t("Güncelleme zaten sürüyor."))
        async with self._busy:
            if reason := self.blocked_reason():
                raise UpdateError(reason)
            rel = self._release
            try:
                await self._install(rel)
            except UpdateError as e:
                self._phase("error", str(e))
                raise
            except Exception as e:                    # beklenmeyen: yine de anlaşılır mesaj
                log.exception("panel update failed")
                self._phase("error", _t("Güncelleme kurulamadı: {e}", e=e))
                raise UpdateError(self.state["message"])

    async def _install(self, rel: dict) -> None:
        assets = rel["assets"]
        self._phase("download", _t("vulu panel {v} indiriliyor…", v=rel["version"]))
        try:
            async with new_client() as c:
                manifest_raw = await self._download(c, assets[MANIFEST], MAX_SMALL)
                sig = (await self._download(c, assets[SIGNATURE], MAX_SMALL)).decode("ascii", "replace")
                self._phase("verify", _t("İmza doğrulanıyor…"))
                if not verify(manifest_raw, sig):
                    raise UpdateError(_t("Güncellemenin imzası doğrulanamadı; kurulmadı."))
                m = json.loads(manifest_raw)
                ver, zip_name, size, sha = str(m["version"]), str(m["zip"]), int(m["size"]), str(m["sha256"]).lower()
                if ver != rel["version"] or _ver(ver) <= _ver(__version__) or zip_name not in assets or not 0 < size <= MAX_ZIP:
                    raise UpdateError(_t("Güncelleme bilgisi release ile uyuşmuyor; kurulmadı."))
                self._phase("download", _t("vulu panel {v} indiriliyor…", v=ver))
                data = await self._download(c, assets[zip_name], size)
        except httpx.HTTPError:
            raise UpdateError(_t("Güncelleme indirilemedi. İnternet bağlantını kontrol et."))
        except (ValueError, KeyError, TypeError):
            raise UpdateError(_t("Güncelleme bilgisi okunamadı; kurulmadı."))
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
            raise UpdateError(_t("İndirilen güncelleme doğrulanamadı (sağlama toplamı uyuşmuyor)."))

        self._phase("apply", _t("Dosyalar güncelleniyor…"))
        await asyncio.to_thread(self._apply, data, ver)
        self._phase("restart", _t("vulu panel {v} kuruldu, yeniden başlatılıyor…", v=ver))
        request_restart(delay=1.5)

    # ---------- dosyalar (iş parçacığında) ----------
    def _apply(self, data: bytes, ver: str) -> None:
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = [i.filename for i in z.infolist() if not i.is_dir()]
        except zipfile.BadZipFile:
            raise UpdateError(_t("Güncelleme paketi bozuk; kurulmadı."))
        bad = [n for n in names if not _safe_member(n)]
        if bad or "app/__init__.py" not in names or "run.py" not in names:
            raise UpdateError(_t("Güncelleme paketinde beklenmeyen dosyalar var; kurulmadı."))
        init = z.read("app/__init__.py").decode("utf-8", "replace")
        if f'__version__ = "{ver}"' not in init:
            raise UpdateError(_t("Güncelleme paketinin sürümü uyuşmuyor; kurulmadı."))

        backup = UPDATE_DIR / "backup"
        old_req = (BASE_DIR / "requirements.txt").read_bytes() if (BASE_DIR / "requirements.txt").is_file() else b""
        self._backup(backup)
        new_set = set(names)
        try:
            for n in names:
                dest = BASE_DIR / n
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".update")
                tmp.write_bytes(z.read(n))
                if dest.is_file():
                    shutil.copymode(dest, tmp)        # baslat.sh'nin çalıştırma izni korunur
                tmp.replace(dest)
            # app/ altında yeni sürümde olmayan dosyalar (eski modüller, şablonlar) kaldırılır
            for p in (BASE_DIR / "app").rglob("*"):
                rel = p.relative_to(BASE_DIR).as_posix()
                if p.is_file() and "__pycache__" not in p.parts and rel not in new_set:
                    p.unlink()
            if "requirements.txt" in new_set and z.read("requirements.txt") != old_req:
                self._phase("deps", _t("Gerekli paketler kuruluyor…"))
                self._pip()
        except Exception:
            self._restore(backup)
            raise

    @staticmethod
    def _managed() -> list[Path]:
        out = [BASE_DIR / f for f in ROOT_FILES if (BASE_DIR / f).is_file()]
        for d in ROOT_DIRS:
            out += [p for p in (BASE_DIR / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        return out

    def _backup(self, backup: Path) -> None:
        shutil.rmtree(backup, ignore_errors=True)
        for p in self._managed():
            dest = backup / p.relative_to(BASE_DIR)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)

    def _restore(self, backup: Path) -> None:
        if not backup.is_dir():
            return
        for p in (BASE_DIR / "app").rglob("*"):            # yeni sürümün eklediği dosyalar
            if p.is_file() and "__pycache__" not in p.parts and not (backup / p.relative_to(BASE_DIR)).exists():
                p.unlink(missing_ok=True)
        for p in backup.rglob("*"):
            if p.is_file():
                dest = BASE_DIR / p.relative_to(backup)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

    @staticmethod
    def _pip() -> None:
        req = BASE_DIR / "requirements.txt"
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                                "--progress-bar", "off", "-r", str(req)], cwd=BASE_DIR, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise UpdateError(_t("Gerekli paketler kurulamadı: {e}", e=e))
        if r.returncode != 0:
            tail = " ".join((r.stderr or r.stdout or "").strip().splitlines()[-2:])[:300]
            raise UpdateError(_t("Gerekli paketler kurulamadı: {e}", e=tail))
        mark = Path(sys.prefix) / "requirements.installed"   # baslat'ın "paketler güncel" işareti
        try:
            mark.write_bytes(req.read_bytes())
        except OSError:
            pass

    # ---------- arka plan ----------
    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        await asyncio.sleep(60)                         # açılışı yavaşlatmasın
        last_check = 0.0
        while True:
            try:
                if time.time() - last_check >= CHECK_EVERY:
                    await self.check()
                    last_check = time.time()
                if self.auto_enabled() and self._release and not self.blocked_reason() and self._idle():
                    log.warning("vulu panel %s otomatik kuruluyor", self._release["version"])
                    await self.install()
                    return
            except UpdateError:
                pass
            except Exception:
                log.exception("update loop")
            await asyncio.sleep(AUTO_RETRY)

    @staticmethod
    def _idle() -> bool:
        from .container import launcher, process_manager
        return not process_manager.running_ids() and not launcher._prep


updater = Updater()
