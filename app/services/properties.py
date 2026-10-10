"""server.properties düzenleme ve her başlatmada port + RCON ayarlarının panelden uygulanması."""
import os
import re
import secrets
import socket
from pathlib import Path

from ..db import update_instance, used_ports
from ..i18n import _t

_SAFE_VALUE = re.compile(r"^[^\x00-\x1f\\]{0,200}$")   # satır sonu / kaçış karakteri yok → enjeksiyon olmaz


def encode_value(v: str) -> str:
    """ASCII dışı karakterleri \\uXXXX olarak yazar (Properties biçimi; kodlama sorunu çıkmaz)."""
    return "".join(c if ord(c) < 128 else f"\\u{ord(c):04x}" for c in v)


def decode_value(v: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), v)


def read_properties(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    out = {}
    for ln in lines:
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1)
            out[k.strip()] = decode_value(v)
    return out


def update_properties(path: Path, updates: dict[str, str]) -> None:
    for k, v in updates.items():
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", k) or not _SAFE_VALUE.match(str(v)):
            raise ValueError(_t('güvensiz özellik: {k}', k=k))
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, seen = [], set()
    for ln in lines:
        key = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if key in updates:
            out.append(f"{key}={encode_value(str(updates[key]))}")
            seen.add(key)
        else:
            out.append(ln)
    out += [f"{k}={encode_value(str(v))}" for k, v in updates.items() if k not in seen]
    tmp = path.with_name(path.name + ".part")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _free_port(avoid: set[int]) -> int:
    for _ in range(300):
        p = 30000 + secrets.randbelow(10000)
        if p in avoid:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise OSError(_t("RCON için boş port bulunamadı"))


def prepare_runtime(inst: dict) -> dict:
    """Instance'a rastgele RCON portu/şifresi atar (yoksa) ve port + RCON'u server.properties'e yazar."""
    rport, rpw = inst.get("rcon_port"), inst.get("rcon_password")
    if not rport or not rpw:
        rport = _free_port(used_ports() | {int(inst["port"])})
        rpw = secrets.token_urlsafe(24)
        update_instance(inst["id"], rcon_port=rport, rcon_password=rpw)
        inst = {**inst, "rcon_port": rport, "rcon_password": rpw}
    update_properties(Path(inst["path"]) / "server.properties", {
        "server-port": str(int(inst["port"])), "enable-rcon": "true",
        "rcon.port": str(int(rport)), "rcon.password": rpw,
    })
    return inst
