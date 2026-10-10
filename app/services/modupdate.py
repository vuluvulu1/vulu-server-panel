"""Mod güncelleme denetleyicisi.

mods/ (Paper'da plugins/) klasöründeki her jar'ın SHA-512'si hesaplanır ve Modrinth'e sorulur:
  POST /version_files          → dosyanın şu anki sürümü (Modrinth'te yoksa listede çıkmaz)
  POST /version_files/update   → bu Minecraft sürümü + yükleyici için en yeni sürüm
Böylece panelin kurduğu, modpack'ten gelen ve elle eklenen (Modrinth'te bulunan) modların hepsi denetlenir.

Güncelleme: istemci yalnızca dosya adlarını gönderir; sürüm/adres/hash sunucu tarafında yeniden alınır.
Yeni dosya yalnızca Modrinth CDN'inden, SHA-512 doğrulanarak indirilir. Eski dosya silinmez,
.vulu-old-mods/<tarih>/ klasörüne taşınır (son 3 taşıma saklanır). Kapalı (.disabled) mod kapalı kalır.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from .download import download_file
from .jobs import Job, JobError
from .modrinth import FILENAME, FILENAME_ANY, LOADER_FILTER, MANIFEST, ModManager, ModrinthError, read_mods_info, target_dir
from ..i18n import _t

OLD_DIR = ".vulu-old-mods"
KEEP_OLD = 3
CHUNK = 100
MAX_FILES = 1000


def _sha512(p: Path) -> str:
    h = hashlib.sha512()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class ModUpdater:
    def __init__(self, mods: ModManager) -> None:
        self.mods = mods
        self._hash_cache: dict[tuple[str, int, int], str] = {}

    def _jars(self, folder: Path, loader: str) -> list[Path]:
        d = folder / target_dir(loader)
        if not d.is_dir():
            return []
        return [p for p in sorted(d.iterdir(), key=lambda x: x.name.lower())
                if p.is_file() and FILENAME_ANY.match(p.name)][:MAX_FILES]

    def _hashes(self, jars: list[Path]) -> dict[str, Path]:
        out = {}
        for p in jars:
            st = p.stat()
            key = (str(p), st.st_size, st.st_mtime_ns)
            h = self._hash_cache.get(key) or _sha512(p)
            self._hash_cache[key] = h
            out[h] = p
        return out

    async def _lookup(self, hashes: list[str], mc: str, loader: str) -> tuple[dict, dict]:
        cur, new = {}, {}
        loaders = LOADER_FILTER[loader]
        for i in range(0, len(hashes), CHUNK):
            part = hashes[i:i + CHUNK]
            c = await self.mods._post("/version_files", {"hashes": part, "algorithm": "sha512"})
            n = await self.mods._post("/version_files/update", {"hashes": part, "algorithm": "sha512",
                                                                "loaders": loaders, "game_versions": [mc]})
            cur.update(c if isinstance(c, dict) else {})
            new.update(n if isinstance(n, dict) else {})
        return cur, new

    @staticmethod
    def _primary(v: dict) -> dict | None:
        files = v.get("files") or []
        return next((f for f in files if f.get("primary")), files[0] if files else None)

    async def check(self, inst: dict, only: set[str] | None = None) -> dict:
        loader, mc = inst.get("loader") or "", inst.get("mc_version") or ""
        if loader not in LOADER_FILTER or not mc:
            raise ModrinthError(_t("Güncelleme denetimi için Minecraft sürümü ve Fabric/Forge/NeoForge/Paper gerekli."))
        folder = Path(inst["path"])
        jars = self._jars(folder, loader)
        if only is not None:
            jars = [p for p in jars if p.name in only]
        by_hash = await asyncio.to_thread(self._hashes, jars)
        if not by_hash:
            return {"items": [], "checked": 0, "unknown": 0}
        cur, new = await self._lookup(list(by_hash), mc, loader)
        pids = list({v.get("project_id") for v in cur.values() if isinstance(v, dict) and v.get("project_id")})
        titles = {}
        for i in range(0, len(pids), CHUNK):
            try:
                for p in await self.mods._get("/projects", {"ids": json.dumps(pids[i:i + CHUNK])}):
                    titles[p.get("id")] = str(p.get("title") or "")[:100]
            except ModrinthError:
                pass
        items = []
        for h, path in by_hash.items():
            c, n = cur.get(h), new.get(h)
            if not isinstance(c, dict) or not isinstance(n, dict) or n.get("id") == c.get("id"):
                continue
            f = self._primary(n)
            if not f or (f.get("hashes") or {}).get("sha512") == h:
                continue
            items.append({"file": path.name, "title": titles.get(c.get("project_id")) or path.name,
                          "project_id": c.get("project_id"), "current": str(c.get("version_number") or "")[:60],
                          "new": str(n.get("version_number") or "")[:60], "new_type": n.get("version_type") or "release",
                          "new_id": n.get("id"), "new_file": f.get("filename"), "url": f.get("url"),
                          "sha512": (f.get("hashes") or {}).get("sha512", ""), "size": int(f.get("size") or 0)})
        items.sort(key=lambda x: x["title"].lower())
        return {"items": items, "checked": len(by_hash), "unknown": len(by_hash) - len(cur)}

    # ---------- uygula ----------
    def ensure_apply_job(self, inst: dict, files: list[str]) -> Job:
        return self.mods.jobs.start("mods", _t("Modlar güncelleniyor"), f"mods-{inst['id']}", lambda j: self._apply(j, inst, files))

    async def _apply(self, job: Job, inst: dict, files: list[str]) -> dict:
        job.update(1, "resolve", _t("Güncellemeler denetleniyor…"))
        try:
            res = await self.check(inst, set(files))
        except ModrinthError as e:
            raise JobError(str(e))
        todo = res["items"]
        if not todo:
            return {"count": 0, "message": _t("Güncellenecek mod bulunamadı (zaten güncel olabilir).")}
        folder = Path(inst["path"])
        target = folder / target_dir(inst["loader"])
        stamp = time.strftime("%Y%m%d-%H%M%S")
        old_dir = folder / OLD_DIR / stamp
        info = read_mods_info(folder)
        done, n = [], len(todo)
        for i, it in enumerate(todo):
            if not FILENAME.match(it["new_file"] or ""):
                raise JobError(_t('{title}: geçersiz dosya adı.', title=it['title']))
            u = urlparse(it["url"] or "")
            if u.scheme not in ("https", "http") or (u.hostname or "") not in self.mods.cdn or not it["sha512"]:
                raise JobError(f"{it['title']}: beklenmeyen indirme adresi reddedildi.")
            old = target / it["file"]
            disabled = old.name.endswith(".disabled")
            new_name = it["new_file"] + (".disabled" if disabled else "")
            part = target / (it["new_file"] + ".vulu-part")
            try:
                await download_file(job, it["url"], part, expected_sha512=it["sha512"], size_hint=it["size"],
                                    start_pct=5 + 90 * i / n, span_pct=90 / n, label=f"[{i + 1}/{n}] {it['title']}")
                old_dir.mkdir(parents=True, exist_ok=True)
                if old.is_file():
                    shutil.move(str(old), str(old_dir / old.name))
                part.replace(target / new_name)
            finally:
                part.unlink(missing_ok=True)
            done.append(it)
            if info:                                         # panelin kaydını da güncelle
                base = it["file"][:-9] if disabled else it["file"]
                for m in info.get("mods", {}).values():
                    if m.get("filename") == base:
                        m.update(filename=it["new_file"], version=it["new"], version_id=it["new_id"], sha512=it["sha512"])
        if info:
            (folder / MANIFEST).write_text(json.dumps(info), encoding="utf-8")
        olds = sorted((p for p in (folder / OLD_DIR).iterdir() if p.is_dir()), key=lambda p: p.name) if (folder / OLD_DIR).is_dir() else []
        for p in olds[:-KEEP_OLD]:
            shutil.rmtree(p, ignore_errors=True)
        job.update(99, "done", _t("Tamamlandı"))
        return {"count": len(done), "old_dir": f"{OLD_DIR}/{stamp}",
                "message": _t('{n} mod güncellendi. Eski dosyalar {OLD_DIR}/{stamp} klasöründe.', n=len(done), OLD_DIR=OLD_DIR, stamp=stamp)}
