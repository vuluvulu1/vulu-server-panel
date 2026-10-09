"""Modrinth'ten mod / eklenti kurulumu (API v2, anahtar gerekmez).

Her istenen proje için: sunucuyu destekliyor mu (client-only ise atlanır) → seçilen Minecraft sürümü ve
yükleyiciye uygun en yeni kararlı sürüm → gerekli (required) bağımlılıklar da aynı şekilde → dosya SHA-512
ile doğrulanarak mods/ (Paper'da plugins/) klasörüne indirilir.
Bulunamayan / uygun sürümü olmayan mod uyarıyla atlanır; indirme veya doğrulama hatası kurulumu durdurur.
Yalnızca panelin kurduğu dosyalar (.vulu-mods.json'da kayıtlı) güncellenir/silinir; senin eklediğin dosyalara dokunulmaz.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .download import download_file
from .http import new_client
from .jobs import Job, JobError, JobManager

MANIFEST = ".vulu-mods.json"
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")
FILENAME = re.compile(r"^[A-Za-z0-9._+()\[\] -]{1,150}\.jar$")
FILENAME_ANY = re.compile(r"^[A-Za-z0-9._+()\[\] -]{1,150}\.jar(\.disabled)?$")
LOADER_FILTER = {"paper": ["paper", "spigot", "bukkit"], "fabric": ["fabric"], "forge": ["forge"], "neoforge": ["neoforge"]}
TARGET_DIR = {"paper": "plugins"}                 # diğerleri: mods
MAX_MODS = 200


class ModrinthError(Exception):
    pass


class _NotFound(ModrinthError):
    pass


def read_mods_info(folder: Path) -> dict | None:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def target_dir(loader: str) -> str:
    return TARGET_DIR.get(loader, "mods")


class ModManager:
    def __init__(self, api_base: str, cdn_hosts: list[str], jobs: JobManager) -> None:
        self.api, self.cdn, self.jobs = api_base.rstrip("/"), set(cdn_hosts), jobs

    async def _get(self, path: str, params: dict | None = None):
        try:
            async with new_client() as c:
                r = await c.get(self.api + path, params=params)
        except httpx.HTTPError:
            raise ModrinthError("Modrinth'e ulaşılamadı. İnternet bağlantını kontrol et.")
        if r.status_code == 404:
            raise _NotFound("bulunamadı")
        if r.status_code == 429:
            raise ModrinthError("Modrinth istek sınırına takıldı. Birkaç dakika sonra tekrar dene.")
        try:
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            raise ModrinthError("Modrinth yanıtı okunamadı.")

    async def _post(self, path: str, body: dict):
        try:
            async with new_client() as c:
                r = await c.post(self.api + path, json=body)
        except httpx.HTTPError:
            raise ModrinthError("Modrinth'e ulaşılamadı. İnternet bağlantını kontrol et.")
        if r.status_code == 429:
            raise ModrinthError("Modrinth istek sınırına takıldı. Birkaç dakika sonra tekrar dene.")
        try:
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            raise ModrinthError("Modrinth yanıtı okunamadı.")

    async def resolve(self, slugs: list[str], mc: str, loader: str) -> tuple[list[dict], list[str]]:
        loaders = LOADER_FILTER.get(loader)
        if not loaders:
            raise ModrinthError("Bu yükleyici için Modrinth kurulumu desteklenmiyor.")
        resolved: dict[str, dict] = {}
        skipped: set[str] = set()
        warnings: list[str] = []
        queue: list[tuple[str, str | None]] = [(s, None) for s in slugs]
        while queue:
            key, pinned = queue.pop(0)
            if len(resolved) >= MAX_MODS:
                raise ModrinthError(f"Çok fazla mod (en fazla {MAX_MODS}).")
            try:
                proj = await self._get(f"/project/{key}")
            except _NotFound:
                warnings.append(f"'{key}' Modrinth'te bulunamadı, atlandı.")
                continue
            pid, title = proj["id"], proj.get("title", key)
            if pid in resolved or pid in skipped:
                continue
            if proj.get("project_type") not in ("mod", "plugin"):
                skipped.add(pid)
                warnings.append(f"{title} bir mod/eklenti değil, atlandı.")
                continue
            if proj.get("server_side") == "unsupported":
                skipped.add(pid)
                warnings.append(f"{title} yalnızca istemci modu, sunucuya kurulmadı.")
                continue
            ver = None
            if pinned:                                     # bağımlılık belirli bir sürüm istiyorsa onu dene
                try:
                    v = await self._get(f"/version/{pinned}")
                    if mc in v.get("game_versions", []) and set(loaders) & set(v.get("loaders", [])):
                        ver = v
                except _NotFound:
                    pass
            if ver is None:
                vs = await self._get(f"/project/{pid}/version",
                                     {"loaders": json.dumps(loaders), "game_versions": json.dumps([mc])})
                if not vs:
                    skipped.add(pid)
                    warnings.append(f"{title} için {mc}/{loader} sürümü yok, atlandı.")
                    continue
                ver = next((v for v in vs if v.get("version_type") == "release"), vs[0])
            files = ver.get("files") or []
            f = next((x for x in files if x.get("primary")), files[0] if files else None)
            if not f or not FILENAME.match(f.get("filename", "")):
                raise ModrinthError(f"{title}: geçersiz dosya adı.")
            url = f.get("url", "")
            if urlparse(url).scheme not in ("https", "http") or (urlparse(url).hostname or "") not in self.cdn:
                raise ModrinthError(f"{title}: beklenmeyen indirme adresi reddedildi.")
            resolved[pid] = {
                "slug": proj.get("slug", key), "title": title, "project_id": pid, "version_id": ver["id"],
                "version": ver.get("version_number", ""), "filename": f["filename"], "url": url,
                "sha512": (f.get("hashes") or {}).get("sha512", ""), "sha1": (f.get("hashes") or {}).get("sha1", ""),
                "size": int(f.get("size") or 0),
            }
            for d in ver.get("dependencies", []):
                if d.get("dependency_type") == "required" and d.get("project_id") and d["project_id"] not in resolved:
                    queue.append((d["project_id"], d.get("version_id")))
        return list(resolved.values()), warnings

    def ensure_install_job(self, iid: int, folder: Path, mc: str, loader: str, slugs: list[str]) -> Job:
        kind = "eklenti" if loader == "paper" else "mod"
        return self.jobs.start("mods", f"Modrinth {kind}leri kuruluyor", f"mods-{iid}",
                               lambda j: self._install(j, folder, mc, loader, slugs))

    # ---------- ortak yardımcılar ----------
    @staticmethod
    def _unlink(target: Path, fn: str) -> None:
        if FILENAME.match(fn):
            for name in (fn, fn + ".disabled"):
                (target / name).unlink(missing_ok=True)

    async def _fetch(self, job: Job, target: Path, entries: list[dict], old_mods: dict) -> None:
        n = max(len(entries), 1)
        for i, e in enumerate(entries):
            dest, dis = target / e["filename"], target / (e["filename"] + ".disabled")
            prev = old_mods.get(e["project_id"], {})
            if prev.get("version_id") == e["version_id"] and (dest.is_file() or dis.is_file()):
                job.update(5 + 90 * (i + 1) / n, "download", f"[{i + 1}/{len(entries)}] {e['title']} zaten kurulu")
                continue
            part = target / (e["filename"] + ".part")
            try:
                await download_file(job, e["url"], part, expected_sha512=e["sha512"], expected_sha1="" if e["sha512"] else e["sha1"],
                                    size_hint=e["size"], start_pct=5 + 90 * i / n, span_pct=90 / n,
                                    label=f"[{i + 1}/{len(entries)}] {e['title']}")
                part.replace(dest)
            finally:
                part.unlink(missing_ok=True)
            if prev.get("filename") and prev["filename"] != e["filename"]:     # eski sürümü (panel kurmuşsa) kaldır
                self._unlink(target, prev["filename"])

    @staticmethod
    def _entry_meta(e: dict) -> dict:
        return {k: e[k] for k in ("slug", "title", "version_id", "version", "filename", "sha512")}

    # ---------- profil modlarını kur / güncelle ----------
    async def _install(self, job: Job, folder: Path, mc: str, loader: str, slugs: list[str]) -> dict:
        job.update(1, "resolve", "Mod sürümleri aranıyor…")
        old = read_mods_info(folder) or {}
        extra = [x for x in old.get("extra", []) if SLUG.match(x)]            # tarayıcıdan eklenenler korunur
        try:
            entries, warnings = await self.resolve(list(dict.fromkeys(slugs + extra)), mc, loader)
        except ModrinthError as e:
            raise JobError(str(e))
        target = folder / target_dir(loader)
        target.mkdir(parents=True, exist_ok=True)
        old_mods = old.get("mods", {})
        await self._fetch(job, target, entries, old_mods)
        keep = {e["filename"] for e in entries}
        for m in old_mods.values():                      # yalnızca panelin eskiden kurduğu, artık gerekmeyen dosyalar
            if m.get("filename") not in keep:
                self._unlink(target, m.get("filename", ""))
        (folder / MANIFEST).write_text(json.dumps({
            "requested": sorted(slugs), "extra": extra, "mc": mc, "loader": loader, "warnings": warnings,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mods": {e["project_id"]: self._entry_meta(e) for e in entries},
        }), encoding="utf-8")
        return {"count": len(entries), "warnings": warnings}

    # ---------- mod tarayıcı: arama ----------
    async def search(self, query: str, mc: str, loader: str, offset: int = 0, limit: int = 20) -> dict:
        cat = LOADER_FILTER.get(loader)
        if not cat:
            raise ModrinthError("Bu yükleyici için mod araması desteklenmiyor.")
        ptype = ["project_type:mod", "project_type:plugin"] if loader == "paper" else ["project_type:mod"]
        facets = [ptype, [f"versions:{mc}"], [f"categories:{loader}"], ["server_side:required", "server_side:optional"]]
        data = await self._get("/search", {"query": query[:100], "facets": json.dumps(facets), "limit": limit, "offset": offset,
                                           "index": "relevance" if query.strip() else "downloads"})
        hits = []
        for h in data.get("hits", []):
            if not SLUG.match(str(h.get("slug", ""))):
                continue
            icon = str(h.get("icon_url") or "")
            ih = urlparse(icon).hostname or ""
            hits.append({
                "project_id": str(h.get("project_id", "")), "slug": h["slug"], "title": str(h.get("title", ""))[:100],
                "description": str(h.get("description", ""))[:300], "downloads": int(h.get("downloads") or 0),
                "server_side": h.get("server_side"), "author": str(h.get("author", ""))[:50],
                "icon": icon if icon.startswith("https://") and (ih == "modrinth.com" or ih.endswith(".modrinth.com")) else "",
            })
        return {"hits": hits, "total": int(data.get("total_hits") or 0)}

    # ---------- mod tarayıcı: tek mod ekle ----------
    def ensure_add_job(self, iid: int, folder: Path, mc: str, loader: str, slug: str) -> Job:
        return self.jobs.start("mods", f"Modrinth: {slug} kuruluyor", f"mods-{iid}",
                               lambda j: self._add(j, folder, mc, loader, slug))

    async def _add(self, job: Job, folder: Path, mc: str, loader: str, slug: str) -> dict:
        job.update(1, "resolve", "Sürüm aranıyor…")
        try:
            entries, warnings = await self.resolve([slug], mc, loader)
        except ModrinthError as e:
            raise JobError(str(e))
        if not entries:
            raise JobError(warnings[0] if warnings else "Uygun sürüm bulunamadı.")
        target = folder / target_dir(loader)
        target.mkdir(parents=True, exist_ok=True)
        info = read_mods_info(folder) or {"requested": [], "extra": [], "mods": {}}
        await self._fetch(job, target, entries, info.get("mods", {}))
        for e in entries:
            info.setdefault("mods", {})[e["project_id"]] = self._entry_meta(e)
        if entries[0]["slug"] not in info.setdefault("extra", []):
            info["extra"].append(entries[0]["slug"])
        info.update(mc=mc, loader=loader, installed_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        (folder / MANIFEST).write_text(json.dumps(info), encoding="utf-8")
        return {"count": len(entries), "warnings": warnings, "title": entries[0]["title"]}

    # ---------- kurulu modlar ----------
    def installed_list(self, folder: Path, loader: str) -> list[dict]:
        target = folder / target_dir(loader)
        info = read_mods_info(folder) or {}
        by_file = {m["filename"]: m for m in info.get("mods", {}).values()}
        extra, req = set(info.get("extra", [])), set(info.get("requested", []))
        out = []
        if target.is_dir():
            for p in sorted(target.iterdir(), key=lambda x: x.name.lower()):
                if not p.is_file() or not FILENAME_ANY.match(p.name):
                    continue
                enabled = not p.name.endswith(".disabled")
                base = p.name if enabled else p.name[:-9]
                m = by_file.get(base)
                source = "elle" if not m else "eklenen" if m["slug"] in extra else "profil" if m["slug"] in req else "bağımlılık"
                out.append({"file": p.name, "enabled": enabled, "title": m["title"] if m else base,
                            "version": m["version"] if m else "", "source": source, "size": p.stat().st_size})
        return out

    @staticmethod
    def _checked(folder: Path, loader: str, filename: str) -> tuple[Path, Path]:
        if not FILENAME_ANY.match(filename):
            raise ModrinthError("Geçersiz dosya adı.")
        target = folder / target_dir(loader)
        p = target / filename
        if p.resolve().parent != target.resolve() or not p.is_file():
            raise ModrinthError("Dosya bulunamadı.")
        return target, p

    def set_enabled(self, folder: Path, loader: str, filename: str, enabled: bool) -> None:
        target, p = self._checked(folder, loader, filename)
        base = filename[:-9] if filename.endswith(".disabled") else filename
        dest = target / (base if enabled else base + ".disabled")
        if dest == p:
            return
        if dest.exists():
            raise ModrinthError("Aynı adlı bir dosya zaten var.")
        p.rename(dest)

    def remove(self, folder: Path, loader: str, filename: str) -> None:
        target, p = self._checked(folder, loader, filename)
        base = filename[:-9] if filename.endswith(".disabled") else filename
        p.unlink()
        info = read_mods_info(folder)
        if info:
            for pid, m in list(info.get("mods", {}).items()):
                if m.get("filename") == base:
                    del info["mods"][pid]
                    info["extra"] = [x for x in info.get("extra", []) if x != m.get("slug")]
            (folder / MANIFEST).write_text(json.dumps(info), encoding="utf-8")
