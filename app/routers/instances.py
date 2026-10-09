import asyncio
import re
import sqlite3

import psutil
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import INSTANCES_DIR
from ..security import validate_java_path, validate_jvm_args
from ..db import get_conn, get_instance
from ..services.container import launcher, minecraft
from ..services.minecraft import LOADERS, McError
from ..services.paper import PaperError, read_jar_info
from ..services.container import installers, modpacks
from ..services.container import minecraft as mc_service
from ..services.jvm import PRESETS, validate_args_file
from ..services.modrinth import ModrinthError, read_mods_info
from ..services.profiles import get_profile, props_as_strings
from ..services.properties import update_properties
from ..services.process import ProcessError, process_manager as pm
from ..templating import templates

router = APIRouter()

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
JAR_RE = re.compile(r"^[A-Za-z0-9._-]+\.jar$")
MC_RE = re.compile(r"^[A-Za-z0-9._+-]{1,40}$")
JAVA_MODES = {"auto", "custom", "8", "11", "17", "21", "25"}

_tasks: set[asyncio.Task] = set()


def _bg(coro) -> None:
    """Uzun işleri (durdurma gibi) istek bitmeden arka planda yürüt."""
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _safe(iid: int, coro) -> None:
    try:
        await coro
    except ProcessError as e:
        pm.notify_error(iid, str(e))


def _sys_ram_gb() -> int:
    return max(1, psutil.virtual_memory().total // 2**30)


def _ctx(values: dict, errors: list[str]) -> dict:
    return {"values": values, "errors": errors, "loaders": LOADERS, "presets": PRESETS, "sys_ram_gb": _sys_ram_gb(),
            "profile": get_profile(values.get("profile_id"))}


def _next_free_port() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(port) AS p FROM instances").fetchone()
    return (row["p"] + 1) if row["p"] else 25565


# ---------- sayfalar ----------
@router.get("/instances/new")
async def new_instance_form(request: Request, profile: str = "", modpack: str = ""):
    values = {
        "name": "", "port": str(_next_free_port()), "ram_gb": "4",
        "jar_file": "server.jar", "java_path": "java", "jvm_args": "",
        "mc_version": "", "loader": "vanilla", "java_mode": "auto",
        "jvm_preset": "aikar", "launch_type": "auto", "args_file": "", "profile_id": "",
        "modpack_slug": "", "modpack_version": "", "modpack_label": "",
    }
    errs: list[str] = []
    if prof := get_profile(profile):                      # profil seçildiyse formu onunla doldur
        values.update(profile_id=prof.id, loader=prof.loader, jvm_preset=prof.jvm_preset,
                      ram_gb=str(min(prof.default_ram_gb, _sys_ram_gb())))
        ver = prof.mc_version
        if ver == "latest":
            try:
                mgr = installers.get(prof.loader)
                ver = (await mgr.versions() if mgr else await mc_service.list_versions())["latest"] or ""
            except Exception:
                ver = ""                                   # servise ulaşılamadı: sürümü kullanıcı seçsin
        values["mc_version"] = ver
    if modpack and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}", modpack):     # Modrinth modpack seçildi
        try:
            pk = await modpacks.version_info(modpack)
            values.update(modpack_slug=pk["slug"], modpack_version=pk["version_id"], modpack_label=f"{pk['title']} {pk['version_number']}",
                          loader=pk["loader"], mc_version=pk["mc_version"], jvm_preset="aikar", ram_gb=str(min(6, _sys_ram_gb())))
        except ModrinthError as e:
            errs.append(str(e))
    return templates.TemplateResponse(request, "instance_new.html", _ctx(values, errs))


