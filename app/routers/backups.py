from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..db import get_conn, get_instance, update_instance
from ..services.backup import BackupError
from ..services.container import backups, jobs, launcher
from ..templating import templates
from ..i18n import _t

router = APIRouter()
STOPPED = ("stopped", "crashed")


def _inst(iid: int) -> dict:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, _t("Sunucu bulunamadı"))
    return inst


@router.get("/backups")
async def backups_overview(request: Request):
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM instances ORDER BY id").fetchall()]
    for r in rows:
        items = backups.list_backups(r)
        r["backup_count"], r["backup_size"] = len(items), sum(i["size"] for i in items)
        r["last_backup"] = items[0]["created"] if items else None
    return templates.TemplateResponse(request, "backups.html", {"rows": rows})


@router.get("/instances/{iid}/backups")
async def backups_page(request: Request, iid: int):
    return templates.TemplateResponse(request, "instance_backups.html", {"inst": _inst(iid)})


@router.get("/api/instances/{iid}/backups/list")
async def backups_list(iid: int):
    inst = _inst(iid)
    running = jobs.find_running(f"backup-{iid}") or jobs.find_running(f"restore-{iid}")
    return {"items": backups.list_backups(inst), "status": launcher.pm.status(iid), "job_id": running.id if running else None,
            "limit": inst.get("backup_limit") or 0}


class CreateBody(BaseModel):
    mode: str = Field("full", pattern=r"^(full|world)$")
    note: str = Field("", max_length=60)


class FileBody(BaseModel):
    file: str = Field(max_length=120)


@router.post("/api/instances/{iid}/backups/create")
async def backups_create(iid: int, b: CreateBody):
    inst = _inst(iid)
    if jobs.find_running(f"restore-{iid}"):
        raise HTTPException(409, _t("Geri yükleme sürüyor."))
    if launcher.pm.status(iid) in ("preparing", "starting", "stopping"):
        raise HTTPException(409, _t("Sunucu başlarken/dururken yedek alınamaz; birkaç saniye bekle."))
    return {"job_id": backups.ensure_create_job(inst, b.mode, b.note.strip()).id}


class LimitBody(BaseModel):
    enabled: bool
    max: int = Field(5, ge=1, le=500)


@router.post("/api/instances/{iid}/backups/limit")
async def backups_limit(iid: int, b: LimitBody):
    _inst(iid)
    update_instance(iid, backup_limit=b.max if b.enabled else None)
    return {"ok": True, "limit": b.max if b.enabled else 0}


@router.post("/api/instances/{iid}/backups/restore")
async def backups_restore(iid: int, b: FileBody):
    inst = _inst(iid)
    if launcher.pm.status(iid) not in STOPPED:
        raise HTTPException(409, _t("Geri yüklemek için önce sunucuyu durdur."))
    if jobs.find_running(f"backup-{iid}") or any(j.status == "running" and (j.key or "").endswith(f"-{iid}") for j in jobs._jobs.values()):
        raise HTTPException(409, _t("Bu sunucu için başka bir işlem sürüyor; bitmesini bekle."))
    try:
        return {"job_id": backups.ensure_restore_job(inst, b.file).id}
    except BackupError as e:
        raise HTTPException(400, str(e))


@router.post("/api/instances/{iid}/backups/delete")
async def backups_delete(iid: int, b: FileBody):
    inst = _inst(iid)
    try:
        backups.delete(inst, b.file)
    except BackupError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.get("/api/instances/{iid}/backups/download")
async def backups_download(iid: int, file: str = Query(..., max_length=120)):
    inst = _inst(iid)
    try:
        p = backups.path_for(inst, file)
    except BackupError as e:
        raise HTTPException(404, str(e))
    return FileResponse(p, filename=p.name, media_type="application/zip")
