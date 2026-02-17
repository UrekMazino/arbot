from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.send_json(
            {
                "event_type": "heartbeat",
                "ts": datetime.now(timezone.utc).timestamp(),
                "payload": {"status": "connected"},
            }
        )
        while True:
            # Keepalive channel; redis fanout wiring is V2.2.
            await asyncio.sleep(15)
            await websocket.send_json(
                {
                    "event_type": "heartbeat",
                    "ts": datetime.now(timezone.utc).timestamp(),
                    "payload": {"status": "alive"},
                }
            )
    except WebSocketDisconnect:
        return

