import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("DATABASE_PATH", tempfile.gettempdir() + "/avava_vpn_test.db")

import sys
from types import ModuleType

fake_db_module = ModuleType("database")


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
    import app_context
    from handlers import navigation as navigation_handlers
    from handlers import payments as payments_handlers

app_context.payment_storage = SimpleNamespace(
    get_payment_by_order=lambda order_id: None,
    update_payment_status=lambda *args, **kwargs: None,
    create_payment_record=lambda *args, **kwargs: None,
)
app_context.yookassa = SimpleNamespace(
    check_payment=lambda payment_id: {"status": "pending", "paid": False},
    capture_payment=lambda payment_id: {"status": "succeeded"},
    create_payment=lambda *args, **kwargs: {
        "success": True,
        "payment_id": "pay_1",
        "payment_url": "https://example.com",
    },
)
app_context.subscription_manager = None


class DummyQuery:
    def __init__(self):
        self.edited_messages = []
        self.answers = []

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append({"text": text, "kwargs": kwargs})

    async def answer(self, text, **kwargs):
        self.answers.append({"text": text, "kwargs": kwargs})


class DummyUpdate:
    def __init__(self):
        self.callback_query = DummyQuery()


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_use_days_apply_handles_missing_user_info(self):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})

        with (
            patch.object(
                navigation_handlers.db,
                "get_subscription_by_id",
                return_value={"id": 1, "user_id": 42, "tariff_id": "basic"},
            ),
            patch.object(navigation_handlers.db, "get_user_by_id", return_value=None),
            patch.object(navigation_handlers.app_context, "subscription_manager", None),
        ):
            await navigation_handlers.handle_use_days_apply(update, context, 42, "1")

        self.assertEqual(
            update.callback_query.edited_messages[0]["text"],
            "❌ У вас нет дней для использования",
        )

    async def test_handle_get_link_without_subscription_manager_returns_not_found(self):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})

        with (
            patch.object(
                navigation_handlers.db,
                "get_subscription_by_id",
                return_value={"id": 1, "user_id": 42},
            ),
            patch.object(navigation_handlers.app_context, "subscription_manager", None),
        ):
            await navigation_handlers.handle_get_link(update, context, 42, "1")

        self.assertEqual(
            update.callback_query.edited_messages[0]["text"],
            "❌ Сервис подписок недоступен",
        )

    async def test_handle_subscribe_blocks_existing_subscription(self):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})

        with (
            patch.object(
                payments_handlers.db,
                "get_active_subscription",
                return_value={"tariff_id": "basic", "ends_at": "2026-01-01T00:00:00"},
            ),
            patch.object(
                payments_handlers, "safe_date_format", return_value="2026-01-01 00:00"
            ),
        ):
            await payments_handlers.handle_subscribe(update, context, 42, "basic")

        text = update.callback_query.edited_messages[0]["text"]
        self.assertIn("У вас уже есть активная подписка", text)

    async def test_handle_cancel_uses_db_fallback_when_subscription_manager_missing(
        self,
    ):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})

        with (
            patch.object(navigation_handlers.app_context, "subscription_manager", None),
            patch.object(
                navigation_handlers.db, "cancel_subscription", return_value=True
            ),
        ):
            await navigation_handlers.handle_cancel(update, context, 42, "1")

        self.assertEqual(
            update.callback_query.edited_messages[0]["text"], "✅ Подписка отменена"
        )

    async def test_handle_confirm_change_for_free_tariff_invokes_tariff_change(self):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})

        with (
            patch.object(
                payments_handlers, "handle_tariff_change", new=AsyncMock()
            ) as change_mock,
            patch.dict(
                payments_handlers.TARIFFS,
                {
                    "basic": {
                        "id": "basic",
                        "name": "Basic",
                        "price": 0,
                        "currency": "рублей",
                        "duration_days": 30,
                    }
                },
            ),
        ):
            await payments_handlers.handle_confirm_change(
                update, context, 42, "1_basic"
            )

        change_mock.assert_awaited_once()

    async def test_handle_check_change_payment_reports_invalid_order_data(self):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})
        storage = SimpleNamespace(
            get_payment_by_order=lambda order_id: {
                "payment_id": "p1",
                "status": "pending",
            },
            update_payment_status=lambda *args, **kwargs: None,
        )

        with (
            patch.object(payments_handlers.app_context, "payment_storage", storage),
            patch.object(
                payments_handlers.app_context,
                "yookassa",
                SimpleNamespace(
                    check_payment=lambda payment_id: {
                        "status": "succeeded",
                        "paid": True,
                    }
                ),
            ),
            patch.object(
                storage,
                "get_payment_by_order",
                return_value={"payment_id": "p1", "status": "pending"},
            ),
            patch.object(storage, "update_payment_status", return_value=None),
        ):
            await payments_handlers.handle_check_change_payment(
                update, context, 42, "bad_order"
            )

        self.assertIn(
            "Ошибка данных заказа", update.callback_query.edited_messages[0]["text"]
        )

    async def test_handle_check_payment_refunds_when_subscription_activation_fails(
        self,
    ):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})
        payment_record = {
            "order_id": "order_1",
            "payment_id": "pay_1",
            "status": "pending",
            "tariff_id": "premium",
            "amount": 199,
            "user_id": 42,
        }
        update_calls = []

        def update_payment_status(order_id, status, payment_id=None, refund_id=None):
            update_calls.append((order_id, status, payment_id, refund_id))
            return True

        storage = SimpleNamespace(
            get_payment_by_order=lambda order_id: payment_record,
            update_payment_status=update_payment_status,
            create_payment_record=lambda *args, **kwargs: None,
        )

        yookassa_client = SimpleNamespace(
            check_payment=lambda payment_id: {"status": "succeeded", "paid": True},
            capture_payment=lambda payment_id: {"success": True, "status": "succeeded"},
            create_refund=Mock(
                return_value={
                    "success": True,
                    "refund_id": "refund_1",
                    "status": "succeeded",
                }
            ),
        )

        create_paid = AsyncMock(
            return_value={"success": False, "error": "panel failure"}
        )
        reward_referrer = Mock()

        with (
            patch.object(payments_handlers.app_context, "payment_storage", storage),
            patch.object(payments_handlers.app_context, "yookassa", yookassa_client),
            patch.object(payments_handlers, "create_paid_subscription", create_paid),
            patch.object(
                payments_handlers.db, "reward_referrer", reward_referrer, create=True
            ),
            patch.dict(
                payments_handlers.TARIFFS,
                {
                    "premium": {
                        "id": "premium",
                        "name": "Premium",
                        "price": 199,
                        "currency": "рублей",
                        "duration_days": 30,
                        "speed": "50 Мбит/с",
                        "warp": False,
                        "test_configs": False,
                    }
                },
            ),
        ):
            await payments_handlers.handle_check_payment(update, context, 42, "order_1")

        self.assertTrue(yookassa_client.create_refund.called)
        self.assertEqual(yookassa_client.create_refund.call_args.args[0], "pay_1")
        self.assertEqual(update_calls[-1], ("order_1", "refunded", "pay_1", "refund_1"))
        self.assertFalse(reward_referrer.called)
        self.assertIn(
            "вернули средства", update.callback_query.edited_messages[-1]["text"]
        )

    async def test_handle_check_payment_refunds_when_extension_fails(self):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})
        payment_record = {
            "order_id": "extend_1_abcd1234",
            "payment_id": "pay_2",
            "status": "pending",
            "tariff_id": "premium",
            "amount": 199,
            "user_id": 42,
        }
        update_calls = []

        def update_payment_status(order_id, status, payment_id=None, refund_id=None):
            update_calls.append((order_id, status, payment_id, refund_id))
            return True

        storage = SimpleNamespace(
            get_payment_by_order=lambda order_id: payment_record,
            update_payment_status=update_payment_status,
            create_payment_record=lambda *args, **kwargs: None,
        )

        create_refund = Mock(
            return_value={
                "success": True,
                "refund_id": "refund_2",
                "status": "succeeded",
            }
        )
        yookassa_client = SimpleNamespace(
            check_payment=lambda payment_id: {"status": "succeeded", "paid": True},
            capture_payment=lambda payment_id: {"success": True, "status": "succeeded"},
            create_refund=create_refund,
        )

        app_subscription_manager = SimpleNamespace(
            extend_subscription=lambda subscription_id, extra_days: {
                "success": False,
                "error": "sync failed",
                "local_db_updated": True,
            },
            get_user_subscription_link=lambda user_id: "https://example.com/link",
        )

        fake_db = SimpleNamespace(reward_referrer=Mock())

        with (
            patch.object(payments_handlers.app_context, "payment_storage", storage),
            patch.object(payments_handlers.app_context, "yookassa", yookassa_client),
            patch.object(
                payments_handlers.app_context,
                "subscription_manager",
                app_subscription_manager,
            ),
            patch.object(
                payments_handlers.db,
                "reward_referrer",
                fake_db.reward_referrer,
                create=True,
            ),
            patch.dict(
                payments_handlers.TARIFFS,
                {
                    "premium": {
                        "id": "premium",
                        "name": "Premium",
                        "price": 199,
                        "currency": "рублей",
                        "duration_days": 30,
                        "speed": "50 Мбит/с",
                        "warp": False,
                        "test_configs": False,
                    }
                },
            ),
        ):
            await payments_handlers.handle_check_payment(
                update, context, 42, "extend_1_abcd1234"
            )

        self.assertTrue(yookassa_client.create_refund.called)
        self.assertEqual(
            update_calls[-1], ("extend_1_abcd1234", "refunded", "pay_2", "refund_2")
        )
        self.assertIn(
            "вернули средства", update.callback_query.edited_messages[-1]["text"]
        )

    async def test_handle_check_payment_does_not_refund_twice_for_refunded_payment(
        self,
    ):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})
        payment_record = {
            "order_id": "order_1",
            "payment_id": "pay_1",
            "status": "refunded",
            "tariff_id": "premium",
            "amount": 199,
            "user_id": 42,
        }

        storage = SimpleNamespace(
            get_payment_by_order=lambda order_id: payment_record,
            update_payment_status=lambda *args, **kwargs: None,
            create_payment_record=lambda *args, **kwargs: None,
        )

        yookassa_client = SimpleNamespace(
            check_payment=lambda payment_id: {"status": "succeeded", "paid": True},
            capture_payment=lambda payment_id: {"success": True, "status": "succeeded"},
            create_refund=Mock(
                return_value={
                    "success": True,
                    "refund_id": "refund_3",
                    "status": "succeeded",
                }
            ),
        )

        with (
            patch.object(payments_handlers.app_context, "payment_storage", storage),
            patch.object(payments_handlers.app_context, "yookassa", yookassa_client),
            patch.dict(
                payments_handlers.TARIFFS,
                {
                    "premium": {
                        "id": "premium",
                        "name": "Premium",
                        "price": 199,
                        "currency": "рублей",
                        "duration_days": 30,
                        "speed": "50 Мбит/с",
                        "warp": False,
                        "test_configs": False,
                    }
                },
            ),
        ):
            await payments_handlers.handle_check_payment(update, context, 42, "order_1")

        self.assertFalse(yookassa_client.create_refund.called)
        self.assertIn(
            "Платеж уже возвращен", update.callback_query.edited_messages[-1]["text"]
        )

    async def test_handle_check_change_payment_does_not_refund_twice_for_refunded_payment(
        self,
    ):
        update = DummyUpdate()
        context = SimpleNamespace(user_data={})
        payment_record = {
            "order_id": "change_42_10_premium",
            "payment_id": "pay_4",
            "status": "refunded",
            "tariff_id": "premium",
            "amount": 199,
            "user_id": 42,
        }

        storage = SimpleNamespace(
            get_payment_by_order=lambda order_id: payment_record,
            update_payment_status=lambda *args, **kwargs: None,
            create_payment_record=lambda *args, **kwargs: None,
        )

        yookassa_client = SimpleNamespace(
            check_payment=lambda payment_id: {"status": "succeeded", "paid": True},
            capture_payment=lambda payment_id: {"success": True, "status": "succeeded"},
            create_refund=Mock(
                return_value={
                    "success": True,
                    "refund_id": "refund_4",
                    "status": "succeeded",
                }
            ),
        )

        with (
            patch.object(payments_handlers.app_context, "payment_storage", storage),
            patch.object(payments_handlers.app_context, "yookassa", yookassa_client),
            patch.dict(
                payments_handlers.TARIFFS,
                {
                    "premium": {
                        "id": "premium",
                        "name": "Premium",
                        "price": 199,
                        "currency": "рублей",
                        "duration_days": 30,
                        "speed": "50 Мбит/с",
                        "warp": False,
                        "test_configs": False,
                    }
                },
            ),
        ):
            await payments_handlers.handle_check_change_payment(
                update, context, 42, "change_42_10_premium"
            )

        self.assertFalse(yookassa_client.create_refund.called)
        self.assertIn(
            "Платеж уже возвращен", update.callback_query.edited_messages[-1]["text"]
        )


if __name__ == "__main__":
    unittest.main()
