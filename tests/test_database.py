import os
import sys
import tempfile
import unittest

sys.modules.pop("database", None)

from database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="avava-db-", dir=tempfile.gettempdir())
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = Database(self.db_path)
        self.db.get_or_create_user({"user_id": 1, "first_name": "Test"})
        self.db.get_or_create_user({"user_id": 9, "first_name": "Referrer"})

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_and_get_subscription(self):
        created = self.db.create_subscription(user_id=1, tariff_id="basic")
        self.assertEqual(created["status"], "created")

        sub = self.db.get_subscription_by_id(created["id"])
        self.assertEqual(sub["user_id"], 1)
        self.assertEqual(sub["tariff_id"], "basic")
        self.assertEqual(sub["status"], "active")

    def test_create_subscription_raises_for_unknown_tariff(self):
        with self.assertRaises(ValueError):
            self.db.create_subscription(user_id=1, tariff_id="unknown")

    def test_cancel_and_extend_subscription(self):
        created = self.db.create_subscription(user_id=1, tariff_id="basic")
        self.assertTrue(self.db.cancel_subscription(created["id"], 1))
        self.assertTrue(self.db.extend_subscription(created["id"], 5))

        sub = self.db.get_subscription_by_id(created["id"])
        self.assertEqual(sub["status"], "cancelled")
        self.assertIn("T", sub["ends_at"])

    def test_user_and_admin_helpers(self):
        user = self.db.get_or_create_user({"user_id": 7, "first_name": "A"})
        self.assertEqual(user["user_id"], 7)
        self.assertTrue(user["referral_code"].startswith("REF_7_"))

        self.db.set_admin(7)
        self.assertTrue(self.db.is_admin(7))
        self.db.remove_admin(7)
        self.assertFalse(self.db.is_admin(7))

        self.db.ban_user(7, reason="spam", duration_days=1)
        user_after_ban = self.db.get_user_by_id(7)
        self.assertEqual(user_after_ban["banned"], 1)
        self.assertEqual(user_after_ban["ban_reason"], "spam")

    def test_referral_and_discount_helpers(self):
        self.db.get_or_create_user({"user_id": 8, "first_name": "B", "referred_by": 9})

        self.assertTrue(self.db.reward_referrer(8, "basic"))

        referrer = self.db.get_user_by_id(9)
        self.assertGreaterEqual(referrer["referral_days"], 7)

    def test_traffic_and_stats_helpers(self):
        self.db.create_subscription(user_id=1, tariff_id="basic")
        self.db.update_traffic_used(1, 1024 * 1024)
        self.db.update_traffic_used(1, 2 * 1024 * 1024)

        stats = self.db.get_subscription_stats()
        self.assertIn("basic", stats)
        self.assertEqual(stats["basic"]["active_count"], 1)

    def test_populate_missing_panel_subscription_ids(self):
        class DummyXController:
            def list_subscriptions(self):
                return [{"id": 123, "sub_token": "abc"}]

        self.db.create_subscription(user_id=1, tariff_id="basic", panel_sub_token="abc")
        result = self.db.populate_missing_panel_subscription_ids(DummyXController())

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["failed_count"], 0)

    def test_close_closes_connection(self):
        self.db.close()
        self.assertIsNone(self.db.conn)


if __name__ == "__main__":
    unittest.main()
