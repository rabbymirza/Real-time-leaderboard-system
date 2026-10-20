import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import get_session, init_db
from app.rebuild import rebuild_if_missing
from app.redis_client import close_redis, get_redis, redis_client
from app.routers import admin, auth, leaderboard, reports, scores

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    # Self-heal: if Redis lost its data, rebuild in the background (don't block startup).
    rebuild_task = asyncio.create_task(rebuild_if_missing(redis_client))
    yield
    rebuild_task.cancel()
    await asyncio.gather(rebuild_task, return_exceptions=True)
    await close_redis()


app = FastAPI(title="Real-time Leaderboard", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(scores.router)
app.include_router(leaderboard.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.exception_handler(RedisError)
async def redis_unavailable(request: Request, exc: RedisError):
    # Any Redis failure on a read endpoint becomes a clean 503 instead of a 500.
    logger.error("Redis error on %s", request.url.path, exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Leaderboard temporarily unavailable"})


@app.get("/health")
async def health(
    r: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "redis": await r.ping()}