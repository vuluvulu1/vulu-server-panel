"""Zamanlanmış görevler: günlük saatte yeniden başlatma (oyunculara geri sayımla) ve yedekleme (saklama sınırıyla).

Saatler panelin çalıştığı bilgisayarın yerel saatidir. Panel kapalıyken kaçırılan görevler sonradan çalıştırılmaz.
"""
import asyncio
import datetime as dt
import logging
import re

from ..db import get_conn, get_instance
from ..i18n import _t

log = logging.getLogger("vulu.scheduler")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DAYS_RE = re.compile(r"^[1-7]{1,7}$")
AUTO_NOTE = "auto:zamanli"
WARN_STEPS = (30, 15, 10, 5, 3, 2, 1)          # dakika: bu anlarda oyunculara duyuru


def next_run(time_hm: str, days: str, now: dt.datetime | None = None) -> dt.datetime | None:
    now = now or dt.datetime.now()
    h, m = map(int, time_hm.split(":"))
    for add in range(0, 8):
        d = (now + dt.timedelta(days=add)).replace(hour=h, minute=m, second=0, microsecond=0)
        if str(d.isoweekday()) in days and d > now:
            return d
    return None


class Scheduler:
    def __init__(self, launcher, backups, pm) -> None:
        self.launcher, self.backups, self.pm = launcher, backups, pm
        self._loop_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._running: set[int] = set()          # şu an çalışan zamanlama id'leri

    def start(self) -> None:
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        for t in [self._loop_task, *self._tasks]:
            if t:
                t.cancel()
        await asyncio.gather(*(t for t in [self._loop_task, *self._tasks] if t), return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            try:
                self._tick(dt.datetime.now())
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("zamanlayıcı")
            await asyncio.sleep(15)

    def _tick(self, now: dt.datetime) -> None:
        with get_conn() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM schedules WHERE enabled = 1")]
        for s in rows:
            if s["id"] in self._running or not TIME_RE.match(s["time_hm"]) or not DAYS_RE.match(s["days"]):
                continue
            h, m = map(int, s["time_hm"].split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            lead = max(0, int(s["warn_minutes"])) if s["kind"] == "restart" else 0
            start_at = target - dt.timedelta(minutes=lead)          # uyarılar hedeften önce başlar
            slot = target.strftime("%Y-%m-%d %H:%M")
            if str(target.isoweekday()) not in s["days"] or s["last_run"] == slot:
                continue
            if not (start_at <= now < target + dt.timedelta(minutes=2)):
                continue
            self._mark(s["id"], slot, _t("çalışıyor…"))
            self._running.add(s["id"])
            t = asyncio.create_task(self._run(s, target, slot))
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)

    @staticmethod
    def _mark(sid: int, slot: str | None, result: str) -> None:
        with get_conn() as conn:
            if slot:
                conn.execute("UPDATE schedules SET last_run = ?, last_result = ? WHERE id = ?", (slot, result[:200], sid))
            else:
                conn.execute("UPDATE schedules SET last_result = ? WHERE id = ?", (result[:200], sid))

    async def _run(self, s: dict, target: dt.datetime, slot: str) -> None:
        try:
            inst = get_instance(s["instance_id"])
            if not inst:
                return
            res = await (self._restart(inst, s, target) if s["kind"] == "restart" else self._backup(inst, s))
            self._mark(s["id"], None, res)
        except asyncio.CancelledError:
            self._mark(s["id"], None, _t("panel kapandığı için yarıda kaldı"))
            raise
        except Exception as e:
            log.exception("zamanlanmış görev")
            self._mark(s["id"], None, _t('hata: {e}', e=e))
        finally:
            self._running.discard(s["id"])

    async def _say(self, iid: int, text: str) -> None:
        try:
            if self.pm.status(iid) == "running":
                await self.pm.send_command(iid, f"say {text}")
        except Exception:
            pass

    async def _restart(self, inst: dict, s: dict, target: dt.datetime) -> str:
        iid = inst["id"]
        if self.pm.status(iid) != "running":
            return _t("atlandı: sunucu çalışmıyordu")
        steps = [w for w in WARN_STEPS if w <= int(s["warn_minutes"])]
        for w in steps:                                   # geri sayım duyuruları
            at = target - dt.timedelta(minutes=w)
            delay = (at - dt.datetime.now()).total_seconds()
            if delay < -30:
                continue                                  # bu adım geçmiş
            await asyncio.sleep(max(0, delay))
            await self._say(iid, f"Sunucu {w} dakika icinde yeniden baslatilacak.")
        delay = (target - dt.datetime.now()).total_seconds() - 10
        if delay > 0:
            await asyncio.sleep(delay)
        await self._say(iid, _t("Sunucu 10 saniye icinde yeniden baslatiliyor..."))
        await asyncio.sleep(10 if steps else 0)
        if self.pm.status(iid) != "running":
            return _t("atlandı: sunucu bu arada durdurulmuş")
        await self.launcher.restart(get_instance(iid) or inst)
        return _t("yeniden başlatıldı")

    async def _backup(self, inst: dict, s: dict) -> str:
        job = self.backups.ensure_create_job(inst, s["backup_mode"], AUTO_NOTE)
        async for snap in job.watch():
            if snap["status"] != "running":
                break
        if job.status != "done":
            return _t('yedek başarısız: {error}', error=job.error)
        removed = self.backups.prune(inst, AUTO_NOTE, int(s["keep"]))
        return _t('yedek alındı ({v0})', v0=job.result.get('file')) + (_t(', {removed} eski yedek silindi', removed=removed) if removed else "")
