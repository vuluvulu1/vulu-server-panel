"""Uzun süren işler (Java kurulumu, ileride mod paketi kurulumu) için küçük iş sistemi.

Bir iş yüzde/aşama/mesaj yayınlar; WebSocket ya da başka bir görev bunu izleyebilir.
"""
import asyncio
import logging
import time
import uuid
from typing import AsyncIterator, Awaitable, Callable

log = logging.getLogger("vulu.jobs")


class JobError(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek iş hatası."""


class Job:
    def __init__(self, kind: str, title: str, key: str | None = None) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.key = key
        self.status = "running"          # running | done | error
        self.percent = 0.0
        self.stage = ""
        self.message = ""
        self.error: str | None = None
        self.result: dict = {}
        self.finished_at: float | None = None
        self._subs: set[asyncio.Queue] = set()
        self._last_pub = 0.0

    def snapshot(self) -> dict:
        return {
            "type": "progress", "job_id": self.id, "kind": self.kind, "title": self.title,
            "status": self.status, "percent": round(self.percent, 1),
            "stage": self.stage, "message": self.message, "error": self.error,
            "result": self.result if self.status == "done" else None,
        }

    def _publish(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_pub < 0.1:   # sık güncellemeleri seyrelt
            return
        self._last_pub = now
        snap = self.snapshot()
        for q in list(self._subs):
            try:
                q.put_nowait(snap)
            except asyncio.QueueFull:
                pass

    def update(self, percent: float | None = None, stage: str | None = None, message: str | None = None) -> None:
        stage_changed = stage is not None and stage != self.stage
        if percent is not None:
            self.percent = max(self.percent, min(99.9, percent))   # geri gitmez, bitişi finish() verir
        if stage is not None:
            self.stage = stage
        if message is not None:
            self.message = message
        self._publish(force=stage_changed)

    def finish(self, result: dict | None = None) -> None:
        self.status, self.percent, self.stage = "done", 100.0, "done"
        self.result = result or {}
        self.finished_at = time.monotonic()
        self._publish(force=True)

    def fail(self, error: str) -> None:
        self.status, self.error, self.message = "error", error, error
        self.finished_at = time.monotonic()
        self._publish(force=True)

    async def watch(self) -> AsyncIterator[dict]:
        """Önce mevcut durumu, sonra iş bitene kadar güncellemeleri verir."""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.add(q)
        try:
            yield self.snapshot()
            while self.status == "running":
                try:
                    yield await asyncio.wait_for(q.get(), timeout=2)
                except asyncio.TimeoutError:
                    continue
            yield self.snapshot()
        finally:
            self._subs.discard(q)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def find_running(self, key: str) -> Job | None:
        return next((j for j in self._jobs.values() if j.key == key and j.status == "running"), None)

    def _purge(self) -> None:
        now = time.monotonic()
        for jid in [j.id for j in self._jobs.values() if j.finished_at and now - j.finished_at > 900]:
            del self._jobs[jid]

    def start(self, kind: str, title: str, key: str, runner: Callable[[Job], Awaitable[dict | None]]) -> Job:
        """Aynı key ile çalışan bir iş varsa onu döndürür (çift indirmeyi önler)."""
        existing = self.find_running(key)
        if existing:
            return existing
        self._purge()
        job = Job(kind, title, key)
        self._jobs[job.id] = job

        async def _run() -> None:
            try:
                job.finish(await runner(job))
            except asyncio.CancelledError:
                job.fail("İptal edildi.")
                raise
            except JobError as e:
                job.fail(str(e))
            except Exception as e:  # beklenmeyen hata: logla, kullanıcıya özet göster
                log.exception("job %s failed", job.id)
                job.fail(f"Beklenmeyen hata: {e}")

        task = asyncio.create_task(_run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
