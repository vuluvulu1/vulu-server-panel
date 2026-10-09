"""Sunucu profilleri: profiles/*.json dosyalarındaki hazır ayar şablonları (yalnızca veri, kod çalıştırmaz).

Bir profil; Minecraft sürümü ("latest" = en yeni), mod yükleyici, JVM ayarı, varsayılan RAM ve
server.properties değerlerini taşır. Profil seçilince "Yeni sunucu" formu bu değerlerle dolar.
(Mod listesi / mod paketi kaynakları sonraki adımda gelecek.)
"""
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import BASE_DIR
from .jvm import PRESETS
from .minecraft import LOADERS
from .modrinth import SLUG

PROFILES_DIR = BASE_DIR / "profiles"
# Bu anahtarları panel kendisi yönetir (her başlatmada yazar); profil ezemez
FORBIDDEN_PROPS = {"server-port", "enable-rcon", "rcon.port", "rcon.password", "server-ip", "query.port"}
_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}$")
_VAL = re.compile(r"^[^\x00-\x1f\\]{0,200}$")      # satır sonu / kaçış karakteri yok → özellik enjeksiyonu olmaz


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,40}$")
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    mc_version: str = Field(default="latest", pattern=r"^(latest|[0-9A-Za-z._+-]{1,40})$")
    loader: str
    jvm_preset: str = "aikar"
    default_ram_gb: int = Field(default=4, ge=1, le=64)
    server_properties: dict[str, str | int | bool] = Field(default_factory=dict)
    mods: list[str] = Field(default_factory=list, max_length=100)     # Modrinth proje adresleri (slug)

    @field_validator("loader", mode="before")
    @classmethod
    def _loader(cls, v):
        v = v.get("type") if isinstance(v, dict) else v          # {"type": "forge"} biçimini de kabul et
        if v not in LOADERS:
            raise ValueError(f"loader şunlardan biri olmalı: {', '.join(LOADERS)}")
        return v

    @field_validator("jvm_preset")
    @classmethod
    def _preset(cls, v):
        if v not in PRESETS:
            raise ValueError(f"jvm_preset şunlardan biri olmalı: {', '.join(PRESETS)}")
        return v

    @field_validator("mods")
    @classmethod
    def _mods(cls, v):
        for s in v:
            if not SLUG.match(s):
                raise ValueError(f"mod adı geçersiz: {s!r}")
        return list(dict.fromkeys(v))                   # tekrarları at

    @field_validator("server_properties")
    @classmethod
    def _props(cls, d):
        for k, v in d.items():
            if not _KEY.match(k) or k in FORBIDDEN_PROPS:
                raise ValueError(f"server_properties anahtarı kabul edilmedi: {k}")
            if not _VAL.match(_as_str(v)):
                raise ValueError(f"server_properties değeri kabul edilmedi: {k}")
        return d


def _as_str(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def props_as_strings(p: Profile) -> dict[str, str]:
    return {k: _as_str(v) for k, v in p.server_properties.items()}


def load_profiles() -> tuple[list[Profile], list[str]]:
    """(geçerli profiller, hata mesajları). Bozuk bir dosya diğerlerini engellemez."""
    profiles, errors, seen = [], [], set()
    for f in sorted(PROFILES_DIR.glob("*.json")):
        try:
            p = Profile.model_validate(json.loads(f.read_text(encoding="utf-8")))
            if p.id in seen:
                raise ValueError(f"id tekrar ediyor: {p.id}")
            seen.add(p.id)
            profiles.append(p)
        except (OSError, ValueError) as e:
            errors.append(f"{f.name}: {' '.join(str(e).split())[:220]}")
    return profiles, errors


def get_profile(profile_id: str | None) -> Profile | None:
    return next((p for p in load_profiles()[0] if p.id == profile_id), None) if profile_id else None
