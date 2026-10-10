import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..services import system as S
from ..services.container import java, jobs, launcher
from ..templating import templates
from ..i18n import _t

router = APIRouter()
JAVA_CHOICES = (8, 11, 17, 21, 25)


@router.get("/settings")
async def system_page(request: Request):
    return templates.TemplateResponse(request, "system.html", {"java_choices": JAVA_CHOICES})


def _java_usage() -> dict[int, list[dict]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, java_major FROM instances WHERE java_major IS NOT NULL").fetchall()
    use: dict[int, list[dict]] = {}
    for r in rows:
        use.setdefault(int(r["java_major"]), []).append({"id": r["id"], "name": r["name"], "status": launcher.pm.status(r["id"])})
    return use


@router.get("/api/system/overview")
async def overview():
    disk = await asyncio.to_thread(S.disk_overview)
    use = _java_usage()
    runtimes = []
    for j in java.installed():
        size = await asyncio.to_thread(S.dir_size, S.java_dir(j["major"]))
        runtimes.append({"major": j["major"], "version": j.get("version"), "vendor": j.get("vendor"), "image_type": j.get("image_type"),
                         "installed_at": j.get("installed_at"), "size": size, "used_by": use.get(j["major"], [])})
    installing = [int(j.key.split("-")[1]) for j in jobs._jobs.values() if j.status == "running" and (j.key or "").startswith("java-")]
    return {"disk": disk, "java": runtimes, "cache": await asyncio.to_thread(S.cache_overview),
            "installing": installing, "missing_for": {str(k): v for k, v in use.items() if not java.find(k)}}


class MajorBody(BaseModel):
    major: int = Field(ge=8, le=99)


@router.post("/api/system/java/delete")
async def java_delete(b: MajorBody):
    users = _java_usage().get(b.major, [])
    busy = [u["name"] for u in users if u["status"] not in ("stopped", "crashed")]
    if busy:
        raise HTTPException(409, _t('Java {major} şu an çalışan sunucular tarafından kullanılıyor: {v1}. Önce onları durdur.', major=b.major, v1=', '.join(busy)))
    if jobs.find_running(f"java-{b.major}"):
        raise HTTPException(409, _t("Bu Java sürümü şu an kuruluyor."))
    try:
        d = S.java_dir(b.major)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not d.is_dir():
        raise HTTPException(404, _t("Bu Java sürümü kurulu değil."))
    try:
        await asyncio.to_thread(S.rmtree, d)
    except OSError as e:
        raise HTTPException(409, _t('Silinemedi (dosya kullanımda olabilir): {v0}', v0=e.strerror or e))
    return {"ok": True, "used_by": [u["name"] for u in users]}


class CacheBody(BaseModel):
    kind: str = Field(max_length=20)


@router.post("/api/system/cache/clear")
async def cache_clear(b: CacheBody):
    if any(j.status == "running" and j.kind in ("vanilla", "paper", "fabric", "forge", "neoforge", "modpack", "upgrade") for j in jobs._jobs.values()):
        raise HTTPException(409, _t("Şu an bir indirme/kurulum sürüyor; bitince tekrar dene."))
    try:
        n = await asyncio.to_thread(S.clear_cache, b.kind)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "removed": n}
