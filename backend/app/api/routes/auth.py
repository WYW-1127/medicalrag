from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.security import create_access_token, hash_password, verify_password
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=72)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105


class UserOut(BaseModel):
    id: int
    username: str


def _session(request: Request) -> Any:
    return request.app.state.session_factory()


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, request: Request) -> User:
    factory = _session(request)
    async with factory() as session:
        exists = (
            await session.execute(select(User).where(User.username == body.username))
        ).scalars()
        if exists.one_or_none() is not None:
            raise HTTPException(status_code=409, detail="用户名已存在")
        user = User(username=body.username, password_hash=hash_password(body.password))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@router.post("/login", response_model=TokenOut)
async def login(body: RegisterIn, request: Request) -> TokenOut:
    factory = _session(request)
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.username == body.username))
        ).scalars().one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenOut(access_token=create_access_token(body.username))
