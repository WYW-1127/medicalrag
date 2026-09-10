"""FastAPI 依赖：当前登录用户（演示级 JWT，无角色体系）。"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证凭据")
    username = decode_token(credentials.credentials)
    if username is None:
        raise HTTPException(status_code=401, detail="凭据无效或已过期")

    from sqlalchemy import select

    factory = request.app.state.session_factory()
    async with factory() as session:
        user = (
            (await session.execute(select(User).where(User.username == username)))
            .scalars()
            .one_or_none()
        )
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    found: User = user  # scalars() 返回 Any，显式标注收窄
    return found
