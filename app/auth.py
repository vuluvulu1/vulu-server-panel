"""Giriş sistemi: tek yönetici hesabı, oturum çerezi, deneme sınırı, ilk kurulum kodu.

- Parola: hashlib.scrypt (standart kütüphane; ek bağımlılık yok, Termux'ta da derleme gerekmez).
- Oturum: rastgele 256 bit belirteç; veritabanında yalnızca SHA-256'sı tutulur. Çerez HttpOnly + SameSite=Strict
  (+ HTTPS ise Secure). Başka sitelerden gelen istekler ayrıca LocalGuardMiddleware'de engellenir.
- İlk kurulum: hiç hesap yokken panel açılışta tek kullanımlık bir kurulum kodu üretir, konsola yazar ve
  data/setup-code.txt dosyasına koyar. Hesap yalnızca bu kodla oluşturulabilir (ağdaki başka biri önce davranıp
  hesabı ele geçiremesin).
- Deneme sınırı: aynı IP ya da kullanıcı adı için art arda 5 hatalı girişten sonra artan süreli bekleme.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone

from starlette.responses import JSONResponse, RedirectResponse

from .config import DATA_DIR
from .db import get_conn
from .i18n import _t

log = logging.getLogger("vulu.auth")

COOKIE = "vulu_session"
SESSION_SHORT = timedelta(hours=12)
SESSION_LONG = timedelta(days=30)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 10
SETUP_FILE = DATA_DIR / "setup-code.txt"
PUBLIC_PREFIXES = ("/static/",)
PUBLIC_PATHS = {"/login", "/setup", "/favicon.ico"}

_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}


# ---------------- parola ----------------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode("utf-8"), salt=salt, maxmem=64 * 1024 * 1024, dklen=32, **_SCRYPT)
    b = lambda x: base64.b64encode(x).decode()
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b(salt)}${b(dk)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(dk)
        got = hashlib.scrypt(pw.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=64 * 1024 * 1024, dklen=len(want))
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


_DUMMY = None


def _dummy_hash() -> str:                       # kullanıcı yokken de aynı süre harcansın (kullanıcı adı sızmasın)
    global _DUMMY
    _DUMMY = _DUMMY or hash_password(secrets.token_hex(16))
    return _DUMMY


def password_problem(pw: str, username: str = "") -> str | None:
    if len(pw) < MIN_PASSWORD:
        return _t('Parola en az {MIN_PASSWORD} karakter olmalı.', MIN_PASSWORD=MIN_PASSWORD)
    if len(pw) > 256:
        return _t("Parola çok uzun.")
    if username and pw.lower() == username.lower():
        return _t("Parola kullanıcı adıyla aynı olamaz.")
    return None


# ---------------- kullanıcılar ----------------
def user_count() -> int:
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(username: str, password: str) -> int:
    with get_conn() as c:
        return c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, hash_password(password))).lastrowid


def authenticate(username: str, password: str) -> dict | None:
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    if not row:
        verify_password(password, _dummy_hash())
        return None
    return dict(row) if verify_password(password, row["password_hash"]) else None


def set_password(user_id: int, password: str) -> None:
    with get_conn() as c:
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))


# ---------------- oturumlar ----------------
def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(user_id: int, remember: bool, ip: str, ua: str) -> str:
    token = secrets.token_urlsafe(32)
    exp = _now() + (SESSION_LONG if remember else SESSION_SHORT)
    with get_conn() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))
        c.execute("INSERT INTO sessions (token_hash, user_id, remember, expires_at, last_seen, ip, user_agent) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (_h(token), user_id, 1 if remember else 0, exp.isoformat(), _now().isoformat(), ip[:64], ua[:200]))
    return token


def session_user(token: str | None) -> dict | None:
    if not token or len(token) > 100:
        return None
    th = _h(token)
    with get_conn() as c:
        row = c.execute("SELECT s.id AS sid, s.remember, s.expires_at, s.last_seen, u.id, u.username, u.role "
                        "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?", (th,)).fetchone()
        if not row:
            return None
        now = _now()
        if datetime.fromisoformat(row["expires_at"]) < now:
            c.execute("DELETE FROM sessions WHERE id = ?", (row["sid"],))
            return None
        if now - datetime.fromisoformat(row["last_seen"]) > timedelta(minutes=5):     # kayan süre (seyrek yazım)
            exp = now + (SESSION_LONG if row["remember"] else SESSION_SHORT)
            c.execute("UPDATE sessions SET last_seen = ?, expires_at = ? WHERE id = ?", (now.isoformat(), exp.isoformat(), row["sid"]))
    return {"id": row["id"], "username": row["username"], "role": row["role"], "sid": row["sid"]}


def delete_session(token: str | None) -> None:
    if token:
        with get_conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (_h(token),))


def delete_other_sessions(user_id: int, keep_sid: int | None) -> int:
    with get_conn() as c:
        return c.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user_id, keep_sid or -1)).rowcount


def list_sessions(user_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute("SELECT id, ip, user_agent, last_seen, created_at FROM sessions WHERE user_id = ? AND expires_at > ? "
                         "ORDER BY last_seen DESC", (user_id, _now().isoformat())).fetchall()
    return [dict(r) for r in rows]


# ---------------- ilk kurulum kodu ----------------
_setup_code: str | None = None


def ensure_setup_code() -> str | None:
    """Hesap yoksa kurulum kodu üret/göster. Hesap varsa dosyayı sil."""
    global _setup_code
    if user_count() > 0:
        _setup_code = None
        SETUP_FILE.unlink(missing_ok=True)
        return None
    if not _setup_code:
        _setup_code = "-".join(secrets.token_hex(3).upper() for _ in range(3))
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            fd = os.open(SETUP_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(_setup_code + "\n")
        except OSError:
            pass
        bar = "=" * 60
        code = _setup_code
        if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):          # terminalde kodu öne çıkar
            bar = f"\x1b[38;2;156;112;76m{bar}\x1b[0m"
            code = f"\x1b[1;38;2;201;169;146m{code}\x1b[0m"
        msg = (_t('\n{bar}\n  vulu panel ilk kurulum kodu:  {setup_code}\n  Tarayıcıda paneli aç ve yönetici hesabını bu kodla oluştur.\n  (Kod ayrıca {SETUP_FILE} dosyasında.)\n{bar}\n', bar=bar, setup_code=code, SETUP_FILE=SETUP_FILE))
        print(msg, flush=True)
    return _setup_code


def check_setup_code(code: str) -> bool:
    return bool(_setup_code) and hmac.compare_digest(code.strip().upper(), _setup_code)


def finish_setup() -> None:
    global _setup_code
    _setup_code = None
    SETUP_FILE.unlink(missing_ok=True)


# ---------------- deneme sınırı ----------------
class RateLimiter:
    def __init__(self, free: int = 5, base: float = 30, cap: float = 900) -> None:
        self.free, self.base, self.cap = free, base, cap
        self._d: dict[str, tuple[int, float]] = {}     # anahtar → (hata sayısı, kilit bitişi)

    def wait(self, *keys: str) -> float:
        now = time.monotonic()
        return max((self._d.get(k, (0, 0))[1] - now for k in keys), default=0.0)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        if len(self._d) > 10000:
            self._d.clear()
        for k in keys:
            n = self._d.get(k, (0, 0))[0] + 1
            lock = now + min(self.cap, self.base * 2 ** (n - self.free)) if n >= self.free else 0
            self._d[k] = (n, lock)

    def ok(self, *keys: str) -> None:
        for k in keys:
            self._d.pop(k, None)


limiter = RateLimiter()


def client_ip(scope) -> str:
    c = scope.get("client")
    return c[0] if c else "?"


def safe_next(nxt: str | None) -> str:
    if not nxt or not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt or len(nxt) > 300:
        return "/"
    return nxt


# ---------------- ara katman ----------------
def _cookie(scope) -> str | None:
    for k, v in scope.get("headers", []):
        if k == b"cookie":
            for part in v.decode("latin-1").split(";"):
                name, _, val = part.strip().partition("=")
                if name == COOKIE:
                    return val
    return None


class AuthMiddleware:
    """Giriş yapılmamış istekleri durdurur: sayfalar → /login (ya da hesap yoksa /setup), API → 401,
    WebSocket → kapatılır. Statik dosyalar ve giriş/kurulum sayfaları serbesttir."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await self.app(scope, receive, send)
        user = session_user(_cookie(scope))
        if user:
            scope.setdefault("state", {})["user"] = user
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
            return
        if path.startswith("/api/"):
            resp = JSONResponse({"detail": _t("Oturum süresi doldu, yeniden giriş yap.")}, status_code=401)
        elif user_count() == 0:
            resp = RedirectResponse("/setup", status_code=303)
        else:
            qs = scope.get("query_string", b"").decode("latin-1")
            nxt = path + ("?" + qs if qs else "")
            from urllib.parse import quote
            resp = RedirectResponse("/login?next=" + quote(safe_next(nxt), safe=""), status_code=303)
        await resp(scope, receive, send)
