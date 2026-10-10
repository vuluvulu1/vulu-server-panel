from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import get_instance
from ..services.container import players
from ..services.players import PlayerError
from ..templating import templates
from ..i18n import _t

router = APIRouter()


def _inst(iid: int) -> dict:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, _t("Sunucu bulunamadı"))
    return inst


@router.get("/instances/{iid}/players")
async def players_page(request: Request, iid: int):
    return templates.TemplateResponse(request, "instance_players.html", {"inst": _inst(iid)})


@router.get("/api/instances/{iid}/players/list")
async def players_list(iid: int):
    return players.overview(_inst(iid))


class ActionBody(BaseModel):
    action: str = Field(max_length=20)
    name: str = Field("", max_length=16)
    reason: str = Field("", max_length=100)


@router.post("/api/instances/{iid}/players/action")
async def players_action(iid: int, b: ActionBody):
    inst = _inst(iid)
    try:
        msg = await players.action(inst, b.action, b.name.strip(), b.reason)
    except PlayerError as e:
        raise HTTPException(400, str(e))
    return {"message": msg, **players.overview(get_instance(iid))}
