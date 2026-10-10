"""Sunucu izleme: süreç CPU/RAM (psutil) + oyuncu/TPS (RCON). 2 sn'de bir örnekler, son ~6 dk bellekte."""
import asyncio
import logging
import re
import time
from collections import deque

import psutil

from ..db import get_instance
from .rcon import RconClient, RconError
from ..i18n import _t

log = logging.getLogger("vulu.stats")
INTERVAL, RCON_EVERY, HISTORY = 2.0, 3, 180
TPS_CMDS = {"paper": "tps", "forge": "forge tps", "neoforge": "neoforge tps"}   # vanilla/fabric'te yok
_COLOR = re.compile(r"§.")
_LIST = re.compile(r"There are (\d+) of a max of (\d+) players online:?\s*(.*)", re.S)
_TPS = (re.compile(r"Mean TPS:\s*([\d.]+)"), re.compile(r"TPS from last[^:]*:\s*\*?([\d.]+)"),
        re.compile(r"Overall:\s*([\d.,]+)\s*TPS"))      # NeoForge/yeni Forge (Türkçe yerelde ondalık virgül: 20,000)


def parse_list(text: str):
    m = _LIST.search(_COLOR.sub("", text))
    if not m:
        return None
    return int(m[1]), int(m[2]), [n.strip() for n in m[3].split(",") if n.strip()]


def parse_tps(text: str) -> float | None:
    t = _COLOR.sub("", text)
    for rx in _TPS:
        m = rx.search(t)
        if m:
            try:
                return round(min(float(m[1].replace(",", ".")), 20.0), 1)
            except ValueError:
                return None
    return None


class _St:
    def __init__(self) -> None:
        self.hist: deque = deque(maxlen=HISTORY)
        self.rcon: RconClient | None = None
        self.clear()

    def clear(self) -> None:
        self.active, self.root, self.tree, self.ticks = False, None, {}, 0
        self.cpu = self.ram_mb = 0.0
        self.uptime = 0
        self.players = self.max_players = self.tps = None
        self.names: list[str] = []
        self.rcon_state = "off"
        self.tps_supported = False


class StatsService:
    def __init__(self, pm) -> None:
        self.pm = pm
        self._st: dict[int, _St] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        for st in self._st.values():
            if st.rcon:
                await st.rcon.close()

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("stats tick")
            await asyncio.sleep(INTERVAL)

    async def _tick(self) -> None:
        running = set(self.pm.running_ids())
        for iid, st in list(self._st.items()):
            if st.active and iid not in running:
                if st.rcon:
                    await st.rcon.close()
                    st.rcon = None
                st.active = False
                st.cpu = st.ram_mb = 0.0
                st.players = st.tps = None
                st.names, st.rcon_state = [], "off"
        for iid in running:
            await self._sample(iid)

    @staticmethod
    def _proc_sample(st: _St, pid: int) -> None:
        try:
            if st.root is None or st.root.pid != pid:
                st.root, st.tree = psutil.Process(pid), {}
            procs = [st.root] + st.root.children(recursive=True)
        except psutil.Error:
            return
        cpu, rss, alive = 0.0, 0, set()
        for p in procs:
            try:
                known = st.tree.get(p.pid)
                if known is None:
                    st.tree[p.pid] = known = p
                    p.cpu_percent(None)                 # ilk çağrı 0 döner (hazırlık)
                else:
                    cpu += known.cpu_percent(None)
                rss += known.memory_info().rss
                alive.add(p.pid)
            except psutil.Error:
                continue
        for k in [k for k in st.tree if k not in alive]:
            del st.tree[k]
        st.cpu = max(0.0, min(100.0, cpu / (psutil.cpu_count() or 1)))
        st.ram_mb = rss / 1048576
        try:
            st.uptime = max(0, int(time.time() - st.root.create_time()))
        except psutil.Error:
            pass

    async def _sample(self, iid: int) -> None:
        st = self._st.setdefault(iid, _St())
        if not st.active:                              # yeni başlatma: geçmişi sıfırla
            st.clear()
            st.hist.clear()
            st.active = True
        pid = self.pm.pid(iid)
        if pid is None:
            return
        await asyncio.to_thread(self._proc_sample, st, pid)
        st.ticks += 1
        if self.pm.status(iid) == "running" and st.ticks % RCON_EVERY == 0:
            await self._query_rcon(iid, st)
        st.hist.append({"t": int(time.time()), "cpu": round(st.cpu, 1), "ram": round(st.ram_mb),
                        "players": st.players, "tps": st.tps})

    async def _query_rcon(self, iid: int, st: _St) -> None:
        inst = get_instance(iid)
        if not inst or not inst.get("rcon_port") or not inst.get("rcon_password"):
            st.rcon_state = "off"
            return
        try:
            if st.rcon is None:
                cli = RconClient("127.0.0.1", int(inst["rcon_port"]), inst["rcon_password"])
                await cli.connect()
                st.rcon = cli
            res = parse_list(await st.rcon.command("list"))
            if res:
                st.players, st.max_players, st.names = res
            cmd = TPS_CMDS.get(inst.get("loader") or "")
            st.tps_supported = cmd is not None
            if cmd:
                st.tps = parse_tps(await st.rcon.command(cmd))
            st.rcon_state = "ok"
        except RconError:
            if st.rcon:
                await st.rcon.close()
            st.rcon, st.rcon_state = None, _t("bekleniyor")

    def snapshot(self, iid: int, ram_max_mb: int, history: bool = False) -> dict:
        st = self._st.get(iid)
        d = {
            "status": self.pm.status(iid), "running": bool(st and st.active), "ram_max_mb": ram_max_mb,
            "cpu": round(st.cpu, 1) if st else 0, "ram_mb": round(st.ram_mb) if st else 0,
            "uptime": st.uptime if st else 0,
            "players": st.players if st else None, "max_players": st.max_players if st else None,
            "player_names": list(st.names) if st else [], "tps": st.tps if st else None,
            "rcon": st.rcon_state if st else "off", "tps_supported": st.tps_supported if st else False,
        }
        if history:
            h = list(st.hist) if st else []
            d["history"] = {k: [p[k] for p in h] for k in ("t", "cpu", "ram", "players", "tps")}
        return d
