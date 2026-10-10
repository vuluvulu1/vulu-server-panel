"""Oyuncu yönetimi: beyaz liste, OP ve yasaklar.

- Sunucu çalışıyorsa işlemler RCON komutuyla yapılır (sunucu UUID'yi kendisi bulur, değişiklik anında geçerli olur).
- Sunucu kapalıysa whitelist.json / ops.json / banned-players.json doğrudan düzenlenir. UUID,
  online-mode=true ise Mojang'dan, kapalıysa Minecraft'ın çevrimdışı kuralıyla (OfflinePlayer:<ad>) hesaplanır.

Güvenlik: oyuncu adı katı bir düzenle doğrulanır (komut enjeksiyonu olmaz), yasak nedeni tek satır ve kısa
tutulur; dosyalar boyut sınırıyla okunur ve atomik yazılır. Mojang'a yalnızca sabit adres üzerinden gidilir.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from .http import new_client
from .properties import read_properties, update_properties
from .rcon import RconClient, RconError
from ..i18n import _t

NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
REASON_RE = re.compile(r"[^\x20-\x7e -￿]")       # kontrol karakterlerini at
FILE_MAX = 2 * 1024 * 1024
LIST_MAX = 5000

FILES = {"whitelist": "whitelist.json", "ops": "ops.json", "bans": "banned-players.json"}
ACTIONS = {"whitelist_add", "whitelist_remove", "op", "deop", "ban", "pardon", "kick", "whitelist_on", "whitelist_off"}


class PlayerError(Exception):
    pass


def offline_uuid(name: str) -> str:
    """Java'nın UUID.nameUUIDFromBytes("OfflinePlayer:" + ad) eşdeğeri (sürüm 3)."""
    h = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(h)))


def _dashed(u: str) -> str:
    return str(uuid.UUID(u.replace("-", "")))


def _read_list(path: Path) -> list[dict]:
    try:
        if not path.is_file() or path.stat().st_size > FILE_MAX:
            return []
        data = json.loads(path.read_text(encoding="utf-8-sig") or "[]")
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict)][:LIST_MAX] if isinstance(data, list) else []