@router.post("/instances")
async def create_instance(
    request: Request,
    name: str = Form(""),
    port: str = Form("25565"),
    ram_gb: str = Form("4"),
    jar_file: str = Form("server.jar"),
    java_path: str = Form("java"),
    jvm_args: str = Form(""),
    mc_version: str = Form(""),
    loader: str = Form("vanilla"),
    java_mode: str = Form("custom"),
    jvm_preset: str = Form("none"),
    launch_type: str = Form("auto"),
    args_file: str = Form(""),
    profile_id: str = Form(""),
    modpack_slug: str = Form(""),
    modpack_version: str = Form(""),
    accept_eula: str | None = Form(None),
):
    values = {
        "name": name.strip(), "port": port.strip(), "ram_gb": ram_gb.strip(),
        "jar_file": jar_file.strip(), "java_path": java_path.strip(), "jvm_args": jvm_args.strip(),
        "mc_version": mc_version.strip(), "loader": loader.strip(), "java_mode": java_mode.strip(),
        "jvm_preset": jvm_preset.strip(), "launch_type": launch_type.strip(), "args_file": args_file.strip(),
        "profile_id": profile_id.strip(), "modpack_slug": modpack_slug.strip(), "modpack_version": modpack_version.strip(), "modpack_label": "",
    }
    errors: list[str] = []

    pack = None
    if values["modpack_slug"] or values["modpack_version"]:      # modpack: sürüm ve yükleyiciyi Modrinth belirler, forma güvenilmez
        try:
            pack = await modpacks.version_info(values["modpack_slug"], values["modpack_version"] or None)
            values.update(loader=pack["loader"], mc_version=pack["mc_version"], modpack_label=f"{pack['title']} {pack['version_number']}")
        except ModrinthError as e:
            errors.append(str(e))

    if not NAME_RE.match(values["name"]):
        errors.append("Ad 1-32 karakter olmalı; harf, rakam, tire ve alt çizgi içerebilir (boşluk yok).")
    if not JAR_RE.match(values["jar_file"]):
        errors.append("Jar dosya adı geçersiz (örn. server.jar).")
    if values["loader"] not in LOADERS:
        errors.append("Geçersiz mod yükleyici.")
    if values["java_mode"] not in JAVA_MODES:
        errors.append("Geçersiz Java seçimi.")
    if values["mc_version"] and not MC_RE.match(values["mc_version"]):
        errors.append("Minecraft sürümü geçersiz.")
    if err := validate_jvm_args(values["jvm_args"]):
        errors.append(err)
    if values["jvm_preset"] not in PRESETS:
        errors.append("Geçersiz JVM ayarı.")
    if values["launch_type"] not in ("auto", "jar", "args-file"):
        errors.append("Geçersiz başlatma türü.")
    if err := validate_args_file(values["args_file"]):
        errors.append(err)
    prof = get_profile(values["profile_id"]) if values["profile_id"] else None
    if values["profile_id"] and not prof:
        errors.append("Seçilen profil bulunamadı.")
    launch_type = values["launch_type"]
    if launch_type == "auto":
        launch_type = "args-file" if values["loader"] in ("forge", "neoforge") else "jar"

    mgr = installers.get(values["loader"])
    if mgr and values["mc_version"] and not errors:
        try:
            known = {v["id"] for v in (await mgr.versions())["versions"]}
            if values["mc_version"] not in known:
                errors.append(f"{values['loader'].capitalize()} {values['mc_version']} sürümünü desteklemiyor. Listeden desteklenen bir sürüm seç.")
        except PaperError:
            pass   # servise ulaşılamıyor: ilk başlatmada net bir hata gösterilir

    java_major: int | None = None
    if values["java_mode"] == "custom":
        if err := validate_java_path(values["java_path"]):
            errors.append(err)
    elif values["java_mode"] == "auto":
        if not values["mc_version"]:
            errors.append("Java'yı otomatik seçmek için bir Minecraft sürümü seçmelisin.")
        elif not errors:
            try:
                java_major = (await minecraft.java_for(values["mc_version"], values["loader"]))["major"]
            except McError as e:
                errors.append(str(e))
    else:
        java_major = int(values["java_mode"])

    port_i = ram_i = 0
    try:
        port_i = int(values["port"])
        if not 1024 <= port_i <= 65535:
            raise ValueError
    except ValueError:
        errors.append("Port 1024-65535 arasında bir sayı olmalı.")
    try:
        ram_i = int(values["ram_gb"])
        if not 1 <= ram_i <= 128:
            raise ValueError
    except ValueError:
        errors.append("RAM 1-128 GB arasında bir sayı olmalı.")
    if ram_i > _sys_ram_gb():
        errors.append(f"Bilgisayarında {_sys_ram_gb()} GB RAM var; bundan fazlasını veremezsin.")

    if not errors:
        with get_conn() as conn:
            if conn.execute("SELECT 1 FROM instances WHERE port = ?", (port_i,)).fetchone():
                errors.append(f"{port_i} portunu başka bir sunucu kullanıyor.")

    if errors:
        return templates.TemplateResponse(
            request, "instance_new.html", _ctx(values, errors), status_code=400
        )

    folder = INSTANCES_DIR / values["name"]
    folder.mkdir(parents=True, exist_ok=True)
    if accept_eula:
        (folder / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    if prof and prof.server_properties:
        try:
            update_properties(folder / "server.properties", props_as_strings(prof))
        except (OSError, ValueError) as e:
            errors.append(f"Profil ayarları yazılamadı: {e}")
            return templates.TemplateResponse(request, "instance_new.html", _ctx(values, errors), status_code=400)

    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO instances (name, path, port, java_path, jar_file, jvm_args, ram_mb, "
                "mc_version, loader, java_major, launch_type, args_file, jvm_preset, profile_id, modpack_slug, modpack_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (values["name"], str(folder), port_i, values["java_path"] or "java",
                 values["jar_file"], values["jvm_args"], ram_i * 1024,
                 values["mc_version"] or None, values["loader"], java_major,
                 launch_type, values["args_file"] or None, values["jvm_preset"], values["profile_id"] or None,
                 pack["slug"] if pack else None, pack["version_id"] if pack else None),
            )
            iid = cur.lastrowid
    except sqlite3.IntegrityError:
        errors.append("Bu isimde bir sunucu zaten var.")
        return templates.TemplateResponse(
            request, "instance_new.html", _ctx(values, errors), status_code=400
        )

    return RedirectResponse(f"/instances/{iid}", status_code=303)


