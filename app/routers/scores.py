import logging

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app import keys
from app.db import get_session
from app.deps import get_current_user
from app.models import ScoreEvent, User
from app.redis_client import get_redis
from app.schemas import ScoreCreate, ScoreOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scores"])


@router.post("/scores", response_model=ScoreOut, status_code=status.HTTP_201_CREATED)
async def submit_score(
    body: ScoreCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    r: Redis = Depends(get_redis),
):
    # 1. SQL first: the append-only event is the source of truth.
    event = ScoreEvent(user_id=user.id, game=body.game, score=body.score)
    session.add(event)
    await session.commit()

    # 2. Redis second. GT = only raise an existing score, never lower it;
    #    a member that isn't in the set yet is simply added.
    member = str(user.id)
    synced = True
    try:
        async with r.pipeline(transaction=True) as pipe:
            pipe.zadd(keys.GLOBAL_LEADERBOARD, {member: body.score}, gt=True)
            pipe.zadd(keys.game_leaderboard(body.game), {member: body.score}, gt=True)
            await pipe.execute()
    except RedisError:
        # Event is safely stored; the boards can be rebuilt from score_events.
        logger.exception("Redis update failed for score event %s", event.id)
        synced = False

    return ScoreOut.model_validate(event).model_copy(update={"leaderboard_synced": synced})