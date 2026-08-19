import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.modules.pop("database", None)

from handlers import subscriptions as subscriptions_handlers


class DummyQuery:
    def __init__(self):
        self.edited_messages = []

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append({"text": text, "kwargs": kwargs})


class DummyUpdate:
    def __init__(self):
        self.callback_query = DummyQuery()


class SubscriptionHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_free_subscription_without_manager(self):
        update = DummyUpdate()
        with patch.object(
            subscriptions_handlers.app_context, "subscription_manager", None
        ):
            await subscriptions_handlers.handle_free_subscription(
                update,
                1,
                "trial",
                {"name": "Trial", "speed": "50", "duration_days": 3, "preset_id": 1},
            )

        self.assertIn(
            "Сервис подписок временно недоступен",
            update.callback_query.edited_messages[0]["text"],
        )

    async def test_handle_free_subscription_reports_manager_error(self):
        update = DummyUpdate()
        manager = SimpleNamespace(
            create_subscription=lambda **kwargs: {"success": False, "error": "boom"}
        )
        with (
            patch.object(
                subscriptions_handlers.app_context, "subscription_manager", manager
            ),
            patch.object(subscriptions_handlers.db, "reward_referrer") as reward_mock,
        ):
            await subscriptions_handlers.handle_free_subscription(
                update,
                1,
                "trial",
                {"name": "Trial", "speed": "50", "duration_days": 3, "preset_id": 1},
            )

        reward_mock.assert_not_called()
        self.assertIn(
            "Ошибка активации", update.callback_query.edited_messages[0]["text"]
        )

    async def test_handle_free_subscription_succeeds(self):
        update = DummyUpdate()
        manager = SimpleNamespace(
            create_subscription=lambda **kwargs: {
                "success": True,
                "sub_link": "https://example.com/link",
            }
        )
        with (
            patch.object(
                subscriptions_handlers.app_context, "subscription_manager", manager
            ),
            patch.object(subscriptions_handlers.db, "reward_referrer") as reward_mock,
        ):
            await subscriptions_handlers.handle_free_subscription(
                update,
                1,
                "trial",
                {"name": "Trial", "speed": "50", "duration_days": 3, "preset_id": 1},
            )

        reward_mock.assert_called_once_with(1, "trial")
        self.assertIn(
            "Подписка активирована", update.callback_query.edited_messages[0]["text"]
        )

    async def test_create_paid_subscription_without_manager(self):
        update = DummyUpdate()
        with patch.object(
            subscriptions_handlers.app_context, "subscription_manager", None
        ):
            await subscriptions_handlers.create_paid_subscription(
                update,
                1,
                "basic",
                {"name": "Basic", "speed": "100", "duration_days": 30, "preset_id": 2},
                "pay_1",
            )

        self.assertIn(
            "Сервис подписок недоступен",
            update.callback_query.edited_messages[0]["text"],
        )

    async def test_handle_tariff_change_without_manager(self):
        update = DummyUpdate()
        with patch.object(
            subscriptions_handlers.app_context, "subscription_manager", None
        ):
            await subscriptions_handlers.handle_tariff_change(
                update,
                1,
                10,
                "premium",
                {
                    "name": "Premium",
                    "speed": "100",
                    "duration_days": 30,
                    "preset_id": 3,
                },
            )

        self.assertIn(
            "Сервис подписок недоступен",
            update.callback_query.edited_messages[0]["text"],
        )

    async def test_handle_tariff_change_reports_manager_error(self):
        update = DummyUpdate()
        manager = SimpleNamespace(
            change_subscription=lambda *args, **kwargs: {
                "success": False,
                "error": "boom",
            }
        )
        with patch.object(
            subscriptions_handlers.app_context, "subscription_manager", manager
        ):
            await subscriptions_handlers.handle_tariff_change(
                update,
                1,
                10,
                "premium",
                {
                    "name": "Premium",
                    "speed": "100",
                    "duration_days": 30,
                    "preset_id": 3,
                },
            )

        self.assertIn(
            "Ошибка смены тарифа", update.callback_query.edited_messages[0]["text"]
        )


if __name__ == "__main__":
    unittest.main()
