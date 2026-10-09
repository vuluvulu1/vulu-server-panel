from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import get_conn, get_instance
from ..services.scheduler import DAYS_RE, TIME_RE, next_run
from ..templating import templates

router = APIRouter()
MAX_PER_INSTANCE = 20


def _inst(iid: int) -> dict:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    return inst


@router.get("/instances/{iid}/schedules")
async def schedules_page(request: Request, iid: int):
    return templates.TemplateResponse(request, "instance_schedules.html", {"inst": _inst(iid)})


@router.get("/api/instances/{iid}/schedules/list")
async def schedules_list(iid: int):
    _inst(iid)
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM schedules WHERE instance_id = ? ORDER BY time_hm, id", (iid,))]
    for r in rows:
        n = next_run(r["time_hm"], r["days"]) if r["enabled"] else None
        r["next_run"] = n.strftime("%d.%m.%Y %H:%M") if n else None
    return {"items": rows}


class ScheduleBody(BaseModel):
    kind: str = Field(pattern=r"^(restart|backup)$")
    time_hm: str = Field(max_length=5)
    days: str = Field(max_length=7)
    warn_minutes: int = Field(5, ge=0, le=30)
    backup_mode: str = Field("world", pattern=r"^(full|world)$")
    keep: int = Field(7, ge=1, le=100)


@router.post("/api/instances/{iid}/schedules/create")
async def schedules_create(iid: int, b: ScheduleBody):
    _inst(iid)
    days = "".join(sorted(set(b.days)))
    if not TIME_RE.match(b.time_hm):
        raise HTTPException(400, "Saat SS:DD biçiminde olmalı (örn. 04:00).")
    if not DAYS_RE.match(days):
        raise HTTPException(400, "En az bir gün seç.")
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM schedules WHERE instance_id = ?", (iid,)).fetchone()[0] >= MAX_PER_INSTANCE:
            raise HTTPException(400, f"Bir sunucu için en fazla {MAX_PER_INSTANCE} zamanlama eklenebilir.")
        conn.execute("INSERT INTO schedules (instance_id, kind, time_hm, days, warn_minutes, backup_mode, keep) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (iid, b.kind, b.time_hm, days, b.warn_minutes, b.backup_mode, b.keep))
    return {"ok": True}


class IdBody(BaseModel):
    id: int
    enabled: bool = True


def _own(conn, iid: int, sid: int) -> None:
    if not conn.execute("SELECT 1 FROM schedules WHERE id = ? AND instance_id = ?", (sid, iid)).fetchone():
        raise HTTPException(404, "Zamanlama bulunamadı.")


@router.post("/api/instances/{iid}/schedules/toggle")
async def schedules_toggle(iid: int, b: IdBody):
    with get_conn() as conn:
        _own(conn, iid, b.id)
        conn.execute("UPDATE schedules SET enabled = ? WHERE id = ?", (1 if b.enabled else 0, b.id))
    return {"ok": True}


@router.post("/api/instances/{iid}/schedules/delete")
async def schedules_delete(iid: int, b: IdBody):
    with get_conn() as conn:
        _own(conn, iid, b.id)
        conn.execute("DELETE FROM schedules WHERE id = ?", (b.id,))
    return {"ok": True}
