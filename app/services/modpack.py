"""Modrinth modpack (.mrpack) kurulumu.

.mrpack = zip: modrinth.index.json (sürüm/yükleyici + dosya listesi: yol, SHA-512, indirme adresi, ortam)
+ overrides/ (+ server-overrides/) ayar klasörleri. Panel: paketi indirip doğrular → tam yükleyici sürümünü
kurar (launcher) → sunucuda çalışmayan (env.server=unsupported) dosyaları atlayarak tüm dosyaları SHA-512
ile doğrulayıp indirir → override'ları açar. Hiçbir betik çalıştırılmaz; tehlikeli yollar/uzantılar atlanır.
"""
import asyncio
import hashlib
import json
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager
from .modrinth import ModrinthError, _NotFound

MANIFEST = ".vulu-modpack.json"
DEP_LOADER = {"fabric-loader": "fabric", "forge": "forge", "neoforge": "neoforge"}
PACK_HOSTS_EXTRA = {"github.com", "raw.githubusercontent.com", "gitlab.com"}          # .mrpack şartnamesinin izin verdikleri
DENY_TOP = {".vulu-jar.json", ".vulu-mods.json", ".vulu-modpack.json", "eula.txt", "user_jvm_args.txt",
            "libraries", "versions", "logs", "crash-reports", ".fabric"}
DENY_EXT = {".exe", ".bat", ".cmd", ".ps1", ".sh", ".dll", ".so", ".dylib", ".msi", ".com", ".scr", ".vbs", ".jar.part"}
BAD_CHARS = re.compile(r'[\x00-\x1f:*?"<>|\\]')
MAX_FILES, MAX_INDEX, MAX_UNZIPPED, MAX_ENTRY, PARALLEL = 3000, 5 * 2**20, 3 * 2**30, 1 * 2**30, 6


def read_pack_info(folder: Path) -> dict | None:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def safe_rel(path: str) -> str | None:
    """Sunucu klasörüne göre güvenli göreli yol ya da None (mutlak, '..', yasaklı klasör/uzantı)."""
    if not isinstance(path, str) or not path or len(path) > 240 or BAD_CHARS.search(path):
        return None
    p = PurePosixPath(path)
    if p.is_absolute() or any(x in ("", ".", "..") for x in p.parts) or p.parts[0] in DENY_TOP:
        return None
    if p.suffix.lower() in DENY_EXT:
        return None
    return p.as_posix()


def _inside(folder: Path, rel: str) -> Path | None:
    dest = (folder / rel).resolve()
    return dest if dest.is_relative_to(folder.resolve()) else None


_REL_RE = re.compile(r"^\d+(\.\d+){1,3}$")


def _mc_range(versions) -> str:
    """Arama sonucundaki Minecraft sürümleri → "1.20.1" ya da "1.19.2–1.20.1" (yalnızca kararlı sürümler).
    Not: Modrinth'in `latest_version` alanı bir sürüm kimliğidir (örn. WMsE2fOj), Minecraft sürümü değildir."""
    rel = [str(v) for v in (versions or []) if isinstance(v, str) and _REL_RE.match(v)]
    if not rel:
        return ""
    rel.sort(key=lambda v: tuple(int(x) for x in v.split(".")))
    return rel[-1] if len(rel) == 1 else f"{rel[0]}–{rel[-1]}"


