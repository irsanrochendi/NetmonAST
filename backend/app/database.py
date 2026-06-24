"""Database engine and session management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()

# ── Async engine (for FastAPI) ─────────────────────────────────────
async_engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ── Sync engine (for poller workers) ───────────────────────────────
# ── Sync engine (for poller workers) ───────────────────────────────
_sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql").replace("postgresql+aiosqlite", "sqlite")
sync_engine = create_engine(_sync_url, pool_size=10, max_overflow=5, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


def get_sync_db():
    """Synchronous session for poller workers."""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
