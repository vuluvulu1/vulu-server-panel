"""Panel ayarları (adres, port, iletişim, alan adları) ve panelin yeniden başlatılması."""
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth, panel_settings as ps
from ..config import ALLOWED_HOSTS_EXTRA, DATA_DIR, HOST, PANEL_CONTACT, PORT, SUPERVISED
from ..services.container import process_manager
from ..services.restart import request_restart
from ..services.updater import UpdateError, updater
from ..i18n import _t

router = APIRouter()
BOOT_ID = os.urandom(6).hex()                       # her açılışta değişir (yeniden başlatma bitti mi?)


def _running() -> dict:
    return {"host_mode": ps.host_mode(HOST), "port": PORT, "contact": PANEL_CONTACT,
            "allowed_hosts": ", ".join(ALLOWED_HOSTS_EXTRA)}


def _saved() -> dict:
    s = ps.load(DATA_DIR)
    r = _running()
    return {"host_mode": ps.host_mode(s["host"]) if "host" in s else r["host_mode"], "port": s.get("port", r["port"]),
            "contact": s.get("contact", r["contact"]),
            "allowed_hosts": ", ".join(s["allowed_hosts"]) if "allowed_hosts" in s else r["allowed_hosts"]}


class LangBody(BaseModel):
    lang: str = Field(max_length=8)


@router.post("/api/panel/lang")
async def set_lang(body: LangBody):
    from .. import i18n
    if body.lang not in i18n.LANGS:
        raise HTTPException(400, i18n._("Desteklenmeyen dil."))
    i18n.set_global(body.lang)
    return {"ok": True, "lang": body.lang}


@router.get("/api/panel/settings")
async def get_settings():
    saved, running = _saved(), _running()
    return {"saved": saved, "running": running, "restart_needed": saved != running, "supervised": SUPERVISED,
            "running_servers": len(process_manager.running_ids()), "boot": BOOT_ID}


class SettingsBody(BaseModel):
    host_mode: str = Field(max_length=10)
    port: int
    contact: str = Field("", max_length=120)
    allowed_hosts: str = Field("", max_length=1000)
    password: str = Field("", max_length=256)


def _user(request: Request) -> dict:
    u = request.scope.get("state", {}).get("user")
    if not u:
        raise HTTPException(401, _t("Giriş gerekli."))
    return u


@router.post("/api/panel/settings")
async def save_settings(request: Request, b: SettingsBody):
    u = _user(request)
    clean, err = ps.validate(b.model_dump())
    if err:
        raise HTTPException(400, err)
    cur = _saved()
    net_changed = (b.host_mode, b.port, ", ".join(clean["allowed_hosts"])) != (cur["host_mode"], cur["port"], cur["allowed_hosts"])
    if net_changed:                                   # ağ ayarları: parola onayı (oturum çalınsa bile panel ağa açılamasın)
        ip = auth.client_ip(request.scope)
        if auth.limiter.wait("pw:" + ip) > 0:
            raise HTTPException(429, _t("Çok fazla hatalı deneme, biraz bekle."))
        if not auth.authenticate(u["username"], b.password):
            auth.limiter.fail("pw:" + ip)
            raise HTTPException(400, _t("Ağ ayarlarını değiştirmek için mevcut parolanı doğru gir."))
    ps.save(DATA_DIR, clean)
    saved = _saved()
    return {"message": _t("Kaydedildi.") + (_t(" Geçerli olması için paneli yeniden başlat.") if saved != _running() else ""),
            "restart_needed": saved != _running()}


@router.post("/api/panel/restart")
async def restart_panel():
    if not SUPERVISED:
        raise HTTPException(400, _t("Panel 'python run.py' ile başlatılmadığı için kendini yeniden başlatamıyor. "
                                 "Konsolda Ctrl+C ile kapatıp 'python run.py' ile yeniden aç."))
    request_restart()
    s = _saved()
    return {"message": _t("Panel yeniden başlatılıyor…"), "port": s["port"], "host_mode": s["host_mode"]}


# ---------------- panel güncellemesi ----------------
@router.get("/api/panel/update")
async def update_state():
    return {**updater.snapshot(), "running_servers": len(process_manager.running_ids())}


@router.post("/api/panel/update/check")
async def update_check():
    return {**(await updater.check()), "running_servers": len(process_manager.running_ids())}


@router.post("/api/panel/update/install")
async def update_install():
    try:
        await updater.install()
    except UpdateError as e:
        raise HTTPException(400, str(e))
    return {"message": updater.state["message"], "boot": BOOT_ID}


class AutoBody(BaseModel):
    enabled: bool


@router.post("/api/panel/update/auto")
async def update_auto(b: AutoBody):
    updater.set_auto(b.enabled)
    return {"ok": True, "auto": b.enabled}
