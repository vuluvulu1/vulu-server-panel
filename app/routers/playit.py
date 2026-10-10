"""playit.gg uç noktaları. Ajan anahtarı hiçbir yanıtta dönmez."""
from fastapi import APIRouter, HTTPException

from ..db import get_instance
from ..services.container import playit
from ..services.playit import PlayitError
from ..services.properties import read_properties
from pathlib import Path
from ..i18n import _t

router = APIRouter()


def _err(e: Exception):
    raise HTTPException(400, str(e))


@router.get("/api/playit/status")
async def playit_status():
    return playit.status()


@router.post("/api/playit/install")
async def playit_install():
    if not playit.status()["supported"]:
        raise HTTPException(400, _t("Bu sistemde playit desteklenmiyor (Windows x64 ve Linux x64)."))
    return {"job_id": playit.ensure_install_job().id}


@router.post("/api/playit/link")
async def playit_link():
    if not playit.installed():
        raise HTTPException(400, _t("Önce playit kurulmalı."))
    try:
        return playit.start_claim()
    except PlayitError as e:
        _err(e)


@router.post("/api/playit/cancel")
async def playit_cancel():
    playit.cancel_claim()
    return {"ok": True}


@router.post("/api/playit/unlink")
async def playit_unlink():
    await playit.unlink()
    return {"ok": True}


@router.post("/api/playit/restart")
async def playit_restart():
    try:
        await playit.stop_agent()
        await playit.start_agent()
    except PlayitError as e:
        _err(e)
    return {"ok": True}


def _inst(iid: int) -> dict:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, _t("Sunucu bulunamadı"))
    return inst


def _warnings(inst: dict) -> list[str]:
    p = Path(inst["path"]) / "server.properties"
    props = read_properties(p) if p.is_file() else {}
    w = []
    if props.get("online-mode", "true") == "false":
        w.append(_t("Hesap doğrulaması kapalı (online-mode=false): adresi bilen herkes istediği adla girebilir."))
    if props.get("white-list", "false") != "true":
        w.append(_t("Beyaz liste kapalı: adresi bilen herkes girebilir. Oyuncular sekmesinden açabilirsin."))
    return w


@router.get("/api/instances/{iid}/playit")
async def instance_playit(iid: int):
    inst = _inst(iid)
    st = playit.status()
    out = {"linked": st["linked"], "running": st["running"], "tunnel": None, "error": "", "warnings": _warnings(inst)}
    if st["linked"]:
        try:
            out["tunnel"] = await playit.tunnel_for(int(inst["port"]))
        except PlayitError as e:
            out["error"] = str(e)
    return out


@router.post("/api/instances/{iid}/playit/open")
async def instance_playit_open(iid: int):
    inst = _inst(iid)
    if not playit.linked():
        raise HTTPException(400, _t("Önce Ayarlar → playit.gg bölümünden hesabını bağla."))
    try:
        if not playit.running():
            await playit.start_agent()
        t = await playit.create_tunnel(inst["name"], int(inst["port"]))
    except PlayitError as e:
        raise HTTPException(400, _t('{e} Tüneli playit.gg/account/tunnels sayfasından elle de oluşturabilirsin: tür Minecraft Java, yerel adres 127.0.0.1, yerel port {port}.', e=e, port=inst['port']))
    return {"tunnel": t}


@router.post("/api/instances/{iid}/playit/close")
async def instance_playit_close(iid: int):
    inst = _inst(iid)
    try:
        await playit.delete_tunnel(int(inst["port"]))
    except PlayitError as e:
        _err(e)
    return {"ok": True}
