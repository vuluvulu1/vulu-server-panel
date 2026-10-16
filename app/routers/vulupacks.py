"""vulu Packs: panelin vulu hesabına bağlanması, paket listesi ve paketten kurulan sunucuların güncellenmesi."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import VULU_API
from ..db import get_conn, get_instance, update_instance
from ..services.container import launcher, vulupacks
from ..services.vulupacks import VuluPackError, read_installed
from ..templating import templates
from ..i18n import _t

router = APIRouter()


@router.get("/vulupacks")
async def vulupacks_page(request: Request):
    acc = vulupacks.account()
    return templates.TemplateResponse(request, "vulupacks.html", {"account": acc and acc["username"], "api": VULU_API})


@router.get("/api/vulupacks")
async def vulupacks_list():
    if not vulupacks.account():
        return {"account": None, "packs": []}
    try:
        packs = await vulupacks.list()
    except VuluPackError as e:
        raise HTTPException(502, str(e))
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, vulu_pack_id, vulu_pack_revision FROM instances WHERE vulu_pack_id IS NOT NULL").fetchall()
    servers: dict[str, list] = {}
    for r in rows:
        servers.setdefault(r["vulu_pack_id"], []).append({"id": r["id"], "name": r["name"], "revision": r["vulu_pack_revision"]})
    for p in packs:
        p["servers"] = servers.get(p["id"], [])
    acc = vulupacks.account()
    return {"account": acc and acc["username"], "packs": packs}


class LinkBody(BaseModel):
    username: str = Field(max_length=16)
    password: str = Field(max_length=72)


@router.post("/api/vulupacks/link")
async def vulupacks_link(b: LinkBody):
    if not b.username.strip() or not b.password:
        raise HTTPException(400, _t("Kullanıcı adı ve şifre gerekli."))
    try:
        return await vulupacks.link(b.username.strip(), b.password)
    except VuluPackError as e:
        raise HTTPException(400, str(e))


@router.post("/api/vulupacks/unlink")
async def vulupacks_unlink():
    await vulupacks.unlink()
    return {"ok": True}


@router.post("/api/instances/{iid}/vulupack/update")
async def vulupack_update(iid: int):
    """Paketin son revizyonu kurulu revizyondan yeniyse, sunucu bir sonraki başlatılışında onu kurar."""
    inst = get_instance(iid)
    if not inst or not inst.get("vulu_pack_id"):
        raise HTTPException(404, _t("Bu sunucu bir vulu paketinden kurulmadı."))
    try:
        p = await vulupacks.get(inst["vulu_pack_id"])
    except VuluPackError as e:
        raise HTTPException(400, str(e))
    latest = int(p.get("revision") or 1)
    installed = (read_installed(Path(inst["path"])) or {}).get("revision")
    if p.get("loader") != inst.get("loader") or p.get("mcVersion") != inst.get("mc_version"):
        raise HTTPException(409, _t("Paket artık {loader} {mc} kullanıyor; bu sunucu {l2} {mc2}. Paketten yeni bir sunucu oluştur.",
                                     loader=p.get("loader"), mc=p.get("mcVersion"), l2=inst.get("loader"), mc2=inst.get("mc_version")))
    if installed == latest:
        return {"updated": False, "revision": latest, "message": _t("Sunucu paketin son revizyonunda (rev {r}).", r=latest)}
    update_instance(iid, vulu_pack_revision=latest)
    running = launcher.pm.status(iid) not in ("stopped", "crashed")
    msg = (_t("Rev {r} sunucu yeniden başlatılınca kurulacak.", r=latest) if running
           else _t("Rev {r} sunucu başlatılınca kurulacak.", r=latest))
    return {"updated": True, "revision": latest, "installed": installed, "message": msg}
