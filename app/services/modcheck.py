"""Mod bağımlılık denetimi: mods/ klasöründeki jar'ların üst verisini okuyup eksik zorunlu bağımlılıkları bulur.

Sunucu başlamadan önce "şu mod eksik, sunucu açılmayacak" diyebilmek için. Yalnızca okuma yapar:
jar'lar zip olarak açılır, yalnızca küçük üst veri dosyaları (fabric.mod.json, quilt.mod.json,
META-INF/mods.toml, META-INF/neoforge.mods.toml) ve iç içe jar'lar (Fabric META-INF/jars, Forge
META-INF/jarjar) okunur. Hiçbir kod çalıştırılmaz. Boyut ve sayı sınırları zip bombalarına karşıdır.

Sürüm aralıkları denetlenmez; yalnızca "bu kimlikte bir mod var mı" bakılır.
"""
from __future__ import annotations

import io
import json
import re
import tomllib
import zipfile
from pathlib import Path
from ..i18n import _t

META_MAX = 1024 * 1024             # tek üst veri dosyası en fazla 1 MB
NESTED_MAX = 32 * 1024 * 1024      # iç içe jar en fazla 32 MB (belleğe okunur)
NESTED_COUNT = 200                 # bir jar'daki en fazla iç içe jar
MAX_JARS = 2000
MAX_DEPTH = 3

# Yükleyicinin kendisinin sağladığı kimlikler (jar olarak bulunmaz)
BUILTIN = {"minecraft", "java", "fabricloader", "fabric-loader", "quilt_loader", "forge", "neoforge",
           "javafml", "lowcodefml", "mixinextras"}
_ID_RE = re.compile(r"^[a-z0-9_.\-]{1,64}$")


def _read(z: zipfile.ZipFile, name: str, limit: int) -> bytes | None:
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > limit:
        return None
    with z.open(info) as f:
        return f.read(limit + 1)[:limit]


def _clean(i) -> str | None:
    i = str(i or "").strip().lower()
    return i if _ID_RE.match(i) else None


def _fabric(data: bytes, env_out: dict) -> tuple[list[str], list[str], str | None, str]:
    j = json.loads(data.decode("utf-8-sig", "replace"), strict=False)
    mid = _clean(j.get("id"))
    ids = [mid] if mid else []
    ids += [x for x in (_clean(p) for p in (j.get("provides") or [])) if x]
    deps = [x for x in (_clean(k) for k in (j.get("depends") or {})) if x]
    env_out["client_only"] = j.get("environment") == "client"
    return ids, deps, mid, str(j.get("name") or mid or "")


def _quilt(data: bytes, env_out: dict) -> tuple[list[str], list[str], str | None, str]:
    root = json.loads(data.decode("utf-8-sig", "replace"), strict=False)
    j = root.get("quilt_loader") or {}
    mid = _clean(j.get("id"))
    ids = [mid] if mid else []
    for p in j.get("provides") or []:
        if x := _clean(p.get("id") if isinstance(p, dict) else p):
            ids.append(x)
    deps = []
    for d in j.get("depends") or []:
        if isinstance(d, dict):
            if d.get("optional"):
                continue
            d = d.get("id")
        if isinstance(d, str) and (x := _clean(d.split(":")[-1])):
            deps.append(x)
    env_out["client_only"] = (root.get("minecraft") or {}).get("environment") == "client"
    return ids, deps, mid, str((j.get("metadata") or {}).get("name") or mid or "")


