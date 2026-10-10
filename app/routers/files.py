import os
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..db import get_instance
from ..services import files as F
from ..services.container import launcher
from ..templating import templates
from ..i18n import _t

router = APIRouter()
STOPPED = ("stopped", "crashed")


def _root(iid: int) -> tuple[dict, Path]:
    inst = get_instance(iid)
    if not inst:
        raise HTTPException(404, _t("Sunucu bulunamadı"))
    root = Path(inst["path"])
    if not root.is_dir():
        raise HTTPException(404, _t("Sunucu klasörü bulunamadı."))
    return inst, root


def _stopped(iid: int) -> None:
    if launcher.pm.status(iid) not in STOPPED:
        raise HTTPException(409, _t("Önce sunucuyu durdur (dosyalar çalışırken değiştirilmez)."))


def _do(fn, *a):
    try:
        return fn(*a)
    except F.FileError as e:
        raise HTTPException(400, str(e))
    except PermissionError:
        raise HTTPException(409, _t("Dosya kullanımda ya da izin yok."))
    except OSError as e:
        raise HTTPException(500, _t('İşlem başarısız: {v0}', v0=e.strerror or e))


@router.get("/instances/{iid}/files")
async def files_page(request: Request, iid: int, path: str = ""):
    inst, _ = _root(iid)
    return templates.TemplateResponse(request, "instance_files.html", {"inst": inst, "start_path": path})


@router.get("/api/instances/{iid}/files/list")
async def files_list(iid: int, path: str = Query("", max_length=400)):
    _, root = _root(iid)
    res = _do(F.listing, root, path)
    res["writable"] = launcher.pm.status(iid) in STOPPED
    return res


@router.get("/api/instances/{iid}/files/read")
async def files_read(iid: int, path: str = Query(..., max_length=400)):
    _, root = _root(iid)
    return _do(F.read_text, root, path)


@router.get("/api/instances/{iid}/files/download")
async def files_download(iid: int, path: str = Query(..., max_length=400)):
    _, root = _root(iid)
    p = _do(F.safe_path, root, path)
    if not p.is_file():
        raise HTTPException(404, _t("Dosya bulunamadı."))
    return FileResponse(p, filename=p.name, media_type="application/octet-stream")


class WriteBody(BaseModel):
    path: str = Field(max_length=400)
    content: str = Field(max_length=F.MAX_EDIT)


class PathBody(BaseModel):
    path: str = Field("", max_length=400)
    name: str = Field("", max_length=150)


@router.post("/api/instances/{iid}/files/write")
async def files_write(iid: int, b: WriteBody):
    _, root = _root(iid)
    _stopped(iid)
    _do(F.write_text, root, b.path, b.content)
    return {"ok": True}


@router.post("/api/instances/{iid}/files/mkdir")
async def files_mkdir(iid: int, b: PathBody):
    _, root = _root(iid)
    _stopped(iid)
    _do(F.make_dir, root, b.path, b.name)
    return {"ok": True}


@router.post("/api/instances/{iid}/files/rename")
async def files_rename(iid: int, b: PathBody):
    _, root = _root(iid)
    _stopped(iid)
    _do(F.rename, root, b.path, b.name)
    return {"ok": True}


@router.post("/api/instances/{iid}/files/delete")
async def files_delete(iid: int, b: PathBody):
    _, root = _root(iid)
    _stopped(iid)
    if not b.path.strip("/\\ "):
        raise HTTPException(400, _t("Kök klasör silinemez."))
    _do(F.delete, root, b.path)
    return {"ok": True}


@router.post("/api/instances/{iid}/files/upload")
async def files_upload(iid: int, file: UploadFile = File(...), path: str = Form(""), overwrite: bool = Form(False)):
    _, root = _root(iid)
    _stopped(iid)
    target = _do(F.upload_target, root, path, file.filename or "", overwrite)
    tmp = target.with_name(target.name + ".vulu-tmp")
    size = 0
    try:
        with open(tmp, "wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > F.MAX_UPLOAD:
                    raise HTTPException(413, _t("Dosya çok büyük (en fazla 512 MB)."))
                out.write(chunk)
        os.replace(tmp, target)
    except OSError as e:
        raise HTTPException(500, _t('Yüklenemedi: {v0}', v0=e.strerror or e))
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True, "name": target.name, "size": size}
