"""Rebuild the Redis leaderboards from score_events (the source of truth).

Three ways to trigger it:
    python -m app.rebuild            # command line
    POST /admin/rebuild              # admin route (runs as a background task)
    automatically at startup         # when the global board is missing from Redis

It uses ZADD ... GT, so it only ever raises scores. That makes it safe to run
while users are submitting scores, and safe to re-run. To also drop stale
entries, delete the leaderboard:* keys in Redis first.
"""

import asyncio
import logging
from contextlib import suppress

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import keys
from app.db import SessionLocal
from app.models import ScoreEvent
from app.redis_client import close_redis, redis_client

logger = logging.getLogger(__name__)

CHUNK = 1000
LOCK_SECONDS = 600  # safety expiry in case a rebuild crashes without releasing the lock


async def rebuild_leaderboards(r: Redis, session: AsyncSession) -> dict[str, int]:
    """Re-create the global and per-game boards. Returns simple counts."""
    # One row per (game, user): their best score in that game. Streamed in chunks,
    # so memory depends on the number of players, not the number of events.
    per_game_user_best = select(
        ScoreEvent.game, ScoreEvent.user_id, func.max(ScoreEvent.score)
    ).group_by(ScoreEvent.game, ScoreEvent.user_id)

    global_best: dict[int, int] = {}
    games: set[str] = set()
    entries = 0

    result = await session.stream(per_game_user_best)
    async for rows in result.partitions(CHUNK):
        per_game: dict[str, dict[str, int]] = {}
        for game, user_id, best in rows:
            per_game.setdefault(game, {})[str(user_id)] = best
            global_best[user_id] = max(best, global_best.get(user_id, best))

        async with r.pipeline(transaction=False) as pipe:
            for game, scores in per_game.items():
                pipe.zadd(keys.game_leaderboard(game), scores, gt=True)
            await pipe.execute()

        games.update(per_game)
        entries += sum(len(scores) for scores in per_game.values())

    # The global board is each user's best score across all games.
    members = [(str(user_id), best) for user_id, best in global_best.items()]
    for i in range(0, len(members), CHUNK):
        await r.zadd(keys.GLOBAL_LEADERBOARD, dict(members[i : i + CHUNK]), gt=True)

    return {
        "players": len(global_best),
        "game_boards": len(games),
        "entries": entries + len(global_best),
    }


async def run_rebuild_job(r: Redis) -> dict[str, int] | None:
    """Rebuild under a lock so two rebuilds never overlap. Logs failures, never raises."""
    try:
        if not await r.set(keys.REBUILD_LOCK, "1", nx=True, ex=LOCK_SECONDS):
            logger.info("Leaderboard rebuild already running; skipping")
            return None
    except RedisError:
        logger.warning("Redis unavailable; cannot rebuild leaderboards")
        return None

    try:
        async with SessionLocal() as session:
            stats = await rebuild_leaderboards(r, session)
        logger.info("Leaderboard rebuild finished: %s", stats)
        return stats
    except Exception:
        logger.exception("Leaderboard rebuild failed")
        return None
    finally:
        with suppress(RedisError):
            await r.delete(keys.REBUILD_LOCK)


async def rebuild_if_missing(r: Redis) -> None:
    """Startup self-heal: Redis lost the global board but SQL still has scores."""
    try:
        if await r.exists(keys.GLOBAL_LEADERBOARD):
            return
        async with SessionLocal() as session:
            has_events = await session.scalar(select(ScoreEvent.id).limit(1)) is not None
    except RedisError:
        logger.warning("Redis unavailable at startup; skipping automatic rebuild")
        return

    if has_events:
        logger.info("Global leaderboard missing in Redis; rebuilding from score_events")
        await run_rebuild_job(r)


async def _cli() -> None:
    try:
        stats = await run_rebuild_job(redis_client)
    finally:
        await close_redis()
    print(stats if stats is not None else "Nothing rebuilt (already running, Redis down, or failed; see log).")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_cli())