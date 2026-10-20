from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def lowercase_username(cls, v: str) -> str:
        # "Alice" and "alice" are the same account.
        return v.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Game names end up inside Redis keys, so keep them to a safe alphabet.
GAME_PATTERN = r"^[a-z0-9_-]+$"


class ScoreCreate(BaseModel):
    game: str = Field(min_length=1, max_length=64, pattern=GAME_PATTERN)
    # Redis scores are doubles, which are exact integers up to 2**53.
    score: int = Field(ge=0, le=2**53)


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game: str
    score: int
    created_at: datetime
    # False if the event was saved but Redis was unreachable (board can be rebuilt).
    leaderboard_synced: bool = True


class LeaderboardEntry(BaseModel):
    rank: int  # 1 = highest score
    user_id: int
    username: str
    score: int


class MyRank(BaseModel):
    user_id: int
    username: str
    rank: int
    score: int
    total_players: int


class Period(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class ReportEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    best_score: int
    submissions: int  # how many scores they submitted in the period


class ReportOut(BaseModel):
    period: Period
    start: datetime  # inclusive, UTC
    end: datetime  # exclusive, UTC
    game: str | None  # None = all games
    entries: list[ReportEntry]