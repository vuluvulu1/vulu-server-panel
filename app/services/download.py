"""Yüzdeli, SHA-256 doğrulamalı dosya indirme (Java ve Paper ortak kullanır)."""
import hashlib
import time
from pathlib import Path

import httpx

from .http import new_client
from .jobs import Job, JobError
from ..i18n import _t


def mb(n: float) -> str:
    return f"{n / 1_048_576:.1f}"


async def download_file(
    job: Job, url: str, dest: Path, *, expected_sha256: str = "", expected_sha1: str = "", expected_sha512: str = "", size_hint: int = 0,
    start_pct: float = 0.0, span_pct: float = 100.0, label: str | None = None,
) -> str:
    """url'yi dest'e indirir; ilerlemeyi job'a start_pct..start_pct+span_pct aralığında yazar."""
    label = label or _t("İndiriliyor")
    sha = hashlib.sha256()
    sha1 = hashlib.sha1()
    sha512 = hashlib.sha512()
    done = 0
    started = time.monotonic()
    try:
        async with new_client() as c:
            async with c.stream("GET", url) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0) or size_hint
                with open(dest, "wb") as f:
                    async for chunk in r.aiter_bytes(65536):
                        f.write(chunk)
                        sha.update(chunk)
                        sha1.update(chunk)
                        sha512.update(chunk)
                        done += len(chunk)
                        speed = done / max(time.monotonic() - started, 0.001)
                        frac = min(done / total, 1.0) if total else 0.0
                        msg = (_t("{label} — {done} / {total} MB ({speed} MB/sn)", label=label, done=mb(done), total=mb(total), speed=mb(speed)) if total
                               else f"{label} — {mb(done)} MB")
                        job.update(start_pct + span_pct * frac, "download", msg)
    except httpx.HTTPError as e:
        raise JobError(_t('İndirme başarısız: {name__}. İnternet bağlantını kontrol et.', name__=e.__class__.__name__))

    job.update(start_pct + span_pct, "verify", _t("Doğrulanıyor…"))
    digest = sha.hexdigest()
    if expected_sha512 and sha512.hexdigest() != expected_sha512.lower():
        raise JobError(_t("İndirilen dosya doğrulanamadı (sağlama toplamı uyuşmuyor). Tekrar dene."))
    if expected_sha1 and sha1.hexdigest() != expected_sha1.lower():
        raise JobError(_t("İndirilen dosya doğrulanamadı (sağlama toplamı uyuşmuyor). Tekrar dene."))
    if expected_sha256 and digest != expected_sha256.lower():
        raise JobError(_t("İndirilen dosya doğrulanamadı (sağlama toplamı uyuşmuyor). Tekrar dene."))
    return digest
