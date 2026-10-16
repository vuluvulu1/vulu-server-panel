"""vulu Packs: vulu Launcher'dan paylaşılan paketlerden sunucu kurulumu.

Panel bir vulu hesabına bir kez bağlanır: kullanıcı adı ve şifreyle giriş yapılır, vulu-api'den yalnızca
paketleri okuyabilen bir panel token'ı (vpt_…) alınır ve data/vulu-account.json'a yazılır. Şifre saklanmaz.

Kurulum, Modrinth modpack'leriyle aynı yoldan geçer: paket bir .mrpack'e çevrilir (modrinth.index.json +
overrides/), sonra ModpackManager onu indirir, doğrular ve açar. Sunucuya gerekmeyenler atlanır:
  - Modrinth'te server_side=unsupported olan modlar, kaynak paketleri ve shaderlar,
  - paket dosyalarındaki istemci klasörleri/dosyaları (resourcepacks, shaderpacks, options.txt…),
  - paket dosyalarındaki, kendini yalnızca istemci olarak tanımlayan mod jar'ları.
Paket güncellenince önceki revizyondan gelip artık listede olmayan mod dosyaları kaldırılır.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import socket
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from ..config import CACHE_DIR, DATA_DIR, VULU_API
from ..i18n import _t
from .http import new_client
from .jobs import Job, JobError, JobManager
from .modcheck import _scan_zip
from .modpack import safe_rel

ACCOUNT_FILE = DATA_DIR / "vulu-account.json"
MANIFEST = ".vulu-pack.json"
CACHE = CACHE_DIR / "vulupacks"
LOADER_KEYS = {"fabric": "fabric-loader", "forge": "forge", "neoforge": "neoforge", "vanilla": None}
# Sunucuda işe yaramayan, yalnızca oyuncunun bilgisayarında anlamlı olan paket dosyaları
CLIENT_ONLY_TOP = {"resourcepacks", "shaderpacks", "options.txt", "optionsshaders.txt", "servers.dat", "vulu-pack.json",
                   "fancymenu_data", "screenshots", "saves", "journeymap", "xaero", "schematics", "replay_recordings"}
MAX_OVERRIDES = 250 * 1048576
_ID = re.compile(r"^[0-9a-f]{24}$")
_VER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")


class VuluPackError(Exception):
    """Kullanıcıya gösterilebilir hata."""


def valid_id(pack_id: str) -> bool:
    return bool(_ID.match(pack_id or ""))


def read_installed(folder: Path) -> dict | None:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class VuluPacks:
    def __init__(self, jobs: JobManager, mods) -> None:
        self.jobs, self.mods = jobs, mods

    # ---------- hesap ----------
    @staticmethod
    def account() -> dict | None:
        try:
            a = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
            return a if isinstance(a.get("token"), str) and a["token"].startswith("vpt_") else None
        except (OSError, ValueError, AttributeError):
            return None

    @staticmethod
    def _api_error(r: httpx.Response, fallback: str) -> VuluPackError:
        try:
            msg = r.json().get("error")
        except ValueError:
            msg = None
        return VuluPackError(str(msg)[:300] if msg else fallback)

    async def link(self, username: str, password: str) -> dict:
        try:
            async with new_client() as c:
                r = await c.post(f"{VULU_API}/auth/login", json={"username": username, "password": password}, timeout=75)
                if r.status_code != 200:
                    raise self._api_error(r, _t("Giriş yapılamadı."))
                jwt = r.json().get("token")
                r = await c.post(f"{VULU_API}/users/me/panel-token", json={"label": f"vulu panel · {socket.gethostname()[:30]}"},
                                 headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
                if r.status_code != 200:
                    raise self._api_error(r, _t("Panel bağlantısı oluşturulamadı."))
                data = r.json()
        except httpx.HTTPError:
            raise VuluPackError(_t("vulu hesap sunucusuna ulaşılamadı. Biraz sonra tekrar dene."))
        token, user = str(data.get("token") or ""), str(data.get("username") or username)
        if not token.startswith("vpt_"):
            raise VuluPackError(_t("vulu hesap sunucusundan beklenmeyen yanıt geldi."))
        ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACCOUNT_FILE.write_text(json.dumps({"username": user, "token": token, "linked_at": time.strftime("%Y-%m-%d %H:%M")}), encoding="utf-8")
        return {"username": user}

    async def unlink(self) -> None:
        acc = self.account()
        if acc:
            try:
                async with new_client() as c:
                    await c.delete(f"{VULU_API}/users/me/panel-token", headers={"Authorization": f"Bearer {acc['token']}"}, timeout=20)
            except httpx.HTTPError:
                pass                                          # bağlantı yine de bu panelden kaldırılır
        ACCOUNT_FILE.unlink(missing_ok=True)

    async def _get(self, path: str, timeout: float = 75):
        acc = self.account()
        if not acc:
            raise VuluPackError(_t("Panel bir vulu hesabına bağlı değil."))
        try:
            async with new_client() as c:
                r = await c.get(f"{VULU_API}{path}", headers={"Authorization": f"Bearer {acc['token']}"}, timeout=timeout)
        except httpx.HTTPError:
            raise VuluPackError(_t("vulu hesap sunucusuna ulaşılamadı. Biraz sonra tekrar dene."))
        if r.status_code == 401:
            ACCOUNT_FILE.unlink(missing_ok=True)
            raise self._api_error(r, _t("Panel bağlantısı geçersiz; vulu hesabını yeniden bağla."))
        if r.status_code != 200:
            raise self._api_error(r, _t("vulu hesap sunucusu hata verdi (HTTP {s}).", s=r.status_code))
        return r.json()

    # ---------- paketler ----------
    @staticmethod
    def _summary(p: dict) -> dict:
        mods = p.get("mods") or []
        return {
            "id": p["id"], "name": p.get("name", ""), "description": p.get("description", ""), "author": p.get("author", ""),
            "mc_version": p.get("mcVersion", ""), "loader": p.get("loader", ""), "loader_version": p.get("loaderVersion"),
            "revision": int(p.get("revision") or 1), "updated_at": p.get("updatedAt"),
            "ram_gb": int(p.get("recommendedRamGb") or 8),
            "mod_count": sum(1 for m in mods if m.get("type", "mod") == "mod"),
            "includes": p.get("includes") or [],
            "cover_url": f"{VULU_API}/packs/{p['id']}/cover" if p.get("hasCover") else None,
            "supported": p.get("loader") in LOADER_KEYS,
        }

    async def list(self) -> list[dict]:
        data = await self._get("/packs")
        return [self._summary(p) for p in data if isinstance(p, dict) and valid_id(str(p.get("id", "")))]

    async def get(self, pack_id: str) -> dict:
        if not valid_id(pack_id):
            raise VuluPackError(_t("Paket bulunamadı."))
        p = await self._get(f"/packs/{pack_id}")
        if not isinstance(p, dict) or p.get("id") != pack_id:
            raise VuluPackError(_t("Paket bulunamadı."))
        if p.get("loader") not in LOADER_KEYS:
            raise VuluPackError(_t("Bu paketin yükleyicisi ({l}) panelde desteklenmiyor.", l=p.get("loader")))
        if not _VER.match(str(p.get("mcVersion", ""))) or (p["loader"] != "vanilla" and not _VER.match(str(p.get("loaderVersion") or ""))):
            raise VuluPackError(_t("Paketin sürüm bilgisi geçersiz."))
        return p

    # ---------- .mrpack'e çevirme ----------
    def ensure_build_job(self, iid: int, pack_id: str) -> Job:
        return self.jobs.start("vulupack", _t("vulu paketi hazırlanıyor"), f"vulupack-{iid}", lambda j: self._build(j, pack_id))

    async def _build(self, job: Job, pack_id: str) -> dict:
        job.update(2, "read", _t("Paket bilgisi alınıyor…"))
        try:
            p = await self.get(pack_id)
        except VuluPackError as e:
            raise JobError(str(e))
        rev = int(p.get("revision") or 1)
        CACHE.mkdir(parents=True, exist_ok=True)
        target = CACHE / f"{pack_id}-r{rev}.mrpack"

        # Modrinth: sunucuda çalışmayan modlar
        job.update(8, "read", _t("Modların sunucu desteği denetleniyor…"))
        mods = [m for m in (p.get("mods") or []) if isinstance(m, dict)]
        ids = sorted({str(m.get("projectId")) for m in mods if m.get("type", "mod") == "mod" and m.get("projectId")})
        server_side: dict[str, str] = {}
        for i in range(0, len(ids), 100):
            try:
                for proj in await self.mods._get("/projects", {"ids": json.dumps(ids[i:i + 100])}):
                    server_side[proj["id"]] = proj.get("server_side", "")
            except Exception:
                pass                                          # bilinmiyorsa kurulur; açılışta istemci modu uyarısı çıkar

        files, skipped = [], []
        for m in mods:
            title = str(m.get("title") or m.get("file") or "?")[:80]
            if m.get("type", "mod") != "mod":               # kaynak paketi / shader: yalnızca oyuncuda
                continue
            rel = safe_rel(str(m.get("file") or ""))
            sha512 = str(m.get("sha512") or "")
            url = str(m.get("url") or "")
            if not rel or not rel.startswith("mods/") or not re.fullmatch(r"[0-9a-f]{128}", sha512) or not url.startswith("https://cdn.modrinth.com/"):
                skipped.append(title)
                continue
            env = "unsupported" if server_side.get(str(m.get("projectId"))) == "unsupported" else "required"
            if env == "unsupported":
                skipped.append(title)
            files.append({"path": rel, "hashes": {"sha512": sha512, "sha1": str(m.get("sha1") or "")},
                          "env": {"client": "required", "server": env}, "downloads": [url], "fileSize": int(m.get("size") or 0)})

        # Paket dosyaları (config, kubejs…)
        job.update(15, "download", _t("Paket dosyaları indiriliyor…"))
        over = CACHE / f"{pack_id}-r{rev}-overrides.zip"
        if not over.is_file():
            await self._download_overrides(job, pack_id, over, int(p.get("overridesSize") or 0))

        job.update(80, "read", _t("Sunucu paketi oluşturuluyor…"))
        deps = {"minecraft": p["mcVersion"]}
        if key := LOADER_KEYS[p["loader"]]:
            deps[key] = p["loaderVersion"]
        index = {"formatVersion": 1, "game": "minecraft", "versionId": f"r{rev}", "name": p["name"], "files": files, "dependencies": deps}
        client_jars = await asyncio.to_thread(self._write_mrpack, target, index, over)
        return {"path": str(target), "loader_version": p.get("loaderVersion") or "", "title": p["name"], "slug": f"vulu:{pack_id}",
                "version_id": f"r{rev}", "version_number": f"rev {rev}", "mc_version": p["mcVersion"], "loader": p["loader"],
                "pack_id": pack_id, "revision": rev, "skipped_client": [s for s in skipped] + client_jars}

    async def _download_overrides(self, job: Job, pack_id: str, dest: Path, size: int) -> None:
        acc = self.account()
        if not acc:
            raise JobError(_t("Panel bir vulu hesabına bağlı değil."))
        part = dest.with_name(dest.name + ".part")
        try:
            async with new_client() as c:
                async with c.stream("GET", f"{VULU_API}/packs/{pack_id}/overrides", headers={"Authorization": f"Bearer {acc['token']}"},
                                    timeout=httpx.Timeout(120, connect=75)) as r:
                    if r.status_code != 200:
                        raise JobError(_t("Paket dosyaları indirilemedi (HTTP {s}).", s=r.status_code))
                    n = 0
                    with open(part, "wb") as out:
                        async for chunk in r.aiter_bytes(65536):
                            n += len(chunk)
                            if n > MAX_OVERRIDES:
                                raise JobError(_t("Paket dosyaları çok büyük."))
                            out.write(chunk)
                            if size:
                                job.update(15 + 60 * min(n / size, 1), "download", _t("Paket dosyaları indiriliyor… {a} / {b} MB", a=f"{n / 1048576:.1f}", b=f"{size / 1048576:.1f}"))
            if size and n != size:
                raise JobError(_t("Paket dosyaları eksik indi; tekrar dene."))
            part.replace(dest)
        except httpx.HTTPError:
            raise JobError(_t("Paket dosyaları indirilemedi. İnternet bağlantını kontrol et."))
        finally:
            part.unlink(missing_ok=True)

    @staticmethod
    def _client_only_jar(data: bytes) -> bool:
        out = {"provided": set(), "requires": {}, "client_only": [], "unreadable": []}
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                _scan_zip(z, "jar", out, 0)
        except (zipfile.BadZipFile, OSError, RuntimeError):
            return False
        return bool(out["client_only"])

    def _write_mrpack(self, target: Path, index: dict, overrides: Path) -> list[str]:
        """modrinth.index.json + overrides/ (istemci dosyaları hariç). Atlanan istemci mod jar'larının adlarını döner."""
        client_jars: list[str] = []
        part = target.with_name(target.name + ".part")
        try:
            with zipfile.ZipFile(overrides) as src, zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as out:
                out.writestr("modrinth.index.json", json.dumps(index))
                for zi in src.infolist():
                    if zi.is_dir():
                        continue
                    parts = PurePosixPath(zi.filename).parts
                    if not parts or parts[0].lower() in CLIENT_ONLY_TOP or parts[0].lower() == "instance.json":
                        continue
                    data = src.read(zi)
                    if parts[0].lower() == "mods" and zi.filename.lower().endswith(".jar") and len(parts) == 2 and self._client_only_jar(data):
                        client_jars.append(parts[1])
                        continue
                    out.writestr("overrides/" + zi.filename, data)
            part.replace(target)
        except zipfile.BadZipFile:
            raise JobError(_t("Paket dosyaları bozuk."))
        finally:
            part.unlink(missing_ok=True)
        return client_jars

    # ---------- kurulum sonrası ----------
    @staticmethod
    def finish(folder: Path, pack: dict) -> list[str]:
        """Önceki revizyondan gelip artık pakette olmayan mod dosyalarını siler, kurulum bilgisini yazar.
        Silinen dosyaların adlarını döner."""
        with zipfile.ZipFile(pack["path"]) as z:
            idx = json.loads(z.read("modrinth.index.json"))
            over_mods = {n[len("overrides/"):] for n in z.namelist() if n.startswith("overrides/mods/")}
        now = {f["path"] for f in idx["files"] if f["env"]["server"] != "unsupported"} | over_mods
        removed = []
        prev = read_installed(folder) or {}
        for rel in prev.get("mods", []):
            if rel in now or not isinstance(rel, str) or safe_rel(rel) is None or not rel.startswith("mods/"):
                continue
            path = (folder / rel).resolve()
            if path.is_relative_to(folder.resolve()) and path.is_file():
                path.unlink()
                removed.append(PurePosixPath(rel).name)
        (folder / MANIFEST).write_text(json.dumps({
            "pack_id": pack["pack_id"], "name": pack["title"], "revision": pack["revision"], "mods": sorted(now),
            "skipped_client": pack.get("skipped_client", []), "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }), encoding="utf-8")
        return removed
