"""Minimal Source-RCON istemcisi (Minecraft RCON ile uyumlu)."""
import asyncio
import struct


class RconError(Exception):
    pass


_NET = (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError)


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 3.0) -> None:
        self.host, self.port, self.password, self.timeout = host, port, password, timeout
        self._r: asyncio.StreamReader | None = None
        self._w: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        try:
            self._r, self._w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)
            await self._send(1, 3, self.password)
            for _ in range(5):
                rid, typ, _ = await self._recv()
                if rid == -1:
                    raise RconError("RCON şifresi reddedildi.")
                if typ == 2 and rid == 1:
                    return
            raise RconError("RCON girişi tamamlanamadı.")
        except _NET as e:
            await self.close()
            raise RconError(f"RCON bağlantısı kurulamadı ({e.__class__.__name__}).")
        except RconError:
            await self.close()
            raise

    async def command(self, cmd: str) -> str:
        if not self._w:
            raise RconError("RCON bağlı değil.")
        try:
            await self._send(2, 2, cmd)
            return (await self._recv())[2]
        except _NET as e:
            await self.close()
            raise RconError(f"RCON komutu başarısız ({e.__class__.__name__}).")

    async def close(self) -> None:
        w, self._w, self._r = self._w, None, None
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), 1)
            except Exception:
                pass

    async def _send(self, req_id: int, typ: int, body: str) -> None:
        payload = struct.pack("<ii", req_id, typ) + body.encode("utf-8") + b"\x00\x00"
        self._w.write(struct.pack("<i", len(payload)) + payload)
        await asyncio.wait_for(self._w.drain(), self.timeout)

    async def _recv(self) -> tuple[int, int, str]:
        length = struct.unpack("<i", await asyncio.wait_for(self._r.readexactly(4), self.timeout))[0]
        if not 10 <= length <= 8192:
            raise RconError("Geçersiz RCON paketi.")
        data = await asyncio.wait_for(self._r.readexactly(length), self.timeout)
        rid, typ = struct.unpack("<ii", data[:8])
        return rid, typ, data[8:-2].decode("utf-8", "replace")
