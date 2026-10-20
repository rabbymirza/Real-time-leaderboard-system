from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, session: AsyncSession = Depends(get_session)):
    user = User(username=body.username, password_hash=await hash_password(body.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # The unique index is the real guard, so this is race-safe.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    return user


@router.post("/token", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    user = await session.scalar(select(User).where(User.username == form.username.lower()))
    ok = await verify_password(form.password, user.password_hash if user else None)
    if user is None or not ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))