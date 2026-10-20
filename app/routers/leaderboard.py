from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import keys
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.redis_client import get_redis
from app.schemas import GAME_PATTERN, LeaderboardEntry, MyRank

router = APIRouter(tags=["leaderboard"])

Limit = Annotated[int, Query(ge=1, le=100, description="How many players to return")]
Offset = Annotated[int, Query(ge=0, description="How many players to skip (for paging)")]
Game = Annotated[str, Path(min_length=1, max_length=64, pattern=GAME_PATTERN)]


async def _top_entries(
    r: Redis, session: AsyncSession, key: str, limit: int, offset: int
) -> list[LeaderboardEntry]:
    # Highest score first. Members are user ids stored as strings.
    rows = await r.zrevrange(key, offset, offset + limit - 1, withscores=True)
    if not rows:
        return []

    user_ids = [int(member) for member, _ in rows]

    # One batched query for all usernames (no N+1).
    result = await session.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
    names = {uid: name for uid, name in result}

    return [
        LeaderboardEntry(
            rank=offset + position,
            user_id=uid,
            username=names.get(uid, "[unknown]"),
            score=int(score),
        )
        for position, (uid, (_, score)) in enumerate(zip(user_ids, rows), start=1)
    ]


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def global_leaderboard(
    limit: Limit = 10,
    offset: Offset = 0,
    r: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_session),
):
    return await _top_entries(r, session, keys.GLOBAL_LEADERBOARD, limit, offset)


@router.get("/leaderboard/{game}", response_model=list[LeaderboardEntry])
async def game_leaderboard(
    game: Game,
    limit: Limit = 10,
    offset: Offset = 0,
    r: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_session),
):
    # An unknown game just has an empty board.
    return await _top_entries(r, session, keys.game_leaderboard(game), limit, offset)


@router.get("/me/rank", response_model=MyRank)
async def my_rank(
    user: User = Depends(get_current_user),
    r: Redis = Depends(get_redis),
):
    member = str(user.id)
    # One round trip, and the three values come from the same moment.
    async with r.pipeline(transaction=True) as pipe:
        pipe.zrevrank(keys.GLOBAL_LEADERBOARD, member)
        pipe.zscore(keys.GLOBAL_LEADERBOARD, member)
        pipe.zcard(keys.GLOBAL_LEADERBOARD)
        rank, score, total = await pipe.execute()

    if rank is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have not submitted a score yet")

    return MyRank(
        user_id=user.id,
        username=user.username,
        rank=rank + 1,  # ZREVRANK is 0-based
        score=int(score),
        total_players=total,
    )