"""Async DB engine. SQLite locally, Postgres (Supabase) in production."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings

settings = get_settings()
url = settings.DATABASE_URL
if url.startswith("sqlite:///"):
    url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in url else {"statement_cache_size": 0}
engine = create_async_engine(url, echo=False, connect_args=connect_args, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as s:
        yield s


async def init_db():
    from app.models.models import Base as ModelBase  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
