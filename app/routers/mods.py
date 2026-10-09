import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import get_instance
from ..services.container import launcher, mods, modupdater
from ..services.modcheck import check_mods
from ..services.modrinth import FILENAME_ANY, LOADER_FILTER, SLUG, ModrinthError, read_mods_info, target_dir
from ..templating import templates

router = APIRouter()
STOPPED = ("stopped", "crashed")


def _inst(iid: int) -> dict:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    if not (inst.get("mc_version") and inst.get("loader") in LOADER_FILTER):
        raise HTTPException(400, "Mod tarayıcı için Minecraft sürümü ve Fabric/Forge/NeoForge/Paper yükleyicisi gerekli.")
    return inst


def _stopped(iid: int) -> None:
    if launcher.pm.status(iid) not in STOPPED:
        raise HTTPException(409, "Önce sunucuyu durdur (dosyalar çalışırken değiştirilmez).")


@router.get("/instances/{iid}/mods")
async def mods_page(request: Request, iid: int):
    return templates.TemplateResponse(request, "instance_mods.html", {"inst": _inst(iid)})


@router.get("/api/instances/{iid}/mods/search")
async def mods_search(iid: int, q: str = Query("", max_length=100), offset: int = Query(0, ge=0, le=1000)):
    inst = _inst(iid)
    try:
        res = await mods.search(q, inst["mc_version"], inst["loader"], offset)
    except ModrinthError as e:
        raise HTTPException(502, str(e))
    have = {m["slug"] for m in (read_mods_info(Path(inst["path"])) or {}).get("mods", {}).values()}
    for h in res["hits"]:
        h["installed"] = h["slug"] in have
    return res


@router.get("/api/instances/{iid}/mods/installed")
async def mods_installed(iid: int):
    inst = _inst(iid)
    return {"items": mods.installed_list(Path(inst["path"]), inst["loader"]), "dir": target_dir(inst["loader"]),
            "status": launcher.pm.status(iid)}


@router.get("/api/instances/{iid}/mods/check")
async def mods_check(iid: int):
    """Eksik zorunlu bağımlılıklar ve istemciye özel modlar (yalnızca okuma)."""
    inst = _inst(iid)
    if inst["loader"] == "paper":
        return {"missing": [], "client_only": [], "scanned": 0, "unreadable": []}
    return await asyncio.to_thread(check_mods, Path(inst["path"]) / target_dir(inst["loader"]))


@router.post("/api/instances/{iid}/mods/updates/check")
async def mods_updates_check(iid: int):
    """Kurulu jar'ların Modrinth'teki daha yeni sürümleri (hash ile; elle eklenenler dahil)."""
    inst = _inst(iid)
    try:
        res = await modupdater.check(inst)
    except ModrinthError as e:
        raise HTTPException(502, str(e))
    keep = ("file", "title", "current", "new", "new_type")
    return {**res, "items": [{k: it[k] for k in keep} for it in res["items"]]}


class UpdateBody(BaseModel):
    files: list[str] = Field(min_length=1, max_length=1000)


@router.post("/api/instances/{iid}/mods/updates/apply")
async def mods_updates_apply(iid: int, body: UpdateBody):
    inst = _inst(iid)
    _stopped(iid)
    files = [f for f in body.files if isinstance(f, str) and FILENAME_ANY.match(f)]
    if not files:
        raise HTTPException(400, "Geçerli dosya seçilmedi.")
    job = modupdater.ensure_apply_job(inst, files)
    return {"job_id": job.id}


class AddBody(BaseModel):
    slug: str = Field(min_length=2, max_length=64)


class FileBody(BaseModel):
    filename: str = Field(min_length=1, max_length=170)
    enabled: bool = True


@router.post("/api/instances/{iid}/mods/add")
async def mods_add(iid: int, body: AddBody):
    inst = _inst(iid)
    _stopped(iid)
    if not SLUG.match(body.slug):
        raise HTTPException(400, "Geçersiz mod adı.")
    return {"job_id": mods.ensure_add_job(iid, Path(inst["path"]), inst["mc_version"], inst["loader"], body.slug).id}


@router.post("/api/instances/{iid}/mods/toggle")
async def mods_toggle(iid: int, body: FileBody):
    inst = _inst(iid)
    _stopped(iid)
    try:
        mods.set_enabled(Path(inst["path"]), inst["loader"], body.filename, body.enabled)
    except ModrinthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/api/instances/{iid}/mods/remove")
async def mods_remove(iid: int, body: FileBody):
    inst = _inst(iid)
    _stopped(iid)
    try:
        mods.remove(Path(inst["path"]), inst["loader"], body.filename)
    except ModrinthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
