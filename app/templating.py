from fastapi.templating import Jinja2Templates

from . import ui
from .config import BASE_DIR

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

# Tüm şablonlarda erişilebilir. themes() çağrılabilir olduğu için
# yeni tema dosyası eklemek sunucuyu yeniden başlatmayı gerektirmez.
templates.env.globals.update(
    brand=ui.BRAND,
    nav_items=ui.NAV_ITEMS,
    themes=ui.list_themes,
    default_theme=ui.DEFAULT_THEME,
)
