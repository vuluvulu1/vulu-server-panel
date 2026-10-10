import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
INSTANCES_DIR = BASE_DIR / "instances"
DB_PATH = DATA_DIR / "panel.db"

from . import panel_settings as _ps  # noqa: E402

# Panelden değiştirilen ayarlar (data/panel-settings.json) .env'in üzerine yazar
_PANEL = _ps.load(DATA_DIR)
HOST = _PANEL.get("host") or os.getenv("PANEL_HOST", "127.0.0.1")
PORT = int(_PANEL.get("port") or os.getenv("PANEL_PORT", "8000"))
SUPERVISED = os.getenv("VULU_SUPERVISED") == "1"          # run.py gözetiminde mi (panelden yeniden başlatma için)
SECRET_KEY = os.getenv("PANEL_SECRET_KEY", "degistir-beni")

RUNTIMES_DIR = BASE_DIR / "runtimes"

# Dış servis adresleri (testlerde sahte sunucuya yönlendirmek için env ile değiştirilebilir)
ADOPTIUM_API = os.getenv("VULU_ADOPTIUM_API", "https://api.adoptium.net/v3")
MOJANG_MANIFEST_URL = os.getenv(
    "VULU_MOJANG_MANIFEST", "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)

PAPER_API = os.getenv("VULU_PAPER_API", "https://fill.papermc.io/v3")
CACHE_DIR = DATA_DIR / "cache"

# PaperMC, istek başlığında iletişim bilgisi (site ya da e-posta) istiyor.
# .env içine PANEL_CONTACT=<e-posta veya GitHub adresin> yaz.
PANEL_CONTACT = (_PANEL["contact"] if "contact" in _PANEL else os.getenv("PANEL_CONTACT", "")).strip()
USER_AGENT = f"vulu-server-panel/0.1 ({PANEL_CONTACT or 'personal use'})"

# Panele hangi adreslerle girilebilir (DNS rebinding koruması). Varsayılan: sadece yerel.
# VDS'te alan adın için: PANEL_ALLOWED_HOSTS=panel.alanadin.com
ALLOWED_HOSTS_EXTRA = (_PANEL["allowed_hosts"] if "allowed_hosts" in _PANEL else
                       [h.strip().lower() for h in os.getenv("PANEL_ALLOWED_HOSTS", "").split(",") if h.strip()])

FABRIC_API = os.getenv("VULU_FABRIC_API", "https://meta.fabricmc.net/v2")

FORGE_MAVEN = os.getenv("VULU_FORGE_MAVEN", "https://maven.minecraftforge.net")
NEOFORGE_MAVEN = os.getenv("VULU_NEOFORGE_MAVEN", "https://maven.neoforged.net/releases")

MODRINTH_API = os.getenv("VULU_MODRINTH_API", "https://api.modrinth.com/v2")
# Mod dosyaları yalnızca bu sunuculardan indirilir (başka adrese yönlendirilen dosyalar reddedilir)
MODRINTH_CDN_HOSTS = [h.strip().lower() for h in os.getenv("VULU_MODRINTH_CDN", "cdn.modrinth.com,cdn-raw.modrinth.com").split(",") if h.strip()]

BACKUPS_DIR = DATA_DIR / "backups"

PLAYIT_API = os.getenv("VULU_PLAYIT_API", "https://api.playit.gg")
MOJANG_PROFILE_API = os.getenv("VULU_MOJANG_PROFILE_API", "https://api.mojang.com/users/profiles/minecraft/")
# Testler için ek Mojang indirme sunucuları (normalde boş)
MOJANG_EXTRA_HOSTS = {h.strip().lower() for h in os.getenv("VULU_MOJANG_HOSTS", "").split(",") if h.strip()}
