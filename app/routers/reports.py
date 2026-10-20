from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import ScoreEvent, User
from app.schemas import GAME_PATTERN, Period, ReportEntry, ReportOut

# Reports aggregate in SQL, which is heavier than a Redis read, so require a login.
router = APIRouter(tags=["reports"], dependencies=[Depends(get_current_user)])


def _midnight_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def period_bounds(period: Period, day: date) -> tuple[datetime, datetime]:
    """The calendar bucket (UTC) that contains `day`, as [start, end)."""
    if period is Period.daily:
        start = day
        end = start + timedelta(days=1)
    elif period is Period.weekly:
        start = day - timedelta(days=day.weekday())  # Monday
        end = start + timedelta(days=7)
    else:
        start = day.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)  # 1st of next month
    return _midnight_utc(start), _midnight_utc(end)


@router.get("/reports/top-players", response_model=ReportOut)
async def top_players(
    period: Period = Period.weekly,
    on_date: Annotated[
        date | None,
        Query(alias="date", description="Any date inside the period. Defaults to today (UTC)."),
    ] = None,
    game: Annotated[
        str | None, Query(min_length=1, max_length=64, pattern=GAME_PATTERN)
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    session: AsyncSession = Depends(get_session),
):
    day = on_date or datetime.now(timezone.utc).date()
    start, end = period_bounds(period, day)

    best = func.max(ScoreEvent.score)
    stmt = (
        select(ScoreEvent.user_id, User.username, best, func.count())
        .join(User, User.id == ScoreEvent.user_id)
        .where(ScoreEvent.created_at >= start, ScoreEvent.created_at < end)
        .group_by(ScoreEvent.user_id, User.username)
        .order_by(best.desc(), ScoreEvent.user_id)  # user_id = stable tie-break
        .limit(limit)
    )
    if game:
        stmt = stmt.where(ScoreEvent.game == game)

    rows = (await session.execute(stmt)).all()
    entries = [
        ReportEntry(
            rank=rank, user_id=user_id, username=username, best_score=best_score, submissions=count
        )
        for rank, (user_id, username, best_score, count) in enumerate(rows, start=1)
    ]
    return ReportOut(period=period, start=start, end=end, game=game, entries=entries)