def _write_list(path: Path, items: list[dict]) -> None:
    tmp = path.with_name(path.name + ".vulu-tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _clean_entry(e: dict, kind: str) -> dict:
    out = {"name": str(e.get("name", ""))[:32], "uuid": str(e.get("uuid", ""))[:40]}
    if kind == "ops":
        out["level"] = e.get("level") if isinstance(e.get("level"), int) else 4
    if kind == "bans":
        out["reason"] = str(e.get("reason", ""))[:200]
        out["created"] = str(e.get("created", ""))[:40]
        out["expires"] = str(e.get("expires", ""))[:40]
    return out


class PlayerManager:
    def __init__(self, pm, stats, profile_api: str) -> None:
        self.pm, self.stats, self.profile_api = pm, stats, profile_api.rstrip("/") + "/"
        self._locks: dict[int, asyncio.Lock] = {}

    # ---------- okuma ----------
    def overview(self, inst: dict) -> dict:
        folder = Path(inst["path"])
        props = read_properties(folder / "server.properties") if (folder / "server.properties").is_file() else {}
        lists = {k: [_clean_entry(e, k) for e in _read_list(folder / f)] for k, f in FILES.items()}
        snap = self.stats.snapshot(inst["id"], inst["ram_mb"]) if self.stats else {}
        return {**lists,
                "online": [n for n in (snap.get("player_names") or []) if isinstance(n, str) and NAME_RE.match(n)],
                "whitelist_enabled": props.get("white-list", "false") == "true",
                "enforce_whitelist": props.get("enforce-whitelist", "false") == "true",
                "online_mode": props.get("online-mode", "true") != "false",
                "status": self.pm.status(inst["id"])}

    # ---------- işlem ----------
    async def action(self, inst: dict, action: str, name: str = "", reason: str = "") -> str:
        if action not in ACTIONS:
            raise PlayerError(_t("Geçersiz işlem."))
        if action not in ("whitelist_on", "whitelist_off") and not NAME_RE.match(name or ""):
            raise PlayerError(_t("Oyuncu adı 1-16 karakter olmalı; yalnızca harf, rakam ve alt çizgi."))
        reason = REASON_RE.sub("", (reason or "").replace("\n", " ").strip())[:100]
        iid = inst["id"]
        lock = self._locks.setdefault(iid, asyncio.Lock())
        async with lock:
            status = self.pm.status(iid)
            if status == "running":
                return await self._rcon(inst, action, name, reason)
            if status in ("starting", "stopping", "preparing"):
                raise PlayerError(_t("Sunucu açılıyor ya da kapanıyor; birkaç saniye sonra tekrar dene."))
            if action == "kick":
                raise PlayerError(_t("Atmak için sunucunun çalışıyor olması gerekir."))
            return await self._offline(inst, action, name, reason)

    async def _rcon(self, inst: dict, action: str, name: str, reason: str) -> str:
        cmd = {"whitelist_add": f"whitelist add {name}", "whitelist_remove": f"whitelist remove {name}",
               "op": f"op {name}", "deop": f"deop {name}", "pardon": f"pardon {name}",
               "ban": f"ban {name} {reason}".rstrip(), "kick": f"kick {name} {reason}".rstrip(),
               "whitelist_on": "whitelist on", "whitelist_off": "whitelist off"}[action]
        if not inst.get("rcon_port") or not inst.get("rcon_password"):
            raise PlayerError(_t("RCON hazır değil; sunucuyu panelden yeniden başlat."))
        cli = RconClient("127.0.0.1", int(inst["rcon_port"]), inst["rcon_password"])
        try:
            await cli.connect()
            out = await cli.command(cmd)
        except RconError as e:
            raise PlayerError(str(e))
        finally:
            await cli.close()
        if action in ("whitelist_on", "whitelist_off"):          # server.properties'i de eşitle (yeniden başlatmada kalsın)
            try:
                update_properties(Path(inst["path"]) / "server.properties", {"white-list": "true" if action == "whitelist_on" else "false"})
            except (OSError, ValueError):
                pass
        await asyncio.sleep(0.3)                                  # sunucu json dosyasını yazsın
        out = re.sub(r"§.", "", out or "").strip()
        return out[:300] or _t("Komut gönderildi.")

    async def _uuid(self, inst: dict, name: str) -> tuple[str, str]:
        folder = Path(inst["path"])
        props = read_properties(folder / "server.properties") if (folder / "server.properties").is_file() else {}
        if props.get("online-mode", "true") == "false":
            return offline_uuid(name), name
        try:
            async with new_client() as c:
                r = await c.get(self.profile_api + name, timeout=10)
        except Exception:
            raise PlayerError(_t("Mojang'a ulaşılamadı; oyuncunun UUID'si bulunamadı. İnternet bağlantını kontrol et ya da sunucu açıkken dene."))
        if r.status_code in (204, 404):
            raise PlayerError(_t("'{name}' adında bir Minecraft hesabı bulunamadı.", name=name))
        if r.status_code != 200:
            raise PlayerError(_t('Mojang yanıt vermedi (HTTP {status_code}). Biraz sonra tekrar dene.', status_code=r.status_code))
        try:
            j = r.json()
            uid, real = str(j["id"]), str(j.get("name") or name)
        except (ValueError, KeyError, TypeError):
            raise PlayerError(_t("Mojang'dan beklenmeyen yanıt geldi."))
        if not UUID_RE.match(uid) or not NAME_RE.match(real):
            raise PlayerError(_t("Mojang'dan geçersiz yanıt geldi."))
        return _dashed(uid), real

    async def _offline(self, inst: dict, action: str, name: str, reason: str) -> str:
        folder = Path(inst["path"])
        if action in ("whitelist_on", "whitelist_off"):
            on = action == "whitelist_on"
            try:
                update_properties(folder / "server.properties", {"white-list": "true" if on else "false"})
            except (OSError, ValueError) as e:
                raise PlayerError(_t('server.properties yazılamadı: {e}', e=e))
            return _t("Beyaz liste açıldı.") if on else _t("Beyaz liste kapatıldı.")

        kind = {"whitelist_add": "whitelist", "whitelist_remove": "whitelist", "op": "ops", "deop": "ops",
                "ban": "bans", "pardon": "bans"}[action]
        path = folder / FILES[kind]
        items = _read_list(path)
        low = name.lower()
        existing = [e for e in items if str(e.get("name", "")).lower() == low]

        if action in ("whitelist_remove", "deop", "pardon"):
            if not existing:
                return _t('{name} listede yok.', name=name)
            items = [e for e in items if str(e.get("name", "")).lower() != low]
            msg = {"whitelist_remove": _t('{name} beyaz listeden çıkarıldı.', name=name), "deop": _t('{name} artık OP değil.', name=name),
                   "pardon": _t('{name} yasağı kaldırıldı.', name=name)}[action]
        else:
            if existing:
                return {"whitelist_add": _t('{name} zaten beyaz listede.', name=name), "op": _t('{name} zaten OP.', name=name), "ban": _t('{name} zaten yasaklı.', name=name)}[action]
            uid, real = await self._uuid(inst, name)
            items = [e for e in items if str(e.get("uuid", "")).lower() != uid]
            if action == "whitelist_add":
                items.append({"uuid": uid, "name": real})
                msg = _t('{real} beyaz listeye eklendi.', real=real)
            elif action == "op":
                items.append({"uuid": uid, "name": real, "level": 4, "bypassesPlayerLimit": False})
                msg = _t('{real} OP yapıldı.', real=real)
            else:
                items.append({"uuid": uid, "name": real, "created": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
                              "source": "vulu panel", "expires": "forever", "reason": reason or "Banned by an operator."})
                msg = _t('{real} yasaklandı.', real=real)
        if self.pm.status(inst["id"]) not in ("stopped", "crashed"):
            raise PlayerError(_t("Sunucu bu arada başlatıldı; işlemi tekrar dene."))
        try:
            _write_list(path, items)
        except OSError as e:
            raise PlayerError(_t('{v0} yazılamadı: {e}', v0=FILES[kind], e=e))
        return msg
