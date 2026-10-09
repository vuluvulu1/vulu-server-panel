"""Minecraft'ı panelin alt süreci olarak çalıştırır.

Neden asyncio.create_subprocess_exec değil de Popen + okuyucu thread?
Windows'ta `uvicorn --reload` SelectorEventLoop kullanır ve asyncio alt süreçleri
orada NotImplementedError verir. Thread'li Popen her platformda çalışır.

Not: Panel kapanırsa alt süreçler de kapanır (lifespan'da zarifçe durdurulur).
Panelden bağımsız çalışma için VDS'te Systemd/Tmux backend yazılacak (Faz 6).
"""
import asyncio
import re
import shlex
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

import psutil

from ...db import get_conn
from ..jvm import LaunchError, build_command
from .base import ProcessError

BUFFER_LINES = 1000
DONE_RE = re.compile(r"Done \(\d+[.,]\d+s\)!")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _db_status(instance_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE instances SET status = ? WHERE id = ?", (status, instance_id))


class _Channel:
    """Bir instance'ın log tamponu + canlı dinleyicileri. Süreç bitse de yaşar."""

    def __init__(self) -> None:
        self.buffer: deque[str] = deque(maxlen=BUFFER_LINES)
        self.subscribers: set[asyncio.Queue] = set()
        self.status = "stopped"
        self.last_progress: dict | None = None   # hazırlık (Java kurulumu) ilerlemesi

    def publish(self, msg: dict) -> None:
        if msg["type"] == "log":
            self.buffer.append(msg["line"])
        for q in list(self.subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # yavaş istemci: mesajı atla, sistemi bloklama


class _Managed:
    def __init__(self, popen: subprocess.Popen) -> None:
        self.popen = popen
        self.stopping = False  # kullanıcı durdurdu mu? (çökme ile ayırmak için)


class SubprocessBackend:
    def __init__(self) -> None:
        self._procs: dict[int, _Managed] = {}
        self._channels: dict[int, _Channel] = {}

    # ---------- yardımcılar ----------
    def _channel(self, iid: int) -> _Channel:
        return self._channels.setdefault(iid, _Channel())

    def _log(self, iid: int, line: str) -> None:
        self._channel(iid).publish({"type": "log", "line": line})

    def set_status(self, iid: int, status: str) -> None:
        ch = self._channel(iid)
        ch.status = status
        ch.publish({"type": "status", "status": status})
        _db_status(iid, status)

    def notify_error(self, iid: int, message: str) -> None:
        self._channel(iid).publish({"type": "error", "message": message})

    def emit(self, iid: int, msg: dict) -> None:
        """Konsol dinleyicilerine herhangi bir olay yayınlar (ilerleme çubuğu vb.)."""
        ch = self._channel(iid)
        if msg["type"] == "progress":
            ch.last_progress = msg
        elif msg["type"] == "progress_end":
            ch.last_progress = None
        ch.publish(msg)

    def log(self, iid: int, line: str) -> None:
        self._log(iid, line)

    def progress(self, iid: int) -> dict | None:
        return self._channel(iid).last_progress

    # ---------- sorgular ----------
    def is_running(self, iid: int) -> bool:
        m = self._procs.get(iid)
        return bool(m and m.popen.poll() is None)

    def status(self, iid: int) -> str:
        return self._channel(iid).status

    def pid(self, iid: int) -> int | None:
        m = self._procs.get(iid)
        return m.popen.pid if m and m.popen.poll() is None else None

    def running_ids(self) -> list[int]:
        return [i for i, m in self._procs.items() if m.popen.poll() is None]

    def history(self, iid: int) -> list[str]:
        return list(self._channel(iid).buffer)

    def subscribe(self, iid: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._channel(iid).subscribers.add(q)
        return q

    def unsubscribe(self, iid: int, q: asyncio.Queue) -> None:
        self._channel(iid).subscribers.discard(q)

    # ---------- başlat ----------
    async def start(self, inst: dict) -> None:
        iid = inst["id"]
        if self.is_running(iid):
            raise ProcessError("Sunucu zaten çalışıyor.")

        path = Path(inst["path"])
        try:
            cmd = build_command(inst)
        except LaunchError as e:
            raise ProcessError(str(e))

        ch = self._channel(iid)
        if ch.status != "preparing":      # hazırlık (indirme) satırlarını koru, yoksa konsolu temizle
            ch.buffer.clear()
            ch.publish({"type": "clear"})
        self._log(iid, "[panel] Başlatılıyor: " + " ".join(cmd))

        try:
            popen = subprocess.Popen(
                cmd, cwd=path,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except FileNotFoundError:
            raise ProcessError(
                f"Java bulunamadı: '{inst['java_path']}'. Java kurulu mu ve PATH'te mi? "
                "(Terminalde `java -version` dene.)"
            )
        except OSError as e:
            raise ProcessError(f"Süreç başlatılamadı: {e}")

        managed = _Managed(popen)
        self._procs[iid] = managed
        self.set_status(iid, "starting")

        loop = asyncio.get_running_loop()
        threading.Thread(target=self._reader, args=(iid, managed, loop), daemon=True).start()

    # ---------- okuyucu thread ----------
    def _reader(self, iid: int, m: _Managed, loop: asyncio.AbstractEventLoop) -> None:
        try:
            for line in m.popen.stdout:
                self._call(loop, self._on_line, iid, line.rstrip("\r\n"))
        except ValueError:
            pass  # stdout kapandı
        code = m.popen.wait()
        self._call(loop, self._on_exit, iid, m, code)

    @staticmethod
    def _call(loop: asyncio.AbstractEventLoop, fn, *args) -> None:
        try:
            loop.call_soon_threadsafe(fn, *args)
        except RuntimeError:
            pass  # event loop kapanmış (panel kapanıyor)

    def _on_line(self, iid: int, line: str) -> None:
        line = ANSI_RE.sub("", line)
        self._log(iid, line)
        if self._channel(iid).status == "starting" and DONE_RE.search(line):
            self.set_status(iid, "running")

    def _on_exit(self, iid: int, m: _Managed, code: int) -> None:
        if self._procs.get(iid) is not m:
            return  # bu süreç zaten yenisiyle değiştirilmiş
        del self._procs[iid]
        status = "stopped" if (m.stopping or code == 0) else "crashed"
        self._log(iid, f"[panel] Sunucu kapandı (çıkış kodu: {code})")
        self.set_status(iid, status)

    # ---------- durdur / öldür ----------
    async def stop(self, iid: int, timeout: int = 60) -> None:
        m = self._procs.get(iid)
        if not m or m.popen.poll() is not None:
            return
        m.stopping = True
        self.set_status(iid, "stopping")
        try:
            m.popen.stdin.write("stop\n")
            m.popen.stdin.flush()
        except OSError:
            pass
        try:
            await asyncio.to_thread(m.popen.wait, timeout)
        except subprocess.TimeoutExpired:
            self._log(iid, f"[panel] {timeout} sn içinde kapanmadı, zorla sonlandırılıyor.")
            await self.kill(iid)

    async def kill(self, iid: int) -> None:
        m = self._procs.get(iid)
        if not m or m.popen.poll() is not None:
            return
        m.stopping = True
        try:
            for child in psutil.Process(m.popen.pid).children(recursive=True):
                child.kill()
        except psutil.NoSuchProcess:
            pass
        m.popen.kill()

    async def restart(self, inst: dict) -> None:
        await self.stop(inst["id"])
        await self.start(inst)

    async def stop_all(self, timeout: int = 30) -> None:
        await asyncio.gather(*(self.stop(i, timeout) for i in list(self._procs)), return_exceptions=True)

    # ---------- komut ----------
    async def send_command(self, iid: int, command: str) -> None:
        m = self._procs.get(iid)
        if not m or m.popen.poll() is not None:
            raise ProcessError("Sunucu çalışmıyor.")
        command = command.replace("\r", " ").replace("\n", " ").strip()[:500]
        if not command:
            return
        self._log(iid, f"> {command}")
        try:
            m.popen.stdin.write(command + "\n")
            m.popen.stdin.flush()
        except OSError:
            raise ProcessError("Komut gönderilemedi (süreç kapanıyor olabilir).")
