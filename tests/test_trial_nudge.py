import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.modules.pop("database", None)

from database import Database


class StaleTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="avava-trial-", dir=tempfile.gettempdir())
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = Database(self.db_path)
        self.db.get_or_create_user({"user_id": 1, "first_name": "Stale"})
        self.db.get_or_create_user({"user_id": 2, "first_name": "Upgraded"})
        self.db.get_or_create_user({"user_id": 3, "first_name": "Cancelled"})
        self.db.get_or_create_user({"user_id": 4, "first_name": "ActiveTrial"})
        self.db.get_or_create_user({"user_id": 5, "first_name": "Muted"})

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_trial(self, user_id, ends_at):
        return self.db.create_subscription(
            user_id=user_id, tariff_id="trial", ends_at=ends_at
        )

    def test_stale_trial_user_detected(self):
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        self._create_trial(1, expired)
        users = self.db.get_stale_trial_users()
        self.assertEqual([u["user_id"] for u in users], [1])

    def test_upgraded_user_excluded(self):
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        self._create_trial(2, expired)
        self.db.create_subscription(user_id=2, tariff_id="basic")
        users = self.db.get_stale_trial_users()
        self.assertEqual(users, [])

    def test_cancelled_trial_excluded(self):
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        sub = self._create_trial(3, expired)
        self.db.cancel_subscription(sub["id"], 3)
        users = self.db.get_stale_trial_users()
        self.assertEqual(users, [])

    def test_active_trial_excluded(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        self._create_trial(4, future)
        users = self.db.get_stale_trial_users()
        self.assertEqual(users, [])

    def test_muted_user_excluded(self):
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        self._create_trial(5, expired)
        self.db.set_trial_nudge_muted(5, True)
        users = self.db.get_stale_trial_users()
        self.assertEqual(users, [])

    def test_mute_toggle(self):
        self.db.set_trial_nudge_muted(1, True)
        user = self.db.get_user_by_id(1)
        self.assertEqual(user["trial_nudge_muted"], 1)
        self.db.set_trial_nudge_muted(1, False)
        user = self.db.get_user_by_id(1)
        self.assertEqual(user["trial_nudge_muted"], 0)


if __name__ == "__main__":
    unittest.main()