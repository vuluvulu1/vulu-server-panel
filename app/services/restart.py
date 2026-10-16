"""Panelin kendini yeniden başlatması: sunucular düzgünce durdurulur, sonra run.py'ye işaret bırakılır.
run.py bu işareti görünce paneli yeni kodla/ayarlarla yeniden açar."""
import asyncio
import os

from ..config import DATA_DIR, SUPERVISED

RESTART_FLAG = DATA_DIR / "restart.flag"


def request_restart(delay: float = 0.5) -> None:
    async def later():
        from .container import playit, process_manager
        await asyncio.sleep(delay)                    # yanıt tarayıcıya ulaşsın
        try:
            await process_manager.stop_all()          # sunucular düzgünce kaydedip kapansın
            await playit.stop_agent()
        finally:
            RESTART_FLAG.parent.mkdir(parents=True, exist_ok=True)
            RESTART_FLAG.write_text(str(os.getpid()))
    asyncio.get_running_loop().create_task(later())


def can_restart() -> bool:
    return SUPERVISED
