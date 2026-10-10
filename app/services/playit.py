"""playit.gg entegrasyonu: port yönlendirmesi olmadan Minecraft sunucusunu internete açar.

Akış
  1) Resmi playit programı (0.17.1, hizmet kurmadan çalışan sürüm) GitHub sürümünden indirilir,
     SHA-256 sabit değerle doğrulanır → runtimes/playit/. Her başlatmadan önce yeniden doğrulanır.
  2) Bağlama: panel rastgele bir kod üretir, kullanıcı https://playit.gg/claim/<kod> adresinde onaylar,
     panel /claim/setup + /claim/exchange ile ajan anahtarını alır → data/playit/secret.txt
     (tarayıcıya hiçbir zaman gönderilmez).
  3) Program panelin alt süreci olarak `--secret_path ... -s start` ile çalışır; panel açıkken açık kalır,
     çökerse bekleyip yeniden başlatılır.
  4) Tüneller: /agents/rundata ile okunur (yerel port eşleşmesiyle sunucuya bağlanır), /tunnels/create ile
     panelden oluşturulmaya çalışılır; olmazsa kullanıcıya site bağlantısı verilir.

API biçimi playit-agent kaynak kodundan alınmıştır (api_client/src/api.rs):
  POST <API>/<yol>, gövde JSON, yetki "Authorization: Agent-Key <anahtar>",
  yanıt {"status": "success"|"fail"|"error", "data": ...}
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
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
from ..i18n import _t

PLAYIT_VERSION = "0.17.1"
RELEASE_URL = "https://github.com/playit-cloud/playit-agent/releases/download/v{v}/{asset}"
# (platform, mimari) → (dosya, SHA-256). Değerler resmi GitHub sürümünden indirilen dosyalardan hesaplandı.
ASSETS = {
    ("win", "amd64"): ("playit-windows-x86_64-signed.exe", "9b00d6ff7d37d1052e5ae097e1348e11deae8617cd7a8ba39d1777f2006316a3"),
    ("linux", "amd64"): ("playit-linux-amd64", "e78d463d93aa1e3ec36a06ded5a1f4fe879905fdceb865df8f4cef6124f8a555"),
}
CLAIM_TIMEOUT = 15 * 60
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,512}$")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


class PlayitError(Exception):
    pass


def _platform() -> tuple[str, str] | None:
    import platform
    m = platform.machine().lower()
    arch = "amd64" if m in ("x86_64", "amd64") else m
    plat = "win" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else sys.platform
    return (plat, arch) if (plat, arch) in ASSETS else None


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class PlayitManager:
    def __init__(self, api_base: str, runtime_dir: Path, data_dir: Path, jobs: JobManager) -> None:
        self.api = api_base.rstrip("/")
        self.runtime_dir, self.data_dir, self.jobs = runtime_dir, data_dir, jobs
        self.secret_file = data_dir / "secret.txt"
        self.state_file = data_dir / "state.json"
        self.log: deque[str] = deque(maxlen=300)
        self._proc: subprocess.Popen | None = None
        self._want_running = False
        self._watch: asyncio.Task | None = None
        self._claim: dict | None = None            # {"code","url","state","error","task"}
        self._rundata: tuple[float, dict] | None = None

    # ---------- yardımcılar ----------
    @property
    def asset(self):
        p = _platform()
        return ASSETS.get(p) if p else None

    @property
    def exe(self) -> Path | None:
        a = self.asset
        return self.runtime_dir / a[0] if a else None

    def installed(self) -> bool:
        return bool(self.exe and self.exe.is_file())

    def linked(self) -> bool:
        return self._secret() is not None

    def _secret(self) -> str | None:
        try:
            s = self.secret_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return s if SECRET_RE.match(s) else None

    def _state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, st: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st), encoding="utf-8")

    def _write_secret(self, secret: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.secret_file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(secret)
        os.replace(tmp, self.secret_file)

    def _log(self, line: str) -> None:
        line = ANSI_RE.sub("", line).rstrip()
        if line:
            self.log.append(time.strftime("%H:%M:%S ") + line[:400])

    async def _call(self, path: str, body: dict, auth: bool = False):
        headers = {}
        if auth:
            s = self._secret()
            if not s:
                raise PlayitError(_t("playit bağlı değil."))
            headers["Authorization"] = f"Agent-Key {s}"
        try:
            async with new_client() as c:
                r = await c.post(self.api + path, json=body, headers=headers, timeout=20)
        except httpx.HTTPError:
            raise PlayitError(_t("playit.gg'ye ulaşılamadı. İnternet bağlantını kontrol et."))
        if r.status_code == 429:
            raise PlayitError(_t("playit.gg istek sınırına takıldı, biraz sonra tekrar dene."))
        try:
            j = r.json()
        except ValueError:
            raise PlayitError(_t('playit.gg yanıtı okunamadı (HTTP {status_code}).', status_code=r.status_code))
        st = j.get("status") if isinstance(j, dict) else None
        if st == "success":
            return j.get("data")
        if st == "fail":
            raise PlayitError(f"playit: {json.dumps(j.get('data'))[:200]}")
        if st == "error":
            d = j.get("data") or {}
            raise PlayitError(_t('playit hata: {v0} {v1}', v0=d.get('type', '?'), v1=json.dumps(d.get('message'))[:200]))
        raise PlayitError(_t('playit.gg beklenmeyen yanıt (HTTP {status_code}).', status_code=r.status_code))

    # ---------- kurulum ----------
    def ensure_install_job(self) -> Job:
        return self.jobs.start("playit", _t("playit kuruluyor"), "playit-install", self._install)

    async def _install(self, job: Job) -> dict:
        a = self.asset
        if not a:
            raise JobError(_t("Bu işletim sistemi/işlemci için playit desteklenmiyor (Windows x64 ve Linux x64)."))
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        dest = self.runtime_dir / a[0]
        if dest.is_file() and await asyncio.to_thread(_sha256, dest) == a[1]:
            return {"path": str(dest)}
        part = dest.with_name(dest.name + ".part")
        try:
            await download_file(job, RELEASE_URL.format(v=PLAYIT_VERSION, asset=a[0]), part, expected_sha256=a[1],
                                label=f"playit {PLAYIT_VERSION}")
            part.replace(dest)
        finally:
            part.unlink(missing_ok=True)
        if os.name != "nt":
            dest.chmod(0o755)
        job.update(100, "done", _t("playit hazır"))
        return {"path": str(dest)}

    # ---------- bağlama ----------
    def start_claim(self) -> dict:
        if self.linked():
            raise PlayitError(_t("playit zaten bağlı."))
        if self._claim and self._claim["state"] in ("waiting", "accepted"):
            return self.claim_info()
        code = secrets.token_hex(5)
        self._claim = {"code": code, "url": f"https://playit.gg/claim/{code}", "state": "waiting", "error": "",
                       "started": time.time()}
        self._claim["task"] = asyncio.get_running_loop().create_task(self._claim_loop(code))
        return self.claim_info()

    def claim_info(self) -> dict | None:
        c = self._claim
        return {"url": c["url"], "state": c["state"], "error": c["error"]} if c else None

    def cancel_claim(self) -> None:
        if self._claim and (t := self._claim.get("task")) and not t.done():
            t.cancel()
        self._claim = None

    async def _claim_loop(self, code: str) -> None:
        c = self._claim
        try:
            while time.time() - c["started"] < CLAIM_TIMEOUT:
                try:
                    res = await self._call("/claim/setup", {"code": code, "agent_type": "self-managed",
                                                            "version": f"vulu-panel playit {PLAYIT_VERSION}"})
                except PlayitError as e:
                    c["error"] = str(e)
                    await asyncio.sleep(3)
                    continue
                c["error"] = ""
                if res == "UserAccepted":
                    c["state"] = "accepted"
                    break
                if res == "UserRejected":
                    c["state"], c["error"] = "rejected", _t("Bağlantı playit.gg'de reddedildi.")
                    return
                await asyncio.sleep(2)
            else:
                c["state"], c["error"] = "expired", _t("Süre doldu, tekrar dene.")
                return
            for _ in range(30):
                try:
                    data = await self._call("/claim/exchange", {"code": code})
                    secret = str((data or {}).get("secret_key", "")).strip()
                    if not SECRET_RE.match(secret):
                        raise PlayitError(_t("playit geçersiz anahtar döndürdü."))
                    self._write_secret(secret)
                    break
                except PlayitError as e:
                    c["error"] = str(e)
                    await asyncio.sleep(2)
            else:
                c["state"] = "error"
                return
            c["state"], c["error"] = "done", ""
            self._rundata = None
            try:
                rd = await self.rundata(force=True)
                self._save_state({**self._state(), "agent_id": rd.get("agent_id")})
            except PlayitError:
                pass
            await self.start_agent()
        except asyncio.CancelledError:
            pass

    async def unlink(self) -> None:
        self.cancel_claim()
        await self.stop_agent()
        self.secret_file.unlink(missing_ok=True)
        self._save_state({})
        self._rundata = None

    # ---------- ajan süreci ----------
    def running(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    async def start_agent(self) -> None:
        if not self.linked():
            raise PlayitError(_t("Önce playit hesabını bağla."))
        if not self.installed():
            raise PlayitError(_t("playit kurulu değil."))
        if await asyncio.to_thread(_sha256, self.exe) != self.asset[1]:
            raise PlayitError(_t("playit dosyası doğrulanamadı (değiştirilmiş olabilir). Ayarlar'dan yeniden kur."))
        self._want_running = True
        if self.running():
            return
        self._spawn()
        if not self._watch or self._watch.done():
            self._watch = asyncio.get_running_loop().create_task(self._watchdog())

    def _spawn(self) -> None:
        cmd = [str(self.exe), "--secret_path", str(self.secret_file.resolve()), "-s", "start"]
        self._log(_t('[panel] playit {PLAYIT_VERSION} başlatılıyor', PLAYIT_VERSION=PLAYIT_VERSION))
        self._proc = subprocess.Popen(
            cmd, cwd=self.data_dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        p = self._proc

        def reader():
            try:
                for line in p.stdout:
                    self._log(line)
            except ValueError:
                pass
        threading.Thread(target=reader, daemon=True).start()

    async def _watchdog(self) -> None:
        delay = 5
        while self._want_running:
            await asyncio.sleep(3)
            if self._want_running and not self.running() and self.linked():
                code = self._proc.poll() if self._proc else None
                self._log(_t('[panel] playit kapandı (çıkış kodu: {code}); {delay} sn sonra yeniden başlatılıyor', code=code, delay=delay))
                await asyncio.sleep(delay)
                if self._want_running and not self.running():
                    try:
                        self._spawn()
                    except OSError as e:
                        self._log(_t('[panel] playit başlatılamadı: {e}', e=e))
                delay = min(delay * 2, 120)
            elif self.running():
                delay = 5

    async def stop_agent(self) -> None:
        self._want_running = False
        if self._watch:
            self._watch.cancel()
        p, self._proc = self._proc, None
        if p and p.poll() is None:
            p.terminate()
            try:
                await asyncio.to_thread(p.wait, 10)
            except subprocess.TimeoutExpired:
                p.kill()
        if p:
            self._log("[panel] playit durduruldu")

    async def autostart(self) -> None:
        """Panel açılırken: bağlıysa ve kuruluysa programı başlat (hata paneli durdurmaz)."""
        if self.linked() and self.installed():
            try:
                await self.start_agent()
            except PlayitError as e:
                self._log(f"[panel] {e}")

    # ---------- tüneller ----------
    async def rundata(self, force: bool = False) -> dict:
        if not force and self._rundata and time.time() - self._rundata[0] < 10:
            return self._rundata[1]
        data = await self._call("/agents/rundata", {}, auth=True)
        if not isinstance(data, dict):
            raise PlayitError(_t("playit beklenmeyen yanıt verdi."))
        self._rundata = (time.time(), data)
        return data

    @staticmethod
    def _tunnel_view(t: dict) -> dict | None:
        dom = str(t.get("custom_domain") or t.get("assigned_domain") or "")
        if not DOMAIN_RE.match(dom):
            return None
        port = (t.get("port") or {}).get("from")
        ttype = t.get("tunnel_type") or ""
        return {"id": str(t.get("id", ""))[:36], "name": str(t.get("name") or "")[:64], "type": ttype,
                "address": dom if ttype == "minecraft-java" or not port else f"{dom}:{port}",
                "alt": f"{dom}:{port}" if port else dom, "local_port": t.get("local_port"),
                "disabled": bool(t.get("disabled"))}

    async def tunnel_for(self, port: int) -> dict | None:
        rd = await self.rundata()
        for t in rd.get("tunnels") or []:
            if isinstance(t, dict) and t.get("local_port") == port and t.get("proto") in ("tcp", "both", None):
                return self._tunnel_view(t)
        return None

    async def create_tunnel(self, name: str, port: int) -> dict:
        rd = await self.rundata(force=True)
        if (t := await self.tunnel_for(port)):
            return t
        agent_id = str(rd.get("agent_id") or "")
        if not UUID_RE.match(agent_id):
            raise PlayitError(_t("playit ajan kimliği okunamadı."))
        safe = re.sub(r"[^A-Za-z0-9 _-]", "", f"vulu {name}")[:30] or "vulu"
        await self._call("/tunnels/create", {
            "name": safe, "tunnel_type": "minecraft-java", "port_type": "tcp", "port_count": 1,
            "origin": {"type": "agent", "data": {"agent_id": agent_id, "local_ip": "127.0.0.1", "local_port": port}},
            "enabled": True, "alloc": None, "firewall_id": None, "proxy_protocol": None,
        }, auth=True)
        for _ in range(10):                       # adres atanması birkaç saniye sürebilir
            await asyncio.sleep(1.5)
            self._rundata = None
            if (t := await self.tunnel_for(port)):
                return t
        raise PlayitError(_t("Tünel oluşturuldu ama adresi henüz atanmadı; birkaç saniye sonra sayfayı yenile."))

    async def delete_tunnel(self, port: int) -> None:
        t = await self.tunnel_for(port)
        if not t:
            return
        await self._call("/tunnels/delete", {"tunnel_id": t["id"]}, auth=True)
        self._rundata = None

    # ---------- durum ----------
    def status(self) -> dict:
        return {"supported": self.asset is not None, "installed": self.installed(), "linked": self.linked(),
                "running": self.running(), "claim": self.claim_info(), "version": PLAYIT_VERSION,
                "agent_id": self._state().get("agent_id"), "log": list(self.log)[-60:]}
