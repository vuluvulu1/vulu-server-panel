"""Sunucu simgesi (server-icon.png): doğrulama, yazma ve varsayılan vulu simgesi."""
from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from ..config import BASE_DIR

ICON_NAME = "server-icon.png"
ICON_MAX = 256 * 1024
PNG_SIG = b"\x89PNG\r\n\x1a\n"
DEFAULT_ICON = BASE_DIR / "app" / "static" / "img" / "default-icon.png"


def valid_icon(data: bytes) -> bool:
    """Gerçek bir 64x64 PNG mi? (imza + IHDR boyutları + IEND)"""
    return (len(data) <= ICON_MAX and data[:8] == PNG_SIG and data[12:16] == b"IHDR"
            and int.from_bytes(data[16:20], "big") == 64 and int.from_bytes(data[20:24], "big") == 64
            and data.rstrip(b"\x00")[-8:-4] == b"IEND")


def decode_icon(b64: str) -> bytes | None:
    """Tarayıcıdan gelen base64 PNG → bayt; geçersizse None."""
    if not b64 or len(b64) > ICON_MAX * 2:
        return None
    if b64.startswith("data:image/png;base64,"):
        b64 = b64.split(",", 1)[1]
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if valid_icon(raw) else None


def write_icon(folder: Path, data: bytes) -> None:
    tmp = folder / (ICON_NAME + ".vulu-tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, folder / ICON_NAME)
    finally:
        tmp.unlink(missing_ok=True)


def default_icon() -> bytes | None:
    try:
        data = DEFAULT_ICON.read_bytes()
    except OSError:
        return None
    return data if valid_icon(data) else None
