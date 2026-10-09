"""JVM ön ayarları ve başlatma komutunun kurulması (jar / argüman dosyası).

Başlatma türleri:
  jar        java <bayraklar> -jar <jar> nogui            (Vanilla, Paper, Fabric, eski Forge)
  args-file  java @user_jvm_args.txt @<args_file> nogui   (yeni Forge / NeoForge)
Kabuk betiği (run.bat/run.sh) ASLA çalıştırılmaz; komut her zaman liste olarak kurulur.
"""
import os
import re
import shlex
from pathlib import Path

from ..security import validate_java_path, validate_jvm_args


class LaunchError(Exception):
    """Kullanıcıya gösterilebilir başlatma hatası."""


PRESETS = {"none": "Varsayılan (ek bayrak yok)", "aikar": "Aikar bayrakları (önerilen)"}

_AIKAR_COMMON = [
    "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
    "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
    "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4", "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1", "-Dusing.aikars.flags=https://mcflags.emc.gs", "-Daikars.new.flags=true",
]
_AIKAR_SMALL = ["-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
                "-XX:G1ReservePercent=20", "-XX:InitiatingHeapOccupancyPercent=15"]
_AIKAR_LARGE = ["-XX:G1NewSizePercent=40", "-XX:G1MaxNewSizePercent=50", "-XX:G1HeapRegionSize=16M",
                "-XX:G1ReservePercent=15", "-XX:InitiatingHeapOccupancyPercent=20"]


def preset_flags(preset: str, ram_mb: int) -> list[str]:
    if preset == "aikar":
        # UnlockExperimentalVMOptions, G1NewSizePercent gibi deneysel bayraklardan ÖNCE gelmek zorunda
        sized = _AIKAR_SMALL if ram_mb <= 12288 else _AIKAR_LARGE
        return ["-XX:+UnlockExperimentalVMOptions"] + sized + _AIKAR_COMMON
    return []


def jvm_flags(inst: dict) -> list[str]:
    """Bellek + kodlama + ön ayar + kullanıcının ek argümanları (sonuncusu öncekini ezer)."""
    ram = int(inst["ram_mb"])
    return [
        f"-Xms{ram}M", f"-Xmx{ram}M", "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8",
        *preset_flags(inst.get("jvm_preset") or "none", ram),
        *shlex.split(inst.get("jvm_args") or ""),
    ]


# ---------- argüman dosyası ----------
_ARGS_RE = re.compile(r"^[A-Za-z0-9_./+{}-]{1,200}$")
_AUTO_PATTERNS = {
    "forge": "libraries/net/minecraftforge/forge/*/{plat}_args.txt",
    "neoforge": "libraries/net/neoforged/neoforge/*/{plat}_args.txt",
}


def validate_args_file(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None                      # boş = otomatik bul
    if not _ARGS_RE.match(raw) or raw.startswith("/") or ".." in raw.split("/") or "{" in raw.replace("{platform}", ""):
        return "Argüman dosyası yolu geçersiz (sunucu klasörüne göre göreli olmalı, '..' ve özel karakter olamaz)."
    return None


def _natural(p: Path):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.as_posix())]


def resolve_args_file(inst: dict) -> str:
    root = Path(inst["path"]).resolve()
    plat = "win" if os.name == "nt" else "unix"
    raw = (inst.get("args_file") or "").strip()
    if err := validate_args_file(raw):
        raise LaunchError(err)
    if raw:
        cands = [root / raw.replace("{platform}", plat)]
    else:
        pattern = _AUTO_PATTERNS.get(inst.get("loader") or "")
        cands = sorted(root.glob(pattern.format(plat=plat)), key=_natural) if pattern else []
        cands = cands[-1:]               # en yeni sürüm
    for c in cands:
        c = c.resolve()
        if c.is_file() and c.is_relative_to(root):
            return c.relative_to(root).as_posix()
    raise LaunchError(
        "Argüman dosyası bulunamadı. Forge/NeoForge kurucusunu sunucu klasöründe çalıştırdın mı? "
        f"(Aranan: {raw or _AUTO_PATTERNS.get(inst.get('loader') or '', '?')})"
    )


def build_command(inst: dict) -> list[str]:
    err = validate_jvm_args(inst.get("jvm_args") or "") or validate_java_path(inst["java_path"])
    if err:                               # derin savunma: veritabanındaki eski kayıtlar da kontrol edilir
        raise LaunchError(err)
    root = Path(inst["path"])
    flags = jvm_flags(inst)
    if inst.get("launch_type") == "args-file":
        rel = resolve_args_file(inst)
        try:
            (root / "user_jvm_args.txt").write_text("\n".join(flags) + "\n", encoding="utf-8")
        except OSError as e:
            raise LaunchError(f"user_jvm_args.txt yazılamadı: {e}")
        return [inst["java_path"], "@user_jvm_args.txt", f"@{rel}", "nogui"]
    jar = root / inst["jar_file"]
    if not jar.is_file():
        raise LaunchError(f"Jar dosyası bulunamadı: {jar}")
    return [inst["java_path"], *flags, "-jar", inst["jar_file"], "nogui"]
