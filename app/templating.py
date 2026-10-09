from fastapi.templating import Jinja2Templates

from . import ui
from .config import BASE_DIR

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
_STATIC = BASE_DIR / "app" / "static"


def asset_v() -> int:
    """En son değişen statik dosyanın zamanı: /static/... adreslerine ?v= olarak eklenir (önbellek tazelenir)."""
    try:
        return int(max(p.stat().st_mtime for p in _STATIC.rglob("*") if p.is_file()))
    except (OSError, ValueError):
        return 0


# Tüm şablonlarda erişilebilir. themes() çağrılabilir olduğu için
# yeni tema dosyası eklemek sunucuyu yeniden başlatmayı gerektirmez.
templates.env.globals.update(
    brand=ui.BRAND,
    nav_items=ui.NAV_ITEMS,
    themes=ui.list_themes,
    default_theme=ui.DEFAULT_THEME,
    asset_v=asset_v,
)
