from fastapi import APIRouter, HTTPException

from ..db import get_conn, get_instance
from ..services.container import stats

router = APIRouter()


@router.get("/api/stats")
async def all_stats():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, ram_mb FROM instances").fetchall()
    return {str(r["id"]): stats.snapshot(r["id"], r["ram_mb"]) for r in rows}


@router.get("/api/instances/{iid}/stats")
async def instance_stats(iid: int):
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    return stats.snapshot(iid, inst["ram_mb"], history=True)   # RCON şifresi asla dönmez
