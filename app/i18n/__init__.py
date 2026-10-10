"""Çok dil desteği. Kaynak dil Türkçe: metinler koda Türkçe yazılır, çeviri kataloğu Türkçe → hedef dil eşlemesidir
(app/i18n/<dil>.json). Katalogda olmayan metin Türkçe gösterilir, böylece eksik çeviri hiçbir şeyi bozmaz.

Kullanım
  Python / Jinja:  _("Sunucu {name} başlatıldı.", name=ad)
  JavaScript:      _t("Sunucu {name} başlatıldı.", {name: ad})
Dil seçimi tarayıcıda `vulu_lang` çerezinde, panel genelinde data/lang.txt'de tutulur (konsol mesajları ve
zamanlanmış işler gibi istek dışı metinler için). Varsayılan Türkçe.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path

DEFAULT = "tr"
LANGS = {"tr": "Türkçe", "en": "English"}
COOKIE = "vulu_lang"
_DIR = Path(__file__).resolve().parent
_current: ContextVar[str | None] = ContextVar("vulu_lang", default=None)
_catalogs: dict[str, dict[str, str]] = {}


def _lang_file() -> Path:
    from ..config import DATA_DIR
    return DATA_DIR / "lang.txt"


def _load_global() -> str:
    try:
        v = _lang_file().read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT
    return v if v in LANGS else DEFAULT


_global: str | None = None            # ilk kullanımda okunur (config ile döngüsel içe aktarmayı önler)


def set_global(lang: str) -> None:
    """Panel geneli dil (arka plan işleri ve çerezsiz istekler bunu kullanır)."""
    global _global
    if lang not in LANGS:
        raise ValueError(lang)
    _global = lang
    try:
        f = _lang_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(lang + "\n", encoding="utf-8")
    except OSError:
        pass


def catalog(lang: str) -> dict[str, str]:
    if lang == DEFAULT or lang not in LANGS:
        return {}
    if lang not in _catalogs:
        try:
            data = json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))
            _catalogs[lang] = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v}
        except (OSError, ValueError):
            _catalogs[lang] = {}
    return _catalogs[lang]


def get_lang() -> str:
    global _global
    if _global is None:
        _global = _load_global()
    return _current.get() or _global


def set_lang(lang: str | None):
    return _current.set(lang if lang in LANGS else None)


def gettext(text: str, /, **kw) -> str:
    msg = catalog(get_lang()).get(text, text)
    if kw:
        try:
            return msg.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return msg


_ = _t = gettext


def lang_from_cookie(raw: str | None) -> str | None:
    return raw if raw in LANGS else None


class LangMiddleware:
    """Her istekte çerezden dili okur ve bu isteğin bağlamına yazar."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        lang = None
        for k, v in scope.get("headers", []):
            if k == b"cookie":
                for part in v.decode("latin-1").split(";"):
                    name, _sep, val = part.strip().partition("=")
                    if name == COOKIE:
                        lang = lang_from_cookie(val)
        token = set_lang(lang)
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
