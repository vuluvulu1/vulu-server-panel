from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.container import installers
from ..services.paper import PaperError
from ..i18n import _t

router = APIRouter()


def _mgr(loader: str):
    mgr = installers.get(loader)
    if not mgr:
        raise HTTPException(400, _t("Bu mod yükleyici için otomatik indirme yok."))
    return mgr


@router.get("/api/loader/resolve")
async def loader_resolve(loader: str, mc_version: str):
    """İndirilecek jar'ı (etiket, kanal, boyut, önbellekte mi) döndürür."""
    mgr = _mgr(loader)
    try:
        info = await mgr.resolve(mc_version)
    except PaperError as e:
        raise HTTPException(400, str(e))
    return {"loader": loader, "version": info["version"], "label": info["label"], "stable": info["stable"],
            "size": info["size"], "cached": mgr.is_cached(info)}


class LoaderDownload(BaseModel):
    loader: str = Field(min_length=1, max_length=20)
    mc_version: str = Field(min_length=1, max_length=40)


@router.post("/api/loader/download")
async def loader_download(body: LoaderDownload):
    mgr = _mgr(body.loader)
    try:
        info = await mgr.resolve(body.mc_version)
    except PaperError as e:
        raise HTTPException(400, str(e))
    if mgr.is_cached(info):
        return {"cached": True, "job_id": None}
    return {"cached": False, "job_id": mgr.ensure_cached_job(body.mc_version).id}
