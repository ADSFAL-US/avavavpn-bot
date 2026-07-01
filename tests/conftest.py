"""Pytest configuration and fixtures."""
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from db.engine import Base
from db.models import User, Subscription, Payment, AdminLog, VPNConnection, SpeedUpgrade
from db.repositories.user_repo import UserRepository
from db.repositories.subscription_repo import SubscriptionRepository
from db.repositories.payment_repo import PaymentRepository
from db.repositories.admin_repo import AdminRepository
from db.context import DatabaseContext
from database import TARIFFS


# Use in-memory SQLite for tests - each test gets fresh DB
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine - fresh for each test."""
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine):
    """Create test database session - fresh for each test."""
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def user_repo(test_session):
    """Create user repository."""
    return UserRepository(test_session)


@pytest_asyncio.fixture(scope="function")
async def subscription_repo(test_session):
    """Create subscription repository."""
    return SubscriptionRepository(test_session)


@pytest_asyncio.fixture(scope="function")
async def payment_repo(test_session):
    """Create payment repository."""
    return PaymentRepository(test_session)


@pytest_asyncio.fixture(scope="function")
async def admin_repo(test_session):
    """Create admin repository."""
    return AdminRepository(test_session)


@pytest_asyncio.fixture(scope="function")
async def db_context():
    """Create database context with all repositories - fresh for each test."""
    context = DatabaseContext()
    yield context
    # Cleanup is handled by context manager


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "user_id": 123456789,
        "first_name": "Test",
        "username": "testuser",
        "last_name": "User",
        "referred_by": None,
    }


@pytest.fixture
def sample_referrer_data():
    """Sample referrer user data."""
    return {
        "user_id": 987654321,
        "first_name": "Referrer",
        "username": "referrer",
        "last_name": "User",
        "referred_by": None,
    }