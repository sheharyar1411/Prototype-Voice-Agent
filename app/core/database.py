"""
Async SQLAlchemy engine, session factory, and request-scoped dependency.

FLOW MAP:
  get_settings → create_async_engine → get_db (FastAPI Depends) → routers / services

KEY DETAILS:
  - Supports both PostgreSQL (asyncpg) and SQLite (aiosqlite) via DATABASE_URL
  - get_db commits on success, rolls back on error (request-scoped transaction)
  - init_db creates ORM metadata tables; production migrations via Alembic
  - SQLite requires special connect_args for async compatibility
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Engine configuration — adapt connection args based on the database backend.
# ---------------------------------------------------------------------------
_connect_args: dict = {}
_engine_kwargs: dict = {
    "echo": settings.debug and settings.app_env == "local",
}

if settings.database_url.startswith("sqlite"):
    # SQLite requires check_same_thread=False for async usage.
    _connect_args["check_same_thread"] = False
else:
    # PostgreSQL: enable connection health checks to recover from stale conns.
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(
    settings.database_url,
    connect_args=_connect_args,
    **_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a scoped async database session.

    Commits the transaction on success, rolls back on any exception,
    and always closes the session when the request completes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Create all ORM-defined tables if they don't exist.

    This is a convenience for first-run bootstrapping. In production,
    schema evolution is managed by Alembic migrations.
    """
    from app.models.patient import Base  # noqa: F811 — deferred import

    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")
