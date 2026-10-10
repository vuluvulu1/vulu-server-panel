from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..services.container import installers, java, jobs, minecraft
from ..services.java_manager import JavaError
from ..services.minecraft import McError
from ..services.paper import PaperError
from ..i18n import _t

router = APIRouter()


@router.get("/api/minecraft/versions")
async def mc_versions(snapshots: bool = False, loader: str = "vanilla"):
    """loader=paper ise yalnızca Paper'ın desteklediği sürümler döner."""
    try:
        if loader in installers:
            return await installers[loader].versions()
        return await minecraft.list_versions(snapshots)
    except (McError, PaperError) as e:
        raise HTTPException(502, str(e))


@router.get("/api/java/resolve")
async def java_resolve(mc_version: str | None = None, loader: str = "vanilla", major: int | None = None):
    """Gereken Java'yı tespit eder ve kurulu olup olmadığını/indirme boyutunu döndürür."""
    if major is None:
        if not mc_version:
            raise HTTPException(400, _t("mc_version ya da major gerekli"))
        try:
            r = await minecraft.java_for(mc_version, loader)
        except McError as e:
            raise HTTPException(400, str(e))
        major, reason = r["major"], r["reason"]
    else:
        reason = _t('Elle seçildi: Java {major}', major=major)
    try:
        info = await java.info(major)
    except JavaError as e:
        raise HTTPException(400, str(e))
    info["reason"] = reason
    return info


@router.get("/api/java/installed")
async def java_installed():
    return java.installed()


class InstallBody(BaseModel):
    major: int = Field(ge=8, le=99)


@router.post("/api/java/install")
async def java_install(body: InstallBody):
    if java.find(body.major):
        return {"installed": True, "job_id": None}
    job = java.ensure_job(body.major)
    return {"installed": False, "job_id": job.id}


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(ws: WebSocket, job_id: str):
    job = jobs.get(job_id)
    if not job:
        await ws.close(code=4404)
        return
    await ws.accept()
    try:
        async for snap in job.watch():
            await ws.send_json(snap)
            if snap["status"] != "running":
                break
        await ws.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
