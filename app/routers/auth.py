"""Giriş, çıkış, ilk kurulum ve hesap ayarları."""
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .. import auth
from ..config import HOST, PORT
from ..templating import templates
from ..i18n import _t

router = APIRouter()


def _set_cookie(resp, request: Request, token: str, remember: bool) -> None:
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", path="/",
                    secure=request.url.scheme == "https",
                    max_age=int(auth.SESSION_LONG.total_seconds()) if remember else None)


def _page(request: Request, name: str, ctx: dict, status: int = 200):
    return templates.TemplateResponse(request, name, {"bare": True, **ctx}, status_code=status)


# ---------- ilk kurulum ----------
@router.get("/setup")
async def setup_page(request: Request):
    if auth.user_count() > 0:
        return RedirectResponse("/login", status_code=303)
    auth.ensure_setup_code()
    return _page(request, "setup.html", {"error": "", "username": "admin"})


@router.post("/setup")
async def setup_submit(request: Request, code: str = Form(""), username: str = Form(""),
                       password: str = Form(""), password2: str = Form("")):
    if auth.user_count() > 0:
        return RedirectResponse("/login", status_code=303)
    ip = auth.client_ip(request.scope)
    username = username.strip()
    err = ""
    if (w := auth.limiter.wait("setup:" + ip)) > 0:
        err = _t('Çok fazla hatalı deneme. {v0} sn sonra tekrar dene.', v0=int(w) + 1)
    elif not auth.check_setup_code(code):
        auth.limiter.fail("setup:" + ip)
        err = _t("Kurulum kodu yanlış. Kod, paneli başlattığın konsolda ve data/setup-code.txt dosyasında yazıyor.")
    elif not auth.USERNAME_RE.match(username):
        err = _t("Kullanıcı adı 3-32 karakter olmalı (harf, rakam, . _ -).")
    elif p := auth.password_problem(password, username):
        err = p
    elif password != password2:
        err = _t("Parolalar aynı değil.")
    if err:
        return _page(request, "setup.html", {"error": err, "username": username}, 400)
    uid = auth.create_user(username, password)
    auth.finish_setup()
    token = auth.create_session(uid, True, ip, request.headers.get("user-agent", ""))
    resp = RedirectResponse("/", status_code=303)
    _set_cookie(resp, request, token, True)
    return resp


# ---------- giriş / çıkış ----------
@router.get("/login")
async def login_page(request: Request, next: str = "/"):
    if auth.user_count() == 0:
        return RedirectResponse("/setup", status_code=303)
    if auth.session_user(request.cookies.get(auth.COOKIE)):
        return RedirectResponse(auth.safe_next(next), status_code=303)
    return _page(request, "login.html", {"error": "", "next": auth.safe_next(next), "username": ""})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(""), password: str = Form(""),
                       remember: str | None = Form(None), next: str = Form("/")):
    ip = auth.client_ip(request.scope)
    username = username.strip()[:64]
    keys = ("ip:" + ip, "user:" + username.lower())
    nxt = auth.safe_next(next)
    if (w := auth.limiter.wait(*keys)) > 0:
        return _page(request, "login.html", {"error": _t('Çok fazla hatalı deneme. {v0} sn sonra tekrar dene.', v0=int(w) + 1),
                                             "next": nxt, "username": username}, 429)
    user = auth.authenticate(username, password[:256])
    if not user:
        auth.limiter.fail(*keys)
        return _page(request, "login.html", {"error": _t("Kullanıcı adı ya da parola yanlış."), "next": nxt, "username": username}, 401)
    auth.limiter.ok(*keys)
    token = auth.create_session(user["id"], bool(remember), ip, request.headers.get("user-agent", ""))
    resp = RedirectResponse(nxt, status_code=303)
    _set_cookie(resp, request, token, bool(remember))
    return resp


@router.post("/logout")
async def logout(request: Request):
    auth.delete_session(request.cookies.get(auth.COOKIE))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# ---------- hesap ----------
def _user(request: Request) -> dict:
    u = request.scope.get("state", {}).get("user")
    if not u:
        raise HTTPException(401, _t("Giriş gerekli."))
    return u


@router.get("/api/account")
async def account_info(request: Request):
    u = _user(request)
    sessions = auth.list_sessions(u["id"])
    import socket
    lan = []
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))            # paket gönderilmez; yalnızca yerel IP öğrenilir
            lan.append(f"http://{s.getsockname()[0]}:{PORT}")
            s.close()
        except OSError:
            pass
    return {"username": u["username"], "sessions": [{**s, "current": s["id"] == u["sid"]} for s in sessions],
            "bind": HOST, "port": PORT, "lan_urls": lan}


class PasswordBody(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


@router.post("/api/account/password")
async def change_password(request: Request, b: PasswordBody):
    u = _user(request)
    ip = auth.client_ip(request.scope)
    if auth.limiter.wait("pw:" + ip) > 0:
        raise HTTPException(429, _t("Çok fazla hatalı deneme, biraz bekle."))
    if not auth.authenticate(u["username"], b.current):
        auth.limiter.fail("pw:" + ip)
        raise HTTPException(400, _t("Mevcut parola yanlış."))
    if p := auth.password_problem(b.new, u["username"]):
        raise HTTPException(400, p)
    auth.set_password(u["id"], b.new)
    n = auth.delete_other_sessions(u["id"], u["sid"])
    return {"message": _t("Parola değiştirildi.") + (_t(' Diğer {n} oturum kapatıldı.', n=n) if n else "")}


@router.post("/api/account/logout-others")
async def logout_others(request: Request):
    u = _user(request)
    n = auth.delete_other_sessions(u["id"], u["sid"])
    return {"message": _t('{n} oturum kapatıldı.', n=n) if n else _t("Başka açık oturum yok.")}
