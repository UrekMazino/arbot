from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from ..config import settings

router = APIRouter(tags=["ws"])


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    bot_instance_id = str(websocket.query_params.get("bot_instance_id", "") or "").strip()
    channel = f"bot:{bot_instance_id}:events" if bot_instance_id else None

    await websocket.accept()
    redis_client = None
    pubsub = None

    if channel:
        try:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel)
        except Exception:
            pubsub = None

    try:
        await websocket.send_json(
            {
                "event_type": "heartbeat",
                "ts": datetime.now(timezone.utc).timestamp(),
                "payload": {
                    "status": "connected",
                    "bot_instance_id": bot_instance_id or None,
                    "channel": channel,
                },
            }
        )
        last_keepalive = datetime.now(timezone.utc).timestamp()
        while True:
            forwarded = False
            if pubsub is not None:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    forwarded = True
                    data = message.get("data")
                    if isinstance(data, str):
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            payload = {
                                "event_type": "status_update",
                                "ts": datetime.now(timezone.utc).timestamp(),
                                "payload": {"raw": data},
                            }
                    else:
                        payload = data
                    await websocket.send_json(payload)

            now_ts = datetime.now(timezone.utc).timestamp()
            if (not forwarded) and (now_ts - last_keepalive >= 15):
                await websocket.send_json(
                    {
                        "event_type": "heartbeat",
                        "ts": now_ts,
                        "payload": {"status": "alive", "channel": channel},
                    }
                )
                last_keepalive = now_ts

            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            if pubsub is not None:
                if channel:
                    await pubsub.unsubscribe(channel)
                await pubsub.aclose()
        except Exception:
            pass
        try:
            if redis_client is not None:
                await redis_client.aclose()
        except Exception:
            pass
