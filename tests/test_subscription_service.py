import os
import tempfile
import unittest

os.environ.setdefault("DATABASE_PATH", tempfile.gettempdir() + "/avava_vpn_test.db")

from subscription_service import SubscriptionService
from xcontroller_client import XControllerAPIError


class DummyDB:
    def __init__(self):
        self.created = []
        self.subscriptions = {}

    def create_subscription(self, **kwargs):
        self.created.append(kwargs)
        subscription_id = len(self.created)
        self.subscriptions[subscription_id] = {
            "id": subscription_id,
            "panel_subscription_id": kwargs.get("panel_subscription_id"),
            "panel_sub_token": kwargs.get("panel_sub_token"),
            "ends_at": kwargs.get("ends_at"),
        }
        return {"id": subscription_id, "status": "created"}

    def get_subscription_by_id(self, subscription_id):
        return self.subscriptions.get(subscription_id)

    def extend_subscription(self, subscription_id, extra_days):
        sub = self.subscriptions[subscription_id]
        sub["ends_at"] = "2026-01-01T00:00:00"
        return True

    def cancel_subscription(self, subscription_id, user_id):
        sub = self.subscriptions[subscription_id]
        sub["status"] = "cancelled"
        return True

    class conn:
        def execute(self, *args, **kwargs):
            return None

        def commit(self):
            return None


class DummyXC:
    def __init__(self, health_ok=True):
        self.created = []
        self.updated = []
        self.deleted = []
        self.health_ok = health_ok

    def create_user_subscription(
        self, telegram_user_id, tariff, preset_id=None, expiry_days=None
    ):
        self.created.append(
            {
                "user_id": telegram_user_id,
                "tariff": tariff,
                "preset_id": preset_id,
                "expiry_days": expiry_days,
            }
        )
        return {
            "success": True,
            "subscription": {
                "id": 99,
                "sub_token": "abc123",
                "uuid": "uuid-1",
                "email": "user@example.com",
            },
        }

    def health_check(self):
        if self.health_ok:
            return {"status": "healthy"}
        return {"status": "unhealthy", "error": "panel down"}

    def get_subscription_link(self, sub_token):
        return f"https://example.com/{sub_token}"

    def update_subscription(self, subscription_id, **kwargs):
        self.updated.append({"subscription_id": subscription_id, **kwargs})
        raise XControllerAPIError("boom", 500, {})

    def delete_subscription(self, subscription_id):
        self.deleted.append(subscription_id)
        return {"success": True}


class SubscriptionServiceTests(unittest.TestCase):
    def test_create_subscription_returns_success(self):
        db = DummyDB()
        xc = DummyXC()
        service = SubscriptionService(db, xc)

        result = service.create_subscription(
            user_id=1,
            tariff_id="basic",
            preset_id=2,
            expiry_days=30,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["subscription_id"], 1)
        self.assertEqual(result["panel_subscription_id"], 99)
        self.assertEqual(len(db.created), 1)

    def test_extend_subscription_reports_manual_sync_failure(self):
        db = DummyDB()
        xc = DummyXC()
        service = SubscriptionService(db, xc)

        db.subscriptions[1] = {
            "id": 1,
            "user_id": 1,
            "panel_subscription_id": 10,
            "panel_sub_token": "tok",
            "ends_at": "2026-01-01T00:00:00",
        }

        result = service.extend_subscription(1, 7)

        self.assertFalse(result["success"])
        self.assertTrue(result.get("manual_action_required"))
        self.assertNotIn("local_db_updated", result)

    def test_create_subscription_blocks_when_panel_unavailable(self):
        db = DummyDB()
        xc = DummyXC(health_ok=False)
        service = SubscriptionService(db, xc)

        result = service.create_subscription(user_id=2, tariff_id="basic")

        self.assertFalse(result["success"])
        self.assertEqual(result.get("status"), "panel_unavailable")
        self.assertEqual(len(db.created), 0)


if __name__ == "__main__":
    unittest.main()
