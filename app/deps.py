import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import User
from app.security import decode_access_token

# tokenUrl makes the "Authorize" button in /docs work.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
admin_key_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if user_id is None:
        raise unauthorized
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


async def require_admin(token: str | None = Security(admin_key_header)) -> None:
    """Guard for ops-only routes. Disabled entirely until ADMIN_TOKEN is set."""
    expected = settings.admin_token
    if not expected or not token or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")