class ModpackManager:
    def __init__(self, api_base: str, cdn_hosts: list[str], cache_dir: Path, jobs: JobManager, mods) -> None:
        self.cdn, self.cache, self.jobs, self.mods = set(cdn_hosts), cache_dir, jobs, mods
        self.hosts = self.cdn | PACK_HOSTS_EXTRA

    def _host_ok(self, url: str, hosts: set[str]) -> bool:
        u = urlparse(url)
        return u.scheme in ("http", "https") and (u.hostname or "") in hosts

    # ---------- arama / sürüm bilgisi ----------
    async def search(self, query: str, offset: int = 0, limit: int = 20) -> dict:
        facets = [["project_type:modpack"], ["server_side:required", "server_side:optional"],
                  ["categories:fabric", "categories:forge", "categories:neoforge"]]
        data = await self.mods._get("/search", {"query": query[:100], "facets": json.dumps(facets), "limit": limit,
                                                "offset": offset, "index": "relevance" if query.strip() else "downloads"})
        hits = []
        for h in data.get("hits", []):
            slug = str(h.get("slug", ""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}", slug):
                continue
            icon = str(h.get("icon_url") or ""); ih = urlparse(icon).hostname or ""
            hits.append({"slug": slug, "title": str(h.get("title", ""))[:100], "description": str(h.get("description", ""))[:300],
                         "downloads": int(h.get("downloads") or 0), "author": str(h.get("author", ""))[:50],
                         "mc": _mc_range(h.get("versions")),
                         "loaders": [c for c in h.get("categories", []) if c in ("fabric", "forge", "neoforge")],
                         "icon": icon if icon.startswith("https://") and (ih == "modrinth.com" or ih.endswith(".modrinth.com")) else ""})
        return {"hits": hits, "total": int(data.get("total_hits") or 0)}

    async def version_info(self, slug: str, version_id: str | None = None) -> dict:
        """Modpack'in (belirtilmediyse en yeni release) sürümünü ve gereken yükleyici/Minecraft bilgisini döndürür."""
        try:
            proj = await self.mods._get(f"/project/{slug}")
        except _NotFound:
            raise ModrinthError("Modpack Modrinth'te bulunamadı.")
        if proj.get("project_type") != "modpack":
            raise ModrinthError("Bu proje bir modpack değil.")
        if proj.get("server_side") == "unsupported":
            raise ModrinthError("Bu modpack sunucu desteği sunmuyor.")
        if version_id:
            if not re.fullmatch(r"[A-Za-z0-9]{4,20}", version_id):
                raise ModrinthError("Geçersiz modpack sürümü.")
            try:
                v = await self.mods._get(f"/version/{version_id}")
            except _NotFound:
                raise ModrinthError("Modpack sürümü bulunamadı.")
            if v.get("project_id") != proj["id"]:
                raise ModrinthError("Sürüm bu modpack'e ait değil.")
        else:
            vs = await self.mods._get(f"/project/{proj['id']}/version")
            v = next((x for x in vs if x.get("version_type") == "release"), vs[0] if vs else None)
            if not v:
                raise ModrinthError("Bu modpack'in sürümü yok.")
        loaders = [x for x in v.get("loaders", []) if x in ("fabric", "forge", "neoforge")]
        if not loaders:
            raise ModrinthError("Bu modpack'in yükleyicisi desteklenmiyor (Fabric / Forge / NeoForge gerekli).")
        mcs = v.get("game_versions") or []
        if not mcs or not re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", mcs[0]):
            raise ModrinthError("Modpack'in Minecraft sürümü okunamadı.")
        files = v.get("files") or []
        f = next((x for x in files if x.get("primary")), files[0] if files else None)
        if not f or not str(f.get("filename", "")).endswith(".mrpack") or not (f.get("hashes") or {}).get("sha512"):
            raise ModrinthError("Modpack dosyası (.mrpack) bulunamadı.")
        if not self._host_ok(f.get("url", ""), self.cdn):
            raise ModrinthError("Beklenmeyen indirme adresi reddedildi.")
        return {"slug": proj.get("slug", slug), "title": proj.get("title", slug), "project_id": proj["id"], "version_id": v["id"],
                "version_number": v.get("version_number", ""), "mc_version": mcs[0], "loader": loaders[0],
                "file": {"url": f["url"], "sha512": f["hashes"]["sha512"], "size": int(f.get("size") or 0), "filename": f["filename"]}}

    # ---------- 1) .mrpack'i indir ve oku ----------
    def ensure_pack_job(self, iid: int, info: dict) -> Job:
        return self.jobs.start("modpack", f"{info['title']} indiriliyor", f"modpack-dl-{iid}", lambda j: self._fetch_pack(j, info))

    async def _fetch_pack(self, job: Job, info: dict) -> dict:
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / f"{info['version_id']}.mrpack"
        f = info["file"]
        if not path.is_file() or hashlib.sha512(path.read_bytes()).hexdigest() != f["sha512"].lower():
            part = path.with_name(path.name + ".part")
            try:
                await download_file(job, f["url"], part, expected_sha512=f["sha512"], size_hint=f["size"],
                                    start_pct=2, span_pct=80, label=f"{info['title']} paketi")
                part.replace(path)
            finally:
                part.unlink(missing_ok=True)
        job.update(90, "read", "Paket okunuyor…")
        idx = await asyncio.to_thread(self._read_index, path)
        deps = idx["dependencies"]
        key = next((k for k in deps if k in DEP_LOADER), None)
        if not key:
            raise JobError("Bu modpack desteklenmeyen bir yükleyici kullanıyor (Quilt vb.). Fabric / Forge / NeoForge gerekli.")
        if DEP_LOADER[key] != info["loader"] or deps.get("minecraft") != info["mc_version"]:
            raise JobError("Modpack içeriği Modrinth bilgisiyle uyuşmuyor (sürüm/yükleyici).")
        return {"path": str(path), "loader_version": str(deps[key]), "files": len(idx.get("files", []))}

    @staticmethod
    def _read_index(path: Path) -> dict:
        try:
            with zipfile.ZipFile(path) as zf:
                zi = zf.getinfo("modrinth.index.json")
                if zi.file_size > MAX_INDEX:
                    raise JobError("modrinth.index.json çok büyük.")
                idx = json.loads(zf.read(zi))
        except KeyError:
            raise JobError("Geçersiz .mrpack: modrinth.index.json yok.")
        except (zipfile.BadZipFile, ValueError):
            raise JobError("Geçersiz .mrpack dosyası.")
        if idx.get("formatVersion") != 1 or idx.get("game") != "minecraft" or not isinstance(idx.get("dependencies"), dict) \
                or not isinstance(idx.get("files", []), list) or len(idx.get("files", [])) > MAX_FILES:
            raise JobError("Desteklenmeyen .mrpack biçimi.")
        return idx

    # ---------- 2) dosyaları ve override'ları kur ----------
    def ensure_install_job(self, iid: int, folder: Path, pack: dict) -> Job:
        return self.jobs.start("modpack", f"{pack['title']} kuruluyor", f"modpack-install-{iid}", lambda j: self._install(j, folder, pack))

    async def _install(self, job: Job, folder: Path, pack: dict) -> dict:
        job.update(1, "read", "Dosya listesi okunuyor…")
        idx = await asyncio.to_thread(self._read_index, Path(pack["path"]))
        warnings: list[str] = []
        jobs_: list[tuple[str, str, str, int]] = []                     # (rel, url, sha512, size)
        skipped = 0
        seen: dict[str, str] = {}
        for f in idx.get("files", []):
            rel = safe_rel(f.get("path"))
            if rel is None:
                warnings.append(f"Güvensiz dosya yolu atlandı: {str(f.get('path'))[:80]}")
                continue
            if (f.get("env") or {}).get("server") == "unsupported":
                skipped += 1
                continue
            sha = str((f.get("hashes") or {}).get("sha512", ""))
            url = next((u for u in f.get("downloads", []) if isinstance(u, str) and self._host_ok(u, self.hosts)), None)
            if not sha or not url:
                raise JobError(f"{rel}: doğrulanabilir/izinli indirme adresi yok, kurulum durduruldu.")
            if _inside(folder, rel) is None:
                warnings.append(f"Klasör dışına çıkan yol atlandı: {rel}")
                continue
            if rel in seen:                                  # aynı yol iki kez listelenmişse tek kez indir
                if seen[rel] != sha.lower():
                    warnings.append(f"Aynı yol için farklı dosyalar listelenmiş, ilki kullanıldı: {rel}")
                continue
            seen[rel] = sha.lower()
            jobs_.append((rel, url, sha, int(f.get("fileSize") or 0)))
        total, done, sem = max(len(jobs_), 1), [0], asyncio.Semaphore(PARALLEL)
        size_diff = [0]

        async def one(client, rel, url, sha, size):
            async with sem:
                dest = _inside(folder, rel)
                if dest.is_file() and hashlib.sha512(dest.read_bytes()).hexdigest() == sha.lower():
                    done[0] += 1
                    return
                part = dest.with_name(f"{dest.name}.{uuid.uuid4().hex[:8]}.part")     # her indirmenin kendi geçici dosyası
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    for attempt in (1, 2, 3):                       # geçici ağ/bozulma hatalarında 3 deneme
                        h, n, meta = hashlib.sha512(), 0, "?"
                        try:
                            async with client.stream("GET", url) as r:
                                r.raise_for_status()
                                meta = f"HTTP {r.status_code}, {r.headers.get('content-type', '?')}, kodlama {r.headers.get('content-encoding', '-')}"
                                with open(part, "wb") as out:
                                    async for chunk in r.aiter_bytes(65536):
                                        n += len(chunk)
                                        if n > MAX_ENTRY:
                                            raise JobError(f"{rel}: dosya çok büyük.")
                                        out.write(chunk); h.update(chunk)
                        except (httpx.HTTPError, OSError) as e:
                            if attempt == 3:
                                raise JobError(f"{rel}: indirilemedi ({e.__class__.__name__}).")
                            continue
                        if h.hexdigest() == sha.lower():             # içeriği SHA-512 doğrular; fileSize yalnızca bilgi
                            if size and n != size:
                                size_diff[0] += 1
                            break
                        if attempt == 3:
                            raise JobError(f"{rel}: doğrulanamadı — sha512 beklenen {sha[:12]}…, gelen {h.hexdigest()[:12]}…; "
                                           f"boyut beklenen {size}, gelen {n}; {meta}")
                    part.replace(dest)
                finally:
                    part.unlink(missing_ok=True)
            done[0] += 1
            job.update(5 + 85 * done[0] / total, "download", f"[{done[0]}/{len(jobs_)}] {PurePosixPath(rel).name}")

        async with new_client() as client:
            tasks = [asyncio.create_task(one(client, *j)) for j in jobs_]
            if tasks:
                finished, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                errs = [t.exception() for t in finished if t.exception()]      # hepsini oku (işlenmemiş hata uyarısı kalmasın)
                err = errs[0] if errs else None
                if err:
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    raise err
        if size_diff[0]:
            warnings.append(f"{size_diff[0]} dosyada paketin listesindeki boyut gerçek boyuttan farklı (paket hazırlayıcının hatası); "
                            "SHA-512 doğru olduğu için kuruldu.")
        job.update(92, "overrides", "Ayar dosyaları açılıyor…")
        n_over = await asyncio.to_thread(self._extract_overrides, Path(pack["path"]), folder, warnings)
        (folder / MANIFEST).write_text(json.dumps({
            "slug": pack["slug"], "title": pack["title"], "version_id": pack["version_id"], "version": pack["version_number"],
            "mc": pack["mc_version"], "loader": pack["loader"], "loader_version": pack["loader_version"],
            "files": len(jobs_), "skipped_client": skipped, "overrides": n_over, "warnings": warnings,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }), encoding="utf-8")
        return {"files": len(jobs_), "skipped": skipped, "overrides": n_over, "warnings": warnings}

    @staticmethod
    def _extract_overrides(pack_path: Path, folder: Path, warnings: list[str]) -> int:
        count = total = 0
        with zipfile.ZipFile(pack_path) as zf:
            for prefix in ("overrides/", "server-overrides/"):        # server-overrides sonra: üzerine yazar
                for zi in zf.infolist():
                    if not zi.filename.startswith(prefix) or zi.is_dir():
                        continue
                    rel = safe_rel(zi.filename[len(prefix):])
                    dest = _inside(folder, rel) if rel else None
                    if dest is None:
                        warnings.append(f"Yasaklı/güvensiz ayar dosyası atlandı: {zi.filename[:80]}")
                        continue
                    total += zi.file_size
                    if zi.file_size > MAX_ENTRY or total > MAX_UNZIPPED or count > 50000:
                        raise JobError("Modpack ayar dosyaları çok büyük.")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(zi) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    count += 1
        return count
