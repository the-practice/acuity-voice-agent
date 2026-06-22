import json
import logging
from typing import Any
from datetime import timedelta

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


class CallState:
    """Call state storage with Redis fallback to in-memory."""

    def __init__(self):
        self._redis = None
        self._memory = {}
        self._enabled = False

    async def init(self):
        """Initialize Redis connection."""
        try:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            self._enabled = True
            logger.info("CallState: Redis connected")
        except Exception as e:
            logger.warning(f"CallState: Redis unavailable, using in-memory: {e}")
            self._enabled = False

    async def get(self, call_id: str, key: str = None) -> Any:
        """Get state for call_id."""
        if self._enabled and self._redis:
            try:
                data = await self._redis.get(f"call:{call_id}")
                if data:
                    state = json.loads(data)
                    return state.get(key) if key else state
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        return self._memory.get(call_id, {}).get(key) if key else self._memory.get(call_id, {})

    async def set(self, call_id: str, key: str, value: Any) -> None:
        """Set state value for call_id."""
        if self._enabled and self._redis:
            try:
                existing = await self.get(call_id)
                existing[key] = value
                await self._redis.setex(
                    f"call:{call_id}",
                    timedelta(hours=24),
                    json.dumps(existing),
                )
                return
            except Exception as e:
                logger.error(f"Redis set error: {e}")
        if call_id not in self._memory:
            self._memory[call_id] = {}
        self._memory[call_id][key] = value

    async def delete(self, call_id: str) -> None:
        """Delete state for call_id."""
        if self._enabled and self._redis:
            try:
                await self._redis.delete(f"call:{call_id}")
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
        self._memory.pop(call_id, None)

    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()


call_state = CallState()
