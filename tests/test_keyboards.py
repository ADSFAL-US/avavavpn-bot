import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_PATH", tempfile.gettempdir() + "/avava_vpn_test.db")

from keyboards import (
    build_admin_stats,
    build_admin_subscriptions,
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
        self.db_mock.get_total_subscription_count.return_value = 3
        self.db_mock.get_expired_subscription_count.return_value = 1
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

    def test_build_admin_stats_shows_status_breakdown(self):
        self.db_mock.get_subscription_stats.return_value = {
            "basic": {
                "name": "Basic",
                "total_count": 5,
                "active_count": 3,
                "expired_count": 2,
            }
        }
        text, _keyboard = build_admin_stats()
        self.assertIn("Всего подписок: <b>3</b>", text)
        self.assertIn("Активных подписок: <b>1</b>", text)
        self.assertIn("Просроченных подписок: <b>1</b>", text)
        self.assertIn("Basic: <b>5</b> / <b>3</b> / <b>2</b>", text)

    def test_build_admin_subscriptions_shows_status_breakdown(self):
        self.db_mock.get_subscription_stats.return_value = {
            "basic": {
                "name": "Basic",
                "total_count": 5,
                "active_count": 3,
                "expired_count": 2,
            }
        }
        text, _keyboard = build_admin_subscriptions()
        self.assertIn("📦 5 │ 🟢 3 │ 🔴 2", text)

    def test_build_admin_stats_average_profit(self):
        self.db_mock.get_subscription_stats.return_value = {
            "trial": {
                "name": "Trial",
                "total_count": 5,
                "active_count": 5,
                "expired_count": 0,
            },
            "basic": {
                "name": "Basic",
                "total_count": 2,
                "active_count": 2,
                "expired_count": 0,
            },
            "premium": {
                "name": "Premium",
                "total_count": 1,
                "active_count": 1,
                "expired_count": 0,
            },
        }
        self.db_mock.get_active_subscription_count.return_value = 8

        with patch("keyboards.config.TAX_PERCENT", 0):
            text, _keyboard = build_admin_stats()

        # (2 * 99 + 1 * 199 + 5 * 0) / 8 = 49.625 -> 49.62
        self.assertIn("Средняя прибыль с подписки: <b>49.62 ₽</b>", text)

    def test_build_admin_stats_average_profit_with_tax(self):
        self.db_mock.get_subscription_stats.return_value = {
            "basic": {
                "name": "Basic",
                "total_count": 1,
                "active_count": 1,
                "expired_count": 0,
            },
        }
        self.db_mock.get_active_subscription_count.return_value = 1

        with patch("keyboards.config.TAX_PERCENT", 10):
            text, _keyboard = build_admin_stats()

        # 99 * 0.9 = 89.1
        self.assertIn("Средняя прибыль с подписки: <b>89.10 ₽</b>", text)

    def test_build_admin_stats_average_profit_no_active(self):
        self.db_mock.get_subscription_stats.return_value = {}
        self.db_mock.get_active_subscription_count.return_value = 0

        text, _keyboard = build_admin_stats()

        self.assertIn("Средняя прибыль с подписки: <b>0.00 ₽</b>", text)


if __name__ == "__main__":
    unittest.main()
