"""Test environment shared by every test.

The suite always runs against a real PostgreSQL (`tawi_test`, created next to
the dev database by `docker compose up db`). Dialect features like citext and
value-backed enums behave differently on SQLite, so no test runs anywhere else.
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest

# Environment first: app.config caches Settings on first import.
os.environ["TAWI_ENVIRONMENT"] = "ci"
os.environ["TAWI_DATABASE_URL"] = os.environ.get(
    "TAWI_TEST_DATABASE_URL", "postgresql+asyncpg://tawi:tawi@127.0.0.1:5433/tawi_test"
)

import asyncpg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.db import Base  # noqa: E402  # import registers table metadata for truncation

TEST_URL = os.environ["TAWI_DATABASE_URL"]
MAINTENANCE_URL = TEST_URL.replace("/tawi_test", "/tawi").replace("+asyncpg", "")
TEST_DSN = TEST_URL.replace("+asyncpg", "")


async def _ensure_database() -> None:
    conn = await asyncpg.connect(MAINTENANCE_URL)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'tawi_test'")
        if not exists:
            await conn.execute("CREATE DATABASE tawi_test OWNER tawi")
    finally:
        await conn.close()


async def _reset_schema() -> None:
    conn = await asyncpg.connect(TEST_DSN)
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database():
    """Fresh schema per run: drop everything, then run the real migrations.
    A green run therefore proves the migration chain builds cleanly from scratch."""
    asyncio.run(_ensure_database())
    asyncio.run(_reset_schema())
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Per-test session; tables are cleared after every test so tests can be
    read independently and reordered freely."""
    engine = create_async_engine(TEST_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()


@pytest.fixture()
def client(migrated_test_database) -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
