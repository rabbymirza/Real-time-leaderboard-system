from collections.abc import AsyncIterator

import redis.asyncio as redis

from app.config import settings

# One pooled client for the whole process; created/closed in the app lifespan.
redis_client: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> AsyncIterator[redis.Redis]:
    """FastAPI dependency."""
    yield redis_client


async def close_redis() -> None:
    await redis_client.aclose()