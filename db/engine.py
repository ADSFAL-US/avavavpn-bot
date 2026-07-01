"""Async SQLAlchemy engine and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_PATH
import os


class Base(DeclarativeBase):
    pass


# Convert sqlite path to async URL: /path/to/db -> sqlite+aiosqlite:///path/to/db
if DATABASE_PATH.startswith("sqlite:///"):
    ASYNC_DB_URL = DATABASE_PATH.replace("sqlite:///", "sqlite+aiosqlite:///")
elif DATABASE_PATH.startswith("/") or DATABASE_PATH.startswith("./") or ":" in DATABASE_PATH.split("/")[0]:
    # It's a file path
    ASYNC_DB_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"
else:
    ASYNC_DB_URL = DATABASE_PATH

# Ensure directory exists
db_dir = os.path.dirname(DATABASE_PATH.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", ""))
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

engine = create_async_engine(
    ASYNC_DB_URL,
    echo=False,  # Set True for SQL debugging
    pool_pre_ping=True,
    connect_args={"check_same_thread": False},  # aiosqlite handles this
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Dependency for FastAPI-style dependency injection or manual use."""
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    await engine.dispose()
