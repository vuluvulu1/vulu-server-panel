from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, INSTANCES_DIR
from .db import get_conn, init_db
from .routers import auth as auth_router, panel as panel_router, backups, console, players, playit as playit_router, schedules, system, files, instances, java, loader, modpacks, mods, paper, profiles, settings
from .routers import stats as stats_router
from .services.container import jobs, launcher, playit, process_manager, scheduler, stats
from .auth import AuthMiddleware, ensure_setup_code
from .i18n import LangMiddleware
from .security import LocalGuardMiddleware
from .templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    INSTANCES_DIR.mkdir(exist_ok=True)
    init_db()
    ensure_setup_code()          # hiç hesap yoksa kurulum kodunu konsola yaz
    with get_conn() as conn:  # panel açılırken hiçbir süreç çalışmıyor
        conn.execute("UPDATE instances SET status = 'stopped'")
    stats.start()
    scheduler.start()
    await playit.autostart()
    yield
    await playit.stop_agent()
    await scheduler.stop()
    await stats.stop()
    await launcher.shutdown()
    await jobs.shutdown()
    await process_manager.stop_all()


app = FastAPI(title="vulu Server Panel", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(AuthMiddleware)             # içte: oturum denetimi
app.add_middleware(LangMiddleware)             # dil çerezi → istek bağlamı
app.add_middleware(LocalGuardMiddleware)       # dışta (önce çalışır): Host/Origin denetimi
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
# settings/files/backups, instances'tan ÖNCE: instances'taki genel /api/instances/{id}/{action} rotası 3 parçalı adresleri (settings, properties, destroy) yutmasın
app.include_router(auth_router.router)
app.include_router(panel_router.router)
app.include_router(settings.router)
app.include_router(files.router)
app.include_router(backups.router)
app.include_router(schedules.router)
app.include_router(players.router)
app.include_router(playit_router.router)
app.include_router(system.router)
app.include_router(instances.router)
app.include_router(console.router)
app.include_router(java.router)
app.include_router(paper.router)
app.include_router(loader.router)
app.include_router(profiles.router)
app.include_router(mods.router)
app.include_router(modpacks.router)
app.include_router(stats_router.router)


@app.get("/")
async def index(request: Request):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM instances ORDER BY id").fetchall()
    return templates.TemplateResponse(request, "index.html", {"instances": rows})


@app.get("/api/health")
async def health():
    return {"status": "ok"}
