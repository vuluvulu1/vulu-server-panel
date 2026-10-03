from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.container import paper
from ..services.paper import PaperError

router = APIRouter()


@router.get("/api/paper/resolve")
async def paper_resolve(mc_version: str):
    """Seçilen sürüm için indirilecek Paper build'ini (kanal, boyut, önbellekte mi) döndürür."""
    try:
        info = await paper.resolve(mc_version)
    except PaperError as e:
        raise HTTPException(400, str(e))
    return {k: info[k] for k in ("version", "build", "channel", "stable", "name", "size")} | {"cached": paper.is_cached(info)}


class DownloadBody(BaseModel):
    mc_version: str = Field(min_length=1, max_length=40)


@router.post("/api/paper/download")
async def paper_download(body: DownloadBody):
    """Jar'ı önbelleğe indirir (yüzdeli iş). Sunucu ilk başlatılınca önbellekten kopyalanır."""
    try:
        info = await paper.resolve(body.mc_version)
    except PaperError as e:
        raise HTTPException(400, str(e))
    if paper.is_cached(info):
        return {"cached": True, "job_id": None}
    return {"cached": False, "job_id": paper.ensure_cached_job(body.mc_version).id}
