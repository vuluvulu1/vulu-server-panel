"""Güvenlik katmanı: tarayıcı kaynaklı saldırılara karşı koruma + girdi doğrulayıcıları.

Neden gerekli? Panel yalnızca 127.0.0.1'de dinlese bile, kullanıcının tarayıcısında açık
herhangi bir kötü niyetli web sitesi http://127.0.0.1:8000'e istek atabilir (cross-site POST,
WebSocket, DNS rebinding). Panel bilgisayarda süreç başlatıp dosya yazdığı için bu, uzaktan
kod çalıştırmaya kadar gidebilir. Bu middleware bunların hepsini keser.
"""
import os
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse

from starlette.datastructures import MutableHeaders
from starlette.responses import PlainTextResponse

from .config import ALLOWED_HOSTS_EXTRA

BASE_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",                             # clickjacking: panel iframe içine alınamaz
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _hostname(hostport: str) -> str:
    hostport = hostport.strip().lower()
    return hostport.split("]")[0] + "]" if hostport.startswith("[") else hostport.split(":")[0]


class LocalGuardMiddleware:
    """1) Host başlığı beklenen adreslerden biri olmalı (DNS rebinding'i engeller).
    2) Durum değiştiren istekler (POST/PUT/DELETE...) ve WebSocket'ler başka bir siteden gelemez
       (Origin ve Sec-Fetch-Site kontrolü). Origin göndermeyen tarayıcı dışı istemciler (curl) geçer.
    3) Güvenlik başlıklarını ekler."""

    def __init__(self, app) -> None:
        self.app = app
        self.allowed = BASE_HOSTS | set(ALLOWED_HOSTS_EXTRA)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        h = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = h.get("host", "")
        changes_state = scope["type"] == "websocket" or scope.get("method", "GET") not in SAFE_METHODS

        bad = _hostname(host) not in self.allowed
        if not bad and changes_state:
            origin = h.get("origin")
            if origin is not None and urlparse(origin).netloc.lower() != host.lower():
                bad = True                                  # başka site (ya da "null" origin)
            if h.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
                bad = True
        if bad:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await PlainTextResponse("Yasak", status_code=403)(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    headers[k] = v
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ---------------- girdi doğrulayıcıları ----------------
_JVM_TOKEN = re.compile(r"^-(X|D)[A-Za-z0-9_.:+=,/-]*$")
_JVM_FORBIDDEN = (
    "onerror", "onoutofmemory", "javaagent", "agentlib", "agentpath", "jdwp", "vmoptionsfile",
    "-xx:flags", "-xrun", "-xbootclasspath", "system.class.loader", "library.path", "jdk.attach",
)


def validate_jvm_args(raw: str) -> str | None:
    """Hata mesajı döndürür, geçerliyse None. Yalnızca -X/-D ile başlayan güvenli bayraklara izin verir;
    JVM'in komut çalıştırabilen seçenekleri (-XX:OnError, -javaagent ...) ve kabuk karakterleri yasak."""
    if not raw.strip():
        return None
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return "Ek JVM argümanları okunamadı (tırnak hatası)."
    for t in tokens:
        if not _JVM_TOKEN.match(t):
            return (f"JVM argümanı kabul edilmedi: {t[:40]!r}. Yalnızca -X / -D ile başlayan ve "
                    "harf, rakam ve . : + = , / - karakterleri içeren bayraklara izin var.")
        if any(f in t.lower() for f in _JVM_FORBIDDEN):
            return f"Güvenlik nedeniyle bu JVM argümanına izin verilmiyor: {t[:40]!r}"
    return None


def validate_java_path(p: str) -> str | None:
    """Özel Java yolu: PATH'teki 'java' ya da bir java/java.exe dosyasına tam yol olmalı
    (panelin rastgele bir programı çalıştırmasını engeller)."""
    p = p.strip()
    if p in ("java", "java.exe"):
        return None
    if not p or len(p) > 260:
        return "Java yolu boş olamaz."
    if os.path.basename(p.replace("\\", "/")).lower() not in ("java", "java.exe"):
        return "Java yolu bir 'java' ya da 'java.exe' dosyasına işaret etmeli."
    if not os.path.isabs(p):
        return "Tam yol ver (örn. C:\\Program Files\\Java\\jdk-21\\bin\\java.exe) ya da sadece 'java' yaz."
    if not Path(p).is_file():
        return f"Java dosyası bulunamadı: {p}"
    return None
