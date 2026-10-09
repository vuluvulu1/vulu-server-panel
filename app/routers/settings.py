import base64
import binascii
import os
import shutil
import stat
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import INSTANCES_DIR
from ..db import get_conn, get_instance, update_instance
from ..routers.instances import NAME_RE, JAR_RE, _sys_ram_gb
from ..security import validate_java_path, validate_jvm_args
from ..services.container import jobs, launcher, minecraft, upgrader
from ..services.jobs import JobError
from ..services.jvm import PRESETS, validate_args_file
from ..services.minecraft import McError
from ..services.propschema import GROUPS, MANAGED, validate_value
from ..services.properties import read_properties, update_properties
from ..templating import templates

router = APIRouter()
STOPPED = ("stopped", "crashed")
JAVA_MODES = {"auto", "custom", "8", "11", "17", "21", "25"}


def _inst(iid: int) -> dict:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, "Sunucu bulunamadı")
    return inst


def _stopped(iid: int) -> None:
    if launcher.pm.status(iid) not in STOPPED:
        raise HTTPException(409, "Önce sunucuyu durdur (ayarlar çalışırken değiştirilmez).")


# ---------------- sunucu ayarları ----------------
@router.get("/instances/{iid}/settings")
async def settings_page(request: Request, iid: int):
    inst = _inst(iid)
    mode = "custom" if not inst.get("java_major") else str(inst["java_major"])
    if mode not in JAVA_MODES:
        mode = "auto"
    return templates.TemplateResponse(request, "instance_settings.html", {
        "inst": inst, "presets": PRESETS, "sys_ram_gb": _sys_ram_gb(), "java_mode": mode, "stopped": launcher.pm.status(iid) in STOPPED})


class SettingsBody(BaseModel):
    port: str = Field(max_length=10)
    ram_gb: str = Field(max_length=5)
    jvm_preset: str = Field(max_length=20)
    jvm_args: str = Field("", max_length=500)
    java_mode: str = Field(max_length=10)
    java_path: str = Field("java", max_length=260)
    launch_type: str = Field(max_length=12)
    jar_file: str = Field("server.jar", max_length=150)
    args_file: str = Field("", max_length=200)


@router.post("/api/instances/{iid}/settings")
async def settings_save(iid: int, b: SettingsBody):
    inst = _inst(iid)
    _stopped(iid)
    errors: list[str] = []
    upd: dict = {}
    try:
        port = int(b.port.strip())
        if not 1024 <= port <= 65535:
            raise ValueError
        with get_conn() as conn:
            taken = conn.execute("SELECT 1 FROM instances WHERE id != ? AND (port = ? OR rcon_port = ?)", (iid, port, port)).fetchone()
        if taken or port == inst.get("rcon_port"):
            errors.append(f"{port} portunu başka bir sunucu (ya da RCON) kullanıyor.")
        upd["port"] = port
    except ValueError:
        errors.append("Port 1024-65535 arasında bir sayı olmalı.")
    try:
        ram = int(b.ram_gb.strip())
        if not 1 <= ram <= 128:
            raise ValueError
        if ram > _sys_ram_gb():
            errors.append(f"Bilgisayarında {_sys_ram_gb()} GB RAM var; bundan fazlasını veremezsin.")
        upd["ram_mb"] = ram * 1024
    except ValueError:
        errors.append("RAM 1-128 GB arasında bir sayı olmalı.")
    if b.jvm_preset not in PRESETS:
        errors.append("Geçersiz JVM ayarı.")
    if err := validate_jvm_args(b.jvm_args.strip()):
        errors.append(err)
    if b.launch_type not in ("jar", "args-file"):
        errors.append("Geçersiz başlatma türü.")
    if b.launch_type == "jar" and not JAR_RE.match(b.jar_file.strip()):
        errors.append("Jar dosya adı geçersiz (örn. server.jar).")
    if err := validate_args_file(b.args_file):
        errors.append(err)
    java_major, java_path = None, "java"
    if b.java_mode not in JAVA_MODES:
        errors.append("Geçersiz Java seçimi.")
    elif b.java_mode == "custom":
        java_path = b.java_path.strip()
        if err := validate_java_path(java_path):
            errors.append(err)
    elif b.java_mode == "auto":
        if not inst.get("mc_version"):
            errors.append("Java'yı otomatik seçmek için sunucunun Minecraft sürümü kayıtlı olmalı.")
        elif not errors:
            try:
                java_major = (await minecraft.java_for(inst["mc_version"], inst.get("loader") or "vanilla"))["major"]
            except McError as e:
                errors.append(str(e))
    else:
        java_major = int(b.java_mode)
    if errors:
        raise HTTPException(400, " ".join(errors))
    upd.update(jvm_preset=b.jvm_preset, jvm_args=b.jvm_args.strip(), launch_type=b.launch_type, java_major=java_major, java_path=java_path,
               args_file=b.args_file.strip() or None)
    if b.launch_type == "jar":
        upd["jar_file"] = b.jar_file.strip()
    update_instance(iid, **upd)
    return {"ok": True}


# ---------------- server.properties ----------------
@router.get("/instances/{iid}/properties")
async def properties_page(request: Request, iid: int):
    inst = _inst(iid)
    path = Path(inst["path"]) / "server.properties"
    cur = read_properties(path)
    known = {f["key"] for _, fs in GROUPS for f in fs}
    others = {k: ("••••••" if "password" in k else v) for k, v in cur.items() if k not in known and k not in MANAGED}
    return templates.TemplateResponse(request, "instance_properties.html", {
        "inst": inst, "groups": GROUPS, "cur": cur, "exists": path.is_file(), "others": others,
        "stopped": launcher.pm.status(iid) in STOPPED})


