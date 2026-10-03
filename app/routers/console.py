import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..db import get_instance
from ..services.process import ProcessError, process_manager as pm

router = APIRouter()


@router.websocket("/ws/instances/{iid}/console")
async def console_ws(ws: WebSocket, iid: int):
    if not get_instance(iid):
        await ws.close(code=4404)
        return
    await ws.accept()

    # subscribe + history arasında await yok -> satır kaçmaz, tekrarlanmaz
    q = pm.subscribe(iid)
    await ws.send_json({"type": "history", "lines": pm.history(iid), "status": pm.status(iid), "progress": pm.progress(iid)})

    async def sender() -> None:
        try:
            while True:
                await ws.send_json(await q.get())
        except Exception:
            pass  # istemci gitti

    send_task = asyncio.create_task(sender())
    try:
        while True:
            try:
                data = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                continue
            cmd = str(data.get("cmd", "")).strip() if isinstance(data, dict) else ""
            if not cmd:
                continue
            try:
                await pm.send_command(iid, cmd)
            except ProcessError as e:
                await ws.send_json({"type": "error", "message": str(e)})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        send_task.cancel()
        pm.unsubscribe(iid, q)
