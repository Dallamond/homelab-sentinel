"""
Sesión y engine async de SQLAlchemy, más helper de inicialización de esquema.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _ensure_sqlite_dir() -> None:
    """Crea el directorio padre de la DB SQLite si la URL apunta a un archivo."""
    url = settings.database_url
    if "sqlite" not in url:
        return
    # sqlite+aiosqlite:///./data/x.db  -> ./data/x.db
    # sqlite+aiosqlite:////app/data/x.db -> /app/data/x.db
    if "///" not in url:
        return
    path = Path(url.split("///", 1)[-1])
    if path.parent and str(path.parent) not in (".", ""):
        path.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    _ensure_sqlite_dir()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
