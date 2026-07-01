"""Database context manager for handlers - provides async repositories."""
from db.engine import async_session_maker
from db.repositories.user_repo import UserRepository
from db.repositories.subscription_repo import SubscriptionRepository
from db.repositories.payment_repo import PaymentRepository
from db.repositories.admin_repo import AdminRepository
import logging

logger = logging.getLogger(__name__)


class DatabaseContext:
    """Async context manager providing repository access."""

    def __init__(self, session=None):
        self._session = session
        self._own_session = session is None
        self.users = None
        self.subscriptions = None
        self.payments = None
        self.admin = None

    async def __aenter__(self):
        if self._own_session:
            self._session = async_session_maker()
        self.users = UserRepository(self._session)
        self.subscriptions = SubscriptionRepository(self._session)
        self.payments = PaymentRepository(self._session)
        self.admin = AdminRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self._session.rollback()
            logger.error(f"Database transaction rolled back: {exc_val}")
        else:
            await self._session.commit()
        if self._own_session:
            await self._session.close()

    async def commit(self):
        await self._session.commit()

    async def rollback(self):
        await self._session.rollback()


async def get_db():
    """Async context manager for database access."""
    async with DatabaseContext() as db:
        yield db
