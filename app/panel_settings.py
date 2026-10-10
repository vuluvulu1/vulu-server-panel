"""Panelin kendi ayarları (adres, port, iletişim bilgisi, izinli alan adları).

data/panel-settings.json içinde tutulur ve .env'deki değerlerin ÜZERİNE yazar; böylece .env'e dokunmadan
panelden değiştirilebilir. Bu modül yalnızca standart kütüphane kullanır (config.py ve run.py da okur).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from .i18n import _t

FILE_NAME = "panel-settings.json"
HOST_MODES = {"local": "127.0.0.1", "lan": "0.0.0.0"}
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CONTACT_RE = re.compile(r"^[\x21-\x7e]{0,120}$")       # tek satır, boşluksuz yazdırılabilir ASCII (HTTP başlığına girer)


def path(data_dir: Path) -> Path:
    return data_dir / FILE_NAME


def load(data_dir: Path) -> dict:
    try:
        d = json.loads(path(data_dir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data_dir: Path, values: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = path(data_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def validate(raw: dict) -> tuple[dict, str | None]:
    """Gelen değerleri doğrular → (temiz değerler, hata)."""
    out = {}
    mode = raw.get("host_mode")
    if mode not in HOST_MODES:
        return {}, _t("Geçersiz ağ erişimi seçimi.")
    out["host"] = HOST_MODES[mode]
    try:
        port = int(raw.get("port"))
    except (TypeError, ValueError):
        return {}, _t("Port bir sayı olmalı.")
    if not 1024 <= port <= 65535:
        return {}, _t("Port 1024-65535 arasında olmalı.")
    out["port"] = port
    contact = str(raw.get("contact") or "").strip()
    if not CONTACT_RE.match(contact):
        return {}, _t("İletişim bilgisi tek satır olmalı, boşluk ve Türkçe karakter içermemeli (e-posta ya da site adresi).")
    out["contact"] = contact
    hosts = []
    for h in str(raw.get("allowed_hosts") or "").replace("\n", ",").split(","):
        h = h.strip().lower()
        if not h:
            continue
        try:
            ipaddress.ip_address(h)
            ok = True
        except ValueError:
            ok = bool(DOMAIN_RE.match(h))
        if not ok:
            return {}, _t('Geçersiz alan adı: {v0}', v0=h[:60])
        hosts.append(h)
    if len(hosts) > 10:
        return {}, _t("En fazla 10 alan adı.")
    out["allowed_hosts"] = hosts
    return out, None


def host_mode(host: str) -> str:
    return "local" if host in ("127.0.0.1", "localhost", "::1") else "lan"
