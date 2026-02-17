from __future__ import annotations

import json
import logging
from typing import Any

import redis

from .config import settings

logger = logging.getLogger("platform.realtime")
_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def publish_bot_event(bot_instance_id: str, event: dict[str, Any]) -> None:
    if not settings.event_publish_realtime:
        return
    channel = f"bot:{bot_instance_id}:events"
    payload = json.dumps(event, ensure_ascii=True, separators=(",", ":"), default=str)
    try:
        _get_redis_client().publish(channel, payload)
    except Exception as exc:
        logger.warning("Realtime publish failed on channel=%s: %s", channel, exc)

