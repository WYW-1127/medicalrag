from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}


def get_engine(url: str) -> AsyncEngine:
    if url not in _engines:
        _engines[url] = create_async_engine(url, pool_pre_ping=True)
    return _engines[url]


def get_session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    if url not in _session_factories:
        _session_factories[url] = async_sessionmaker(
            get_engine(url), expire_on_commit=False
        )
    return _session_factories[url]


async def get_session() -> AsyncIterator[AsyncSession]:
    from app.core.config import get_settings

    factory = get_session_factory(get_settings().database_url)
    async with factory() as session:
        yield session
