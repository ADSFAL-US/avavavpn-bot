import os
import tempfile
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_PATH", tempfile.gettempdir() + "/avava_vpn_test.db")

import sys


class FakeDB:
    def __init__(self):
        self.conn = SimpleNamespace(cursor=lambda: None)

    def is_admin(self, user_id):
        return False

    def get_user_by_id(self, user_id):
        return None

    def get_subscription_by_id(self, subscription_id):
        return None

    def get_active_subscription(self, user_id):
        return None

    def cancel_subscription(self, subscription_id, user_id):
        return True

    def unban_user(self, user_id):
        return True

    def log_admin_action(self, admin_id, action, target_user_id):
        return True

    def set_admin(self, user_id):
        return True

    def remove_admin(self, user_id):
        return True


fake_db_module = ModuleType("database")
fake_db_module.db = FakeDB()
fake_db_module.TARIFFS = {
    "basic": {
        "id": "basic",
        "name": "Basic",
        "price": 0,
        "currency": "рублей",
        "duration_days": 30,
    },
    "premium": {
        "id": "premium",
        "name": "Premium",
        "price": 199,
        "currency": "рублей",
        "duration_days": 30,
    },
    "trial": {
        "id": "trial",
        "name": "Trial",
        "price": 0,
        "currency": "рублей",
        "duration_days": 3,
    },
}

with patch.dict(sys.modules, {"database": fake_db_module}):
    from handlers import admin as admin_handlers
    from utils import (
        STATE_ADMIN_GIVE_DAYS,
        STATE_BAN_REASON,
        STATE_FIND_USER,
        STATE_SIMULATE_REFERRAL_USERID,
    )


class DummyQuery:
    def __init__(self):
        self.edited_messages = []

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append({"text": text, "kwargs": kwargs})


class DummyUpdate:
    def __init__(self):
        self.callback_query = DummyQuery()


class AdminHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = SimpleNamespace(user_data={})
        self.update = DummyUpdate()

    async def test_handle_admin_give_subscription_sets_state(self):
        with patch.object(
            admin_handlers, "build_admin_panel", return_value=("panel", None)
        ):
            await admin_handlers.handle_admin_panel(self.update, self.context, 1)

        self.assertEqual(self.update.callback_query.edited_messages[0]["text"], "panel")

    async def test_handle_admin_give_tariff_requires_target_user(self):
        await admin_handlers.handle_admin_give_tariff(
            self.update, self.context, 1, "basic"
        )

        self.assertIn(
            "ID пользователя не найден",
            self.update.callback_query.edited_messages[0]["text"],
        )

    async def test_handle_admin_give_tariff_sets_admin_state(self):
        self.context.user_data["admin_give_target"] = 42
        await admin_handlers.handle_admin_give_tariff(
            self.update, self.context, 1, "basic"
        )

        self.assertEqual(self.context.user_data["admin_give_tariff"], "basic")
        self.assertEqual(self.context.user_data["state"], STATE_ADMIN_GIVE_DAYS)
        self.assertIn(
            "Введите количество дней",
            self.update.callback_query.edited_messages[0]["text"],
        )

    async def test_handle_admin_find_sets_state(self):
        await admin_handlers.handle_admin_find(self.update, self.context, 1)

        self.assertEqual(self.context.user_data["state"], STATE_FIND_USER)

    async def test_handle_admin_simulate_referral_sets_state(self):
        await admin_handlers.handle_admin_simulate_referral(
            self.update, self.context, 1
        )

        self.assertEqual(
            self.context.user_data["state"], STATE_SIMULATE_REFERRAL_USERID
        )

    async def test_handle_ban_sets_target_and_reason_state(self):
        await admin_handlers.handle_ban(self.update, self.context, 1, "99")

        self.assertEqual(self.context.user_data["ban_target"], 99)
        self.assertEqual(self.context.user_data["state"], STATE_BAN_REASON)

    async def test_handle_unban_logs_and_updates(self):
        with (
            patch.object(admin_handlers.db, "unban_user") as unban_mock,
            patch.object(admin_handlers.db, "log_admin_action") as log_mock,
        ):
            await admin_handlers.handle_unban(self.update, self.context, 1, "77")

        unban_mock.assert_called_once_with(77)
        log_mock.assert_called_once_with(1, "unban", 77)

    async def test_handle_makeadmin_logs_and_updates(self):
        with (
            patch.object(admin_handlers.db, "set_admin") as set_admin_mock,
            patch.object(admin_handlers.db, "log_admin_action") as log_mock,
        ):
            await admin_handlers.handle_makeadmin(self.update, self.context, 1, "88")

        set_admin_mock.assert_called_once_with(88)
        log_mock.assert_called_once_with(1, "make_admin", 88)

    async def test_handle_removeadmin_logs_and_updates(self):
        with (
            patch.object(admin_handlers.db, "remove_admin") as remove_admin_mock,
            patch.object(admin_handlers.db, "log_admin_action") as log_mock,
        ):
            await admin_handlers.handle_removeadmin(self.update, self.context, 1, "99")

        remove_admin_mock.assert_called_once_with(99)
        log_mock.assert_called_once_with(1, "remove_admin", 99)


if __name__ == "__main__":
    unittest.main()