@router.get("/instances/{iid}")
async def instance_detail(request: Request, iid: int):
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    jar_info = read_jar_info(Path(inst["path"]))
    return templates.TemplateResponse(request, "instance_detail.html", {"inst": inst, "jar_info": jar_info, "profile": get_profile(inst.get("profile_id")),
                         "mods_info": read_mods_info(Path(inst["path"]))})


@router.post("/instances/{iid}/delete")
async def delete_instance(iid: int):
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    if pm.status(iid) in ("preparing", "starting", "running", "stopping"):
        raise HTTPException(409, "Çalışan sunucu silinemez. Önce durdur.")
    with get_conn() as conn:
        conn.execute("DELETE FROM instances WHERE id = ?", (iid,))
    # Dosyalar bilerek silinmiyor: dünya verisi kaybolmasın.
    return RedirectResponse("/", status_code=303)


# ---------- eylemler ----------
@router.post("/api/instances/{iid}/mods/update")
async def mods_update(iid: int):
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    try:
        return {"ok": True, **await launcher.update_mods(inst)}
    except ProcessError as e:
        raise HTTPException(400, str(e))


@router.post("/api/instances/{iid}/paper/update")
async def paper_update(iid: int):
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    try:
        return {"ok": True, **await launcher.update_jar(inst)}
    except ProcessError as e:
        raise HTTPException(400, str(e))


@router.post("/api/instances/{iid}/{action}")
async def instance_action(iid: int, action: str):
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")

    if action == "start":
        try:
            return {"ok": True, **await launcher.start(inst)}
        except ProcessError as e:
            raise HTTPException(400, str(e))
    elif action == "stop":
        _bg(_safe(iid, launcher.stop(iid)))
    elif action == "restart":
        _bg(_safe(iid, launcher.restart(inst)))
    elif action == "kill":
        await launcher.kill(iid)
    else:
        raise HTTPException(404, "Bilinmeyen eylem")
    return {"ok": True}
