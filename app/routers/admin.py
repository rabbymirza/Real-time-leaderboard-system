from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from redis.asyncio import Redis

from app import keys
from app.deps import require_admin
from app.rebuild import run_rebuild_job
from app.redis_client import get_redis

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild(background_tasks: BackgroundTasks, r: Redis = Depends(get_redis)):
    if await r.exists(keys.REBUILD_LOCK):
        raise HTTPException(status.HTTP_409_CONFLICT, "A rebuild is already running")
    # The job opens its own DB session: the request's session is closed by then.
    background_tasks.add_task(run_rebuild_job, r)
    return {"status": "started"}