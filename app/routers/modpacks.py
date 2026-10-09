from fastapi import APIRouter, HTTPException, Query, Request

from ..services.container import modpacks
from ..services.modrinth import ModrinthError
from ..templating import templates

router = APIRouter()


@router.get("/modpacks")
async def modpacks_page(request: Request):
    return templates.TemplateResponse(request, "modpacks.html", {})


@router.get("/api/modpacks/search")
async def modpacks_search(q: str = Query("", max_length=100), offset: int = Query(0, ge=0, le=1000)):
    try:
        return await modpacks.search(q, offset)
    except ModrinthError as e:
        raise HTTPException(502, str(e))
