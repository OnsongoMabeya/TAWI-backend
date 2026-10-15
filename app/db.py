from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Single declarative base for every model."""

    pass


_state: dict[str, object] = {}


def init_db() -> None:
    """Create the engine and session factory. Called from the app lifespan so the
    connection pool always lives and dies inside one event loop."""
    engine: AsyncEngine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    _state["engine"] = engine
    _state["sessions"] = async_sessionmaker(engine, expire_on_commit=False)


async def shutdown_db() -> None:
    engine = _state.pop("engine", None)
    _state.pop("sessions", None)
    if engine is not None:
        await engine.dispose()


def _factory() -> async_sessionmaker[AsyncSession]:
    factory = _state.get("sessions")
    if factory is None:  # non-lifespan context (scripts, one-off tools)
        init_db()
        factory = _state["sessions"]
    return factory  # type: ignore[return-value]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a short-lived async session per request."""
    async with _factory()() as session:
        yield session
