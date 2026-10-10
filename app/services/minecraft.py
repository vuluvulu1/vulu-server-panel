"""Minecraft sürüm listesi ve gereken Java sürümünün tespiti.

Birincil kaynak Mojang'ın kendi verisi: her sürümün JSON'unda `javaVersion.majorVersion`
yazar (1.17+). Bu alan olmayan eski sürümler Java 8 ile çalışır.
Mojang'a ulaşılamazsa bilinen sürümler için yerleşik tabloya düşülür.
"""
import json
import re
import time
from pathlib import Path

import httpx

from .http import new_client
from ..i18n import _t


class McError(Exception):
    pass


LOADERS = ("vanilla", "paper", "fabric", "forge", "neoforge")


def _parse_release(v: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", v)
    return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


def fallback_java(v: str) -> int | None:
    """Mojang'a ulaşılamazken kullanılan, yayınlanmış sürümler için tahmin tablosu."""
    t = _parse_release(v)
    if not t:
        return None
    major, minor, patch = t
    if major >= 26:            # yıl bazlı sürümleme (26.1 = Java 25)
        return 25
    if major != 1:
        return None
    if minor <= 16:
        return 8
    if minor <= 19:
        return 17
    if minor == 20:
        return 17 if patch <= 4 else 21
    return 21                  # 1.21+


class MinecraftService:
    def __init__(self, manifest_url: str, data_dir: Path) -> None:
        self.manifest_url = manifest_url
        self.data_dir = data_dir
        self._manifest: dict | None = None
        self._manifest_at = 0.0
        self._java_cache: dict[str, int] = {}
        self._java_cache_loaded = False

    # ---------- disk önbelleği ----------
    def _read_json(self, name: str):
        try:
            return json.loads((self.data_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_json(self, name: str, data) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.data_dir / (name + ".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.data_dir / name)
        except OSError:
            pass  # önbellek yazılamıyorsa sorun değil

    # ---------- manifest ----------
    async def manifest(self) -> dict:
        if self._manifest and time.monotonic() - self._manifest_at < 1800:
            return self._manifest
        try:
            async with new_client() as c:
                r = await c.get(self.manifest_url)
                r.raise_for_status()
                data = r.json()
            self._manifest, self._manifest_at = data, time.monotonic()
            self._write_json("mc_manifest.json", data)
            return data
        except (httpx.HTTPError, ValueError):
            stale = self._manifest or self._read_json("mc_manifest.json")
            if stale:
                return stale
            raise McError(_t("Mojang sürüm listesine ulaşılamadı. İnternet bağlantını kontrol et."))

    async def list_versions(self, snapshots: bool = False) -> dict:
        m = await self.manifest()
        allowed = {"release", "snapshot"} if snapshots else {"release"}
        versions = [
            {"id": v["id"], "type": v["type"], "released": v.get("releaseTime", "")[:10]}
            for v in m.get("versions", []) if v.get("type") in allowed
        ]
        return {"latest": m.get("latest", {}).get("release"), "versions": versions}

    # ---------- Java gereksinimi ----------
    async def required_java(self, v: str) -> tuple[int, str]:
        """(Mojang'ın istediği ham major, kaynak) döndürür. kaynak: cache | mojang | fallback"""
        if not self._java_cache_loaded:
            self._java_cache = self._read_json("mc_java.json") or {}
            self._java_cache_loaded = True
        if v in self._java_cache:
            return self._java_cache[v], "cache"

        entry = None
        try:
            entry = next((x for x in (await self.manifest()).get("versions", []) if x["id"] == v), None)
        except McError:
            pass

        if entry:
            try:
                async with new_client() as c:
                    r = await c.get(entry["url"])
                    r.raise_for_status()
                    raw = (r.json().get("javaVersion") or {}).get("majorVersion") or 8
                self._java_cache[v] = int(raw)
                self._write_json("mc_java.json", self._java_cache)
                return int(raw), "mojang"
            except (httpx.HTTPError, ValueError):
                pass  # aşağıda tahmine düş

        fb = fallback_java(v)
        if fb is None:
            raise McError(_t("'{v}' sürümü için Java gereksinimi belirlenemedi. Java'yı elle seçebilirsin.", v=v))
        return fb, "fallback"

    async def java_for(self, mc_version: str, loader: str = "vanilla") -> dict:
        """Seçilen Minecraft sürümü (+ mod yükleyici) için kullanılacak Java major'ı.

        Kural: Mojang'ın istediği sürümün birebir aynısı (daha yenisi değil). Forge/NeoForge gibi
        yükleyiciler eski sürümlerde yeni Java'da sorun çıkarabildiği için "yükseltme" yapmıyoruz.
        Java 16 (1.17) artık yayınlanmadığından 17 kullanılır.
        """
        if loader not in LOADERS:
            raise McError(_t("Bilinmeyen mod yükleyici."))
        raw, source = await self.required_java(mc_version)
        major = 17 if raw == 16 else raw
        reason = f"Minecraft {mc_version} → Java {major}"
        if raw == 16:
            reason += _t(" (Mojang 16 istiyor; 16 artık yayınlanmadığı için 17 kullanılır)")
        if source == "fallback":
            reason += _t(" (tahmini: Mojang'a ulaşılamadı)")
        return {"major": major, "reason": reason, "source": source, "loader": loader}