class PropsBody(BaseModel):
    values: dict[str, str | bool | int] = Field(max_length=100)


@router.post("/api/instances/{iid}/properties")
async def properties_save(iid: int, b: PropsBody):
    inst = _inst(iid)
    _stopped(iid)
    clean, errors = {}, []
    for k, raw in b.values.items():
        v, err = validate_value(k, raw)
        if err:
            errors.append(err)
        else:
            clean[k] = v
    if errors:
        raise HTTPException(400, " ".join(errors))
    try:
        update_properties(Path(inst["path"]) / "server.properties", clean)
    except (OSError, ValueError) as e:
        raise HTTPException(500, f"Yazılamadı: {e}")
    return {"ok": True, "changed": len(clean)}


# ---------------- gerçek silme ----------------
class DestroyBody(BaseModel):
    confirm_name: str = Field(max_length=64)


def _force(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)          # Windows: salt-okunur dosyalar silinemez
    func(path)


@router.post("/api/instances/{iid}/destroy")
async def destroy(iid: int, b: DestroyBody):
    inst = _inst(iid)
    _stopped(iid)
    if b.confirm_name != inst["name"]:
        raise HTTPException(400, "Yazdığın ad sunucu adıyla eşleşmiyor.")
    if any(j.status == "running" and j.key and j.key.endswith(f"-{iid}") for j in jobs._jobs.values()):
        raise HTTPException(409, "Bu sunucu için bir kurulum/indirme sürüyor; bitmesini bekle.")
    folder, root = Path(inst["path"]).resolve(), INSTANCES_DIR.resolve()
    if folder.parent != root or not NAME_RE.match(folder.name):      # yalnızca instances/<ad> doğrudan alt klasörü silinir
        raise HTTPException(400, "Güvenlik: sunucu klasörü beklenen konumda değil, dosyalar SİLİNMEDİ.")
    try:
        if folder.exists():
            if sys.version_info >= (3, 12):
                shutil.rmtree(folder, onexc=lambda f, p, e: _force(f, p, e))
            else:
                shutil.rmtree(folder, onerror=_force)
    except OSError as e:
        raise HTTPException(500, f"Klasör silinemedi (açık bir dosya olabilir): {e}")
    with get_conn() as conn:
        conn.execute("DELETE FROM instances WHERE id = ?", (iid,))
    return {"ok": True}


# ---------------- sunucu simgesi (server-icon.png) ----------------
ICON_NAME = "server-icon.png"
ICON_MAX = 256 * 1024
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _valid_icon(data: bytes) -> bool:
    """Gerçek bir 64x64 PNG mi? (imza + IHDR boyutları + IEND)"""
    return (len(data) <= ICON_MAX and data[:8] == PNG_SIG and data[12:16] == b"IHDR"
            and int.from_bytes(data[16:20], "big") == 64 and int.from_bytes(data[20:24], "big") == 64
            and data.rstrip(b"\x00")[-8:-4] == b"IEND")


@router.get("/api/instances/{iid}/icon")
async def icon_get(iid: int):
    p = Path(_inst(iid)["path"]) / ICON_NAME
    if not p.is_file() or p.stat().st_size > ICON_MAX:
        raise HTTPException(404, "Simge yok")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


class IconBody(BaseModel):
    data: str = Field(max_length=ICON_MAX * 2)


@router.post("/api/instances/{iid}/icon")
async def icon_set(iid: int, b: IconBody):
    folder = Path(_inst(iid)["path"])
    try:
        raw = base64.b64decode(b.data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Geçersiz resim verisi.")
    if not _valid_icon(raw):
        raise HTTPException(400, "Simge 64x64 piksel PNG olmalı.")
    tmp = folder / (ICON_NAME + ".vulu-tmp")
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, folder / ICON_NAME)
    except OSError as e:
        raise HTTPException(500, f"Kaydedilemedi: {e.strerror or e}")
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True}


@router.post("/api/instances/{iid}/icon/delete")
async def icon_delete(iid: int):
    (Path(_inst(iid)["path"]) / ICON_NAME).unlink(missing_ok=True)
    return {"ok": True}


# ---------------- Minecraft sürümünü değiştir ----------------
class UpgradeBody(BaseModel):
    mc_version: str = Field(max_length=40)
    confirm_downgrade: bool = False


@router.post("/api/instances/{iid}/upgrade/check")
async def upgrade_check(iid: int, b: UpgradeBody):
    inst = _inst(iid)
    try:
        return await upgrader.check(inst, b.mc_version)
    except JobError as e:
        raise HTTPException(400, str(e))


@router.post("/api/instances/{iid}/upgrade/start")
async def upgrade_start(iid: int, b: UpgradeBody):
    inst = _inst(iid)
    _stopped(iid)
    if any(j.status == "running" and (j.key or "").endswith(f"-{iid}") for j in jobs._jobs.values()):
        raise HTTPException(409, "Bu sunucu için başka bir işlem sürüyor; bitmesini bekle.")
    try:
        plan = await upgrader.check(inst, b.mc_version)
    except JobError as e:
        raise HTTPException(400, str(e))
    if plan["downgrade"] and not b.confirm_downgrade:
        raise HTTPException(400, "Daha eski bir sürüme geçiş dünyayı bozabilir; onaylaman gerekiyor.")
    return {"job_id": upgrader.ensure_job(inst, b.mc_version).id}
