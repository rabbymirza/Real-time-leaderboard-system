import asyncio
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import settings

# recommended() = Argon2id with sane defaults
_hasher = PasswordHash.recommended()

# Verified against when the username doesn't exist, so "unknown user" and
# "wrong password" take about the same time.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


async def hash_password(password: str) -> str:
    # Argon2 is deliberately slow; keep it off the event loop.
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    valid = await asyncio.to_thread(_hasher.verify, password, password_hash or _DUMMY_HASH)
    return valid and password_hash is not None


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id, or None if the token is invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None