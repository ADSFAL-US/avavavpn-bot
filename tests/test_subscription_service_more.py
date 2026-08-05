import unittest
from datetime import datetime

from subscription_service import SubscriptionService
from xcontroller_client import XControllerAPIError


class DummyDB:
    def __init__(self):
        self.created = []
        self.subscriptions = {}
        self.conn = self.Conn()

    def create_subscription(self, **kwargs):
        self.created.append(kwargs)
        sub_id = len(self.created)
        self.subscriptions[sub_id] = {
            "id": sub_id,
            "user_id": kwargs.get("user_id"),
            "tariff_id": kwargs.get("tariff_id"),
            "panel_subscription_id": kwargs.get("panel_subscription_id"),
            "panel_sub_token": kwargs.get("panel_sub_token"),
            "ends_at": kwargs.get("ends_at"),
        }
        return {"id": sub_id, "status": "created"}

    def get_subscription_by_id(self, subscription_id):
        return self.subscriptions.get(subscription_id)

    def extend_subscription(self, subscription_id, extra_days):
        sub = self.subscriptions[subscription_id]
        sub["ends_at"] = "2026-01-01T00:00:00"
        return True

    def cancel_subscription(self, subscription_id, user_id):
        sub = self.subscriptions[subscription_id]
        sub["status"] = "cancelled"
        sub["user_id"] = user_id
        return True

    class Conn:
        def execute(self, *args, **kwargs):
            return None

        def commit(self):
            return None


class DummyXC:
    def __init__(self, health_ok=True, create_success=True, create_error=None):
        self.health_ok = health_ok
        self.create_success = create_success
        self.create_error = create_error
        self.created = []
        self.deleted = []

    def health_check(self):
        if self.health_ok:
            return {"status": "healthy"}
        return {"status": "unhealthy", "error": "panel down"}

    def create_user_subscription(self, **kwargs):
        self.created.append(kwargs)
        if self.create_error:
            raise self.create_error
        if self.create_success:
            return {
                "success": True,
                "subscription": {"id": 77, "sub_token": "tok-1", "uuid": "u1", "email": "user@example.com"},
            }
        return {"success": False, "error": "panel denied"}

    def get_subscription_link(self, sub_token):
        return f"https://example.com/{sub_token}"

    def update_subscription(self, **kwargs):
        raise XControllerAPIError("boom", 500, {})

    def delete_subscription(self, subscription_id):
        self.deleted.append(subscription_id)
        return {"success": True}


class SubscriptionServiceMoreTests(unittest.TestCase):
    def test_create_subscription_returns_invalid_tariff_error(self):
        service = SubscriptionService(DummyDB(), DummyXC())

        result = service.create_subscription(user_id=1, tariff_id="unknown")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Invalid tariff")
        self.assertFalse(result["retryable"])

    def test_create_subscription_returns_panel_error_when_create_fails(self):
        service = SubscriptionService(DummyDB(), DummyXC(create_success=False))

        result = service.create_subscription(user_id=1, tariff_id="basic")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Не удалось создать подписку в панели.")
        self.assertTrue(result["manual_action_required"])

    def test_cancel_subscription_handles_missing_panel_subscription(self):
        db = DummyDB()
        db.subscriptions[1] = {
            "id": 1,
            "user_id": 42,
            "panel_subscription_id": None,
            "panel_sub_token": None,
            "ends_at": None,
        }
        service = SubscriptionService(db, DummyXC())

        result = service.cancel_subscription(1)

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(db.subscriptions[1]["status"], "cancelled")

    def test_change_subscription_uses_fallback_when_update_raises(self):
        db = DummyDB()
        db.subscriptions[1] = {
            "id": 1,
            "user_id": 42,
            "tariff_id": "basic",
            "panel_subscription_id": 10,
            "panel_sub_token": "token",
            "ends_at": None,
        }
        xc = DummyXC()
        service = SubscriptionService(db, xc)

        result = service.change_subscription(1, "premium", expiry_days=10)

        self.assertTrue(result["success"])
        self.assertEqual(result["new_tariff"], "premium")
        self.assertEqual(xc.deleted[0], 10)


if __name__ == "__main__":
    unittest.main()
