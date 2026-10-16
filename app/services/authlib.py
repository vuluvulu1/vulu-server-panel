"""authlib-injector: sunucunun oyuncu doğrulamasını ve skin isteklerini Mojang yerine vulu-api'ye yönlendiren
Java ajanı. "vulu Launcher'a özel" açık sunucular bununla başlatılır.

Ajan panelle birlikte dağıtılmaz; resmi adresinden indirilir, SHA-256'sı doğrulanır ve runtimes/ altında
saklanır. İnternet yoksa daha önce indirilip doğrulanmış sürüm kullanılır."""
import asyncio
import base64
import hashlib
import json
import re
from pathlib import Path

from ..config import AUTHLIB_LATEST_URL, RUNTIMES_DIR, VULU_API
from ..i18n import _t
from .http import new_client

FOLDER = RUNTIMES_DIR / "authlib-injector"
_VERSION_RE = re.compile(r"^[0-9A-Za-z.\-]{1,40}$")
_lock = asyncio.Lock()


class AuthlibError(Exception):
    """Kullanıcıya gösterilebilir hata."""


def api_root() -> str:
    return f"{VULU_API}/yggdrasil"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cached() -> Path | None:
    jars = sorted(FOLDER.glob("authlib-injector-*.jar"), key=lambda p: p.stat().st_mtime, reverse=True) if FOLDER.is_dir() else []
    return jars[0] if jars else None


async def ensure_jar(log) -> Path:
    """Kullanılabilir ajan dosyasının yolu; indirilemez ve önbellekte de yoksa AuthlibError."""
    async with _lock:
        latest = None
        try:
            async with new_client() as c:
                r = await c.get(AUTHLIB_LATEST_URL, timeout=10)
                r.raise_for_status()
                latest = r.json()
        except Exception:
            pass                                             # çevrimdışı: önbellektekiyle devam

        try:
            version, url, sha = str(latest["version"]), str(latest["download_url"]), str(latest["checksums"]["sha256"]).lower()
        except (TypeError, KeyError):
            version = url = sha = ""
        if _VERSION_RE.match(version) and url.startswith("https://") and re.fullmatch(r"[0-9a-f]{64}", sha):
            path = FOLDER / f"authlib-injector-{version}.jar"
            if path.is_file() and await asyncio.to_thread(_sha256, path) == sha:
                return path
            tmp = path.with_name(path.name + ".part")
            try:
                log(_t("[panel] authlib-injector {version} indiriliyor…", version=version))
                FOLDER.mkdir(parents=True, exist_ok=True)
                async with new_client() as c:
                    r = await c.get(url, timeout=60)
                    r.raise_for_status()
                    tmp.write_bytes(r.content)
                if await asyncio.to_thread(_sha256, tmp) != sha:
                    raise AuthlibError(_t("authlib-injector doğrulanamadı (sağlama toplamı uyuşmuyor)."))
                tmp.replace(path)
                for old in FOLDER.glob("authlib-injector-*.jar"):
                    if old != path:
                        old.unlink(missing_ok=True)
                return path
            except Exception as e:
                log(_t("[panel] authlib-injector indirilemedi: {e}", e=e))
            finally:
                tmp.unlink(missing_ok=True)

        if jar := _cached():
            return jar
        raise AuthlibError(_t("authlib-injector indirilemedi ve daha önce indirilmiş bir kopyası yok. İnternet bağlantını kontrol et."))


async def prefetched_metadata() -> str | None:
    """vulu-api'nin kök bilgisi (base64). Sunucu açılırken ajan tekrar sormasın diye önceden verilir.
    Ücretsiz sunucu uykudan uyanırken bir dakika kadar sürebilir; alınamazsa None (ajan kendisi sorar)."""
    try:
        async with new_client() as c:
            r = await c.get(api_root() + "/", timeout=75)
            r.raise_for_status()
            data = r.json()
        if "signaturePublickey" not in data:
            return None
        return base64.b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()
    except Exception:
        return None


async def agent_flags(log) -> list[str]:
    jar = await ensure_jar(log)
    flags = [f"-javaagent:{jar.resolve()}={api_root()}"]
    if meta := await prefetched_metadata():
        flags.append(f"-Dauthlibinjector.yggdrasil.prefetched={meta}")
    else:
        log(_t("[panel] Uyarı: vulu hesap sunucusuna şu an ulaşılamadı; oyuncular bağlanırken tekrar denenecek."))
    return flags
