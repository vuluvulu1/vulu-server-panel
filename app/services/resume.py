"""Panel kapanırken çalışan sunucuları hatırlar, açılınca yeniden başlatır.

Böylece panel güncellemesi ya da bilgisayarın yeniden başlaması (örneğin her gece otomatik reset) sunucuları kapalı
bırakmaz. Çöken ya da elle durdurulan sunucular listede olmadığı için açılmaz.
"""
import asyncio
import json
import logging

from ..config import DATA_DIR
from ..db import get_instance
from ..i18n import _t

log = logging.getLogger("vulu.resume")
RESUME_FILE = DATA_DIR / "resume.json"
START_DELAY = 5          # sn: panel tamamen ayağa kalksın


def save(ids: list[int]) -> None:
    try:
        if ids:
            RESUME_FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")
        else:
            RESUME_FILE.unlink(missing_ok=True)
    except OSError:
        log.exception("çalışan sunucu listesi yazılamadı")


def take() -> list[int]:
    """Kayıtlı listeyi okur ve siler (bir kez kullanılır; bozuk bir sunucu her açılışta denenmesin)."""
    try:
        ids = json.loads(RESUME_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    RESUME_FILE.unlink(missing_ok=True)
    return [i for i in ids if isinstance(i, int)]


def start_saved(launcher) -> asyncio.Task | None:
    ids = take()
    return asyncio.create_task(_start(launcher, ids)) if ids else None


async def _start(launcher, ids: list[int]) -> None:
    await asyncio.sleep(START_DELAY)
    for iid in ids:                       # sırayla: bellek denetimi her sunucu için güncel durumu görsün
        inst = get_instance(iid)
        if not inst:
            continue
        launcher.pm.log(iid, _t("[panel] Panel yeniden başladı; sunucu kapanmadan önce çalıştığı için yeniden açılıyor."))
        try:
            await launcher.start(inst)
        except Exception as e:
            launcher.pm.log(iid, _t("[panel] Sunucu yeniden açılamadı: {e}", e=e))
