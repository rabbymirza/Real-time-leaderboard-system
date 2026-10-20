"""Redis key naming. Every key is built here so the convention lives in one place.

Sorted set layout:
    member = user id (str)   -> stable even if a username changes
    score  = user's score    -> ZREVRANK/ZREVRANGE give rank 1 = highest
"""

GLOBAL_LEADERBOARD = "leaderboard:global"


def game_leaderboard(game: str) -> str:
    """Per-game board, e.g. leaderboard:game:chess"""
    return f"leaderboard:game:{game}"


def period_leaderboard(period: str, bucket: str) -> str:
    """Time-windowed board for periodic reports.

    period: "daily" | "weekly" | "monthly"
    bucket: "2026-10-18" | "2026-W42" | "2026-10"
    e.g. leaderboard:weekly:2026-W42
    """
    return f"leaderboard:{period}:{bucket}"


def username_cache(user_id: int) -> str:
    """Optional id -> username lookup so the board can render names without SQL."""
    return f"user:{user_id}:username"


# Short-lived lock so two rebuilds never run at once.
REBUILD_LOCK = "lock:rebuild"