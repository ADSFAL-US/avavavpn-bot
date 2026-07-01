"""Compatibility layer for database - uses new async repositories but provides sync-like interface."""
import logging
from db.context import DatabaseContext

logger = logging.getLogger(__name__)


class AsyncDatabaseCompat:
    """Compatibility wrapper that uses async repositories internally."""

    def __init__(self):
        self._db_context = None

    async def _get_db(self):
        if self._db_context is None:
            self._db_context = DatabaseContext()
            await self._db_context.__aenter__()
        return self._db_context

    async def close(self):
        if self._db_context:
            await self._db_context.__aexit__(None, None, None)
            self._db_context = None

    # Sync-compatible methods (for gradual migration)
    def get_or_create_user(self, user_data):
        raise NotImplementedError("Use async version with 'async with db() as db:'")

    def is_admin(self, user_id):
        raise NotImplementedError("Use async version")

    def set_admin(self, user_id):
        raise NotImplementedError("Use async version")

    def remove_admin(self, user_id):
        raise NotImplementedError("Use async version")

    def get_active_subscription(self, user_id):
        raise NotImplementedError("Use async version")

    def get_subscription_by_id(self, subscription_id):
        raise NotImplementedError("Use async version")

    def get_user_subscriptions(self, user_id):
        raise NotImplementedError("Use async version")

    def create_subscription(self, **kwargs):
        raise NotImplementedError("Use async version")

    def cancel_subscription(self, subscription_id, user_id):
        raise NotImplementedError("Use async version")

    def cancel_subscription_by_tariff(self, tariff_id, user_id=None):
        raise NotImplementedError("Use async version")

    def update_speed(self, subscription_id, speed_mbps):
        raise NotImplementedError("Use async version")

    def update_traffic_used(self, user_id, bytes_transferred):
        raise NotImplementedError("Use async version")

    def get_user_count(self):
        raise NotImplementedError("Use async version")

    def get_active_subscription_count(self):
        raise NotImplementedError("Use async version")

    def get_all_users(self, offset=0, limit=100):
        raise NotImplementedError("Use async version")

    def get_user_by_id(self, user_id):
        raise NotImplementedError("Use async version")

    def ban_user(self, user_id, reason=None, duration_days=None):
        raise NotImplementedError("Use async version")

    def unban_user(self, user_id):
        raise NotImplementedError("Use async version")

    def log_admin_action(self, admin_id, action, target_user_id=None, details=None):
        raise NotImplementedError("Use async version")

    def get_admin_logs(self, limit=50):
        raise NotImplementedError("Use async version")

    def has_user_ever_had_tariff(self, user_id: int, tariff_id: str) -> bool:
        raise NotImplementedError("Use async version")

    def add_referral_days(self, user_id, days):
        raise NotImplementedError("Use async version")

    def reward_referrer(self, user_id, tariff_id):
        raise NotImplementedError("Use async version")

    def extend_subscription(self, subscription_id, extra_days):
        raise NotImplementedError("Use async version")

    def set_discount_used(self, user_id):
        raise NotImplementedError("Use async version")

    def get_subscription_stats(self):
        raise NotImplementedError("Use async version")


# Global instance for backward compat (DEPRECATED)
db = AsyncDatabaseCompat()
