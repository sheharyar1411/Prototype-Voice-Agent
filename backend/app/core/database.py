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
# Engine configuration — adapt connection args based on the database backend.
# Automatically normalize postgres:// and postgresql:// to postgresql+asyncpg://
# ---------------------------------------------------------------------------
_raw_db_url = settings.database_url.strip()
if _raw_db_url.startswith("postgres://"):
    _db_url = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgresql://") and not _raw_db_url.startswith("postgresql+"):
    _db_url = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    _db_url = _raw_db_url

_connect_args: dict = {}
_engine_kwargs: dict = {
    "echo": settings.debug and settings.app_env == "local",
}

if _db_url.startswith("sqlite"):
    # SQLite requires check_same_thread=False for async usage.
    _connect_args["check_same_thread"] = False
else:
    # PostgreSQL: enable connection health checks to recover from stale conns.
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(
    _db_url,
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
    import os
    if _db_url.startswith("sqlite"):
        raw_path = _db_url.split(":///")[-1]
        if raw_path and not raw_path.startswith(":memory:"):
            db_dir = os.path.dirname(raw_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

    from app.models.patient import Base  # noqa: F811 — deferred import

    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")