def _forge(data: bytes, env_out: dict, neo: bool = False) -> tuple[list[str], list[str], str | None, str]:
    t = tomllib.loads(data.decode("utf-8-sig", "replace"))
    ids, names = [], []
    for m in t.get("mods") or []:
        if x := _clean(m.get("modId")):
            ids.append(x)
            names.append(str(m.get("displayName") or x))
    deps = []
    for owner, lst in (t.get("dependencies") or {}).items():
        if not isinstance(lst, list):
            continue
        for d in lst:
            if not isinstance(d, dict):
                continue
            if "type" in d:                                   # NeoForge: type = required|optional|incompatible|discouraged
                required = str(d["type"]).lower() == "required"
            elif "mandatory" in d:                            # Forge ve eski NeoForge
                required = d["mandatory"] is True
            else:
                required = neo                                # NeoForge'da varsayılan "required"
            if required and str(d.get("side", "BOTH")).upper() in ("BOTH", "SERVER"):
                if x := _clean(d.get("modId")):
                    deps.append(x)
    env_out["client_only"] = False
    return ids, deps, (ids[0] if ids else None), ", ".join(names[:3])


PARSERS = [("fabric.mod.json", _fabric), ("quilt.mod.json", _quilt),
           ("META-INF/neoforge.mods.toml", lambda d, e: _forge(d, e, neo=True)), ("META-INF/mods.toml", _forge)]


def _scan_zip(z: zipfile.ZipFile, label: str, out: dict, depth: int) -> None:
    for meta, parse in PARSERS:
        data = _read(z, meta, META_MAX)
        if data is None:
            continue
        env: dict = {}
        try:
            ids, deps, mid, name = parse(data, env)
        except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
            out["unreadable"].append(label)
            continue
        out["provided"].update(ids)
        if depth == 0:                                    # yalnızca üst düzey modların bağımlılıkları raporlanır
            for d in deps:
                out["requires"].setdefault(d, set()).add(name or label)
            if env.get("client_only"):
                out["client_only"].append({"file": label, "name": name or label})
        break                                             # her jar için ilk bulunan üst veri yeter
    if depth >= MAX_DEPTH:
        return
    nested = [n for n in z.namelist() if n.endswith(".jar") and n.startswith(("META-INF/jars/", "META-INF/jarjar/"))]
    for n in nested[:NESTED_COUNT]:
        data = _read(z, n, NESTED_MAX)
        if data is None:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as nz:
                _scan_zip(nz, label, out, depth + 1)
        except (zipfile.BadZipFile, OSError, RuntimeError):
            pass


def check_mods(mods_dir: Path) -> dict:
    """{'missing': [{'id','required_by':[...]}], 'client_only': [...], 'scanned': n, 'unreadable': [...]}"""
    out = {"provided": set(), "requires": {}, "client_only": [], "unreadable": []}
    jars = sorted(mods_dir.glob("*.jar"))[:MAX_JARS] if mods_dir.is_dir() else []
    for jar in jars:
        if not jar.is_file():
            continue
        try:
            with zipfile.ZipFile(jar) as z:
                _scan_zip(z, jar.name, out, 0)
        except (zipfile.BadZipFile, OSError, RuntimeError):
            out["unreadable"].append(jar.name)
    provided = out["provided"] | BUILTIN
    missing = [{"id": d, "required_by": sorted(by)[:10]} for d, by in sorted(out["requires"].items()) if d not in provided]
    return {"missing": missing, "client_only": out["client_only"][:100], "scanned": len(jars),
            "unreadable": sorted(set(out["unreadable"]))[:50]}


def summary_lines(res: dict, limit: int = 15) -> list[str]:
    """Konsola yazılacak kısa uyarı satırları."""
    lines = []
    if res["missing"]:
        lines.append(_t('[panel] Uyarı: {n} zorunlu bağımlılık eksik, sunucu açılmayabilir:', n=len(res['missing'])))
        for m in res["missing"][:limit]:
            lines.append(_t('[panel]   - {id} (isteyen: {v1})', id=m['id'], v1=', '.join(m['required_by'][:3])))
        if len(res["missing"]) > limit:
            lines.append(_t('[panel]   … ve {v0} tane daha. Ayrıntı: Modlar penceresi.', v0=len(res['missing']) - limit))
    if res["client_only"]:
        names = ", ".join(c["name"] for c in res["client_only"][:5])
        lines.append(_t('[panel] Uyarı: istemciye özel mod(lar) sunucuda: {names}. Sunucuyu çökertebilir; Modlar penceresinden kapatabilirsin.', names=names))
    return lines
