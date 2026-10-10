"""Arayüzün tek ayar noktası: marka, menü ve tema keşfi.

- Menüye sayfa eklemek  -> NAV_ITEMS'a bir satır ekle
- Yeni tema eklemek     -> app/static/css/themes/ altına bir .css dosyası at
- Marka adını değiştir  -> BRAND
"""
import re

from .config import BASE_DIR

BRAND = {"name": "vulu", "accent_word": "panel"}
SOURCE_URL = "https://github.com/vuluvulu1/vulu-server-panel"   # AGPL-3.0: kaynak koduna bağlantı (Ayarlar sayfasının altında)

# soon=True olanlar "yakında" diye pasif görünür (sayfa henüz yok)
NAV_ITEMS = [
    {"label": "Sunucular", "href": "/", "icon": "bi-hdd-rack"},
    {"label": "Yedekler", "href": "/backups", "icon": "bi-archive"},
    {"label": "Ayarlar", "href": "/settings", "icon": "bi-gear"},
]

DEFAULT_THEME = "vulu"
THEMES_DIR = BASE_DIR / "app" / "static" / "css" / "themes"

# Her tema dosyasının ilk satırı: /* name: Görünen Ad | mode: dark */
_META = re.compile(r"/\*\s*name:\s*(?P<name>.+?)\s*\|\s*mode:\s*(?P<mode>dark|light)\s*\*/")


def list_themes() -> list[dict]:
    themes = []
    for f in sorted(THEMES_DIR.glob("*.css")):
        lines = f.read_text(encoding="utf-8").splitlines()
        m = _META.match(lines[0]) if lines else None
        themes.append({
            "id": f.stem,
            "name": m["name"] if m else f.stem,
            "mode": m["mode"] if m else "dark",
        })
    themes.sort(key=lambda t: (t["id"] != DEFAULT_THEME, t["name"].lower()))   # varsayılan en başta
    return themes
