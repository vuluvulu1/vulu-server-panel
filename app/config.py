import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
INSTANCES_DIR = BASE_DIR / "instances"
DB_PATH = DATA_DIR / "panel.db"

HOST = os.getenv("PANEL_HOST", "127.0.0.1")
PORT = int(os.getenv("PANEL_PORT", "8000"))
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
PANEL_CONTACT = os.getenv("PANEL_CONTACT", "").strip()
USER_AGENT = f"vulu-server-panel/0.1 ({PANEL_CONTACT or 'personal use'})"

# Panele hangi adreslerle girilebilir (DNS rebinding koruması). Varsayılan: sadece yerel.
# VDS'te alan adın için: PANEL_ALLOWED_HOSTS=panel.alanadin.com
ALLOWED_HOSTS_EXTRA = [h.strip().lower() for h in os.getenv("PANEL_ALLOWED_HOSTS", "").split(",") if h.strip()]
