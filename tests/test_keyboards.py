import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_PATH", tempfile.gettempdir() + "/avava_vpn_test.db")

from keyboards import (
    build_main_menu,
    build_referral_menu,
    build_tariff_detail,
    build_tariffs_menu,
    build_use_days_menu,
)


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("keyboards.db")
        self.db_mock = self.patcher.start()
        self.db_mock.get_active_subscription.return_value = None
        self.db_mock.get_user_by_id.return_value = {
            "user_id": 1,
            "referral_code": "ABC",
            "referral_days": 3,
        }
        self.db_mock.get_subscription_stats.return_value = {}
        self.db_mock.get_user_count.return_value = 1
        self.db_mock.get_active_subscription_count.return_value = 1
        self.db_mock.get_all_users.return_value = []
        self.db_mock.get_admin_logs.return_value = []
        self.addCleanup(self.patcher.stop)

    def test_build_main_menu_without_subscription(self):
        text, keyboard = build_main_menu(1)
        self.assertIn("Avava VPN Bot", text)
        self.assertIn("Нет активной подписки", text)
        self.assertGreaterEqual(len(keyboard.inline_keyboard), 3)

    def test_build_referral_menu_with_days(self):
        text, keyboard = build_referral_menu(1)
        self.assertIn("Реферальная система", text)
        self.assertIn("https://t.me/", text)
        self.assertGreaterEqual(len(keyboard.inline_keyboard), 2)

    def test_build_use_days_menu_without_subscription(self):
        text, _keyboard = build_use_days_menu(1)
        self.assertIn("У вас накоплено", text)
        self.assertIn("нет накопленных дней", text.lower())

    def test_build_tariffs_menu_contains_all_tariffs(self):
        text, keyboard = build_tariffs_menu()
        self.assertIn("Выберите тариф", text)
        self.assertGreaterEqual(len(keyboard.inline_keyboard), 1)

    def test_build_tariff_detail_for_unknown_tariff(self):
        text, _keyboard = build_tariff_detail("unknown", 1)
        self.assertEqual(text, "❌ Тариф не найден")


if __name__ == "__main__":
    unittest.main()
