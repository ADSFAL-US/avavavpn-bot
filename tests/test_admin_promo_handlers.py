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
        self.promo_codes = {}
        self.next_promo_id = 1

    def is_admin(self, user_id):
        return user_id == 12345

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

    def get_user_count(self):
        return 10

    def get_subscription_stats(self):
        return {}

    def create_promo_code(self, code, discount_percent=0, free_days=0, valid_from=None,
                          valid_until=None, max_activations=1, applicable_tariffs=None,
                          activation_text=None, is_idempotent=0, is_active=1):
        promo_id = self.next_promo_id
        self.next_promo_id += 1
        promo = {
            "id": promo_id,
            "code": code.upper(),
            "discount_percent": discount_percent,
            "free_days": free_days,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "max_activations": max_activations,
            "current_activations": 0,
            "applicable_tariffs": applicable_tariffs,
            "activation_text": activation_text,
            "is_idempotent": is_idempotent,
            "is_active": is_active,
        }
        self.promo_codes[promo_id] = promo
        return promo_id

    def get_promo_code_by_code(self, code):
        for promo in self.promo_codes.values():
            if promo["code"] == code.upper() and promo["is_active"]:
                return promo
        return None

    def get_promo_code_by_id(self, promo_id):
        return self.promo_codes.get(promo_id)

    def list_promo_codes(self, active_only=True):
        if active_only:
            return [p for p in self.promo_codes.values() if p["is_active"]]
        return list(self.promo_codes.values())

    def update_promo_code(self, promo_id, **fields):
        if promo_id not in self.promo_codes:
            return False
        for key, value in fields.items():
            if key == "code" and value:
                value = value.upper()
            self.promo_codes[promo_id][key] = value
        return True

    def delete_promo_code(self, promo_id):
        if promo_id in self.promo_codes:
            self.promo_codes[promo_id]["is_active"] = 0
            return True
        return False

    def get_promo_activations(self, promo_code_id):
        return []

    def activate_promo_code(self, user_id, code):
        return {"success": False, "error": "Not implemented"}


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
    from handlers import admin_promo as admin_promo_handlers
    from utils import (
        STATE_PROMO_CODE,
        STATE_PROMO_DAYS,
        STATE_PROMO_DISCOUNT,
        STATE_PROMO_IDEMPOTENT,
        STATE_PROMO_MAX_ACTIVATIONS,
        STATE_PROMO_TARIFFS,
        STATE_PROMO_TEXT,
        STATE_PROMO_VALID_FROM,
        STATE_PROMO_VALID_UNTIL,
    )


class DummyQuery:
    def __init__(self):
        self.edited_messages = []
        self.data = ""

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append({"text": text, "kwargs": kwargs})


class DummyMessage:
    def __init__(self):
        self.replied_messages = []

    async def reply_text(self, text, **kwargs):
        self.replied_messages.append({"text": text, "kwargs": kwargs})


class DummyUpdate:
    def __init__(self):
        self.callback_query = DummyQuery()
        self.message = DummyMessage()
        self.effective_user = SimpleNamespace(id=12345)


class AdminPromoHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset the fake database before each test
        fake_db_module.db.promo_codes = {}
        fake_db_module.db.next_promo_id = 1
        
        self.context = SimpleNamespace(user_data={})
        self.update = DummyUpdate()
        self.update.callback_query.data = "admin_promos"
        self.update.effective_user.id = 12345

    # ===== Admin Promos Menu =====
    async def test_handle_admin_promos_shows_menu(self):
        await admin_promo_handlers.handle_admin_promos(self.update, self.context, 12345)
        self.assertEqual(len(self.update.callback_query.edited_messages), 1)
        self.assertIn("Управление промокодами", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Creation Flow =====
    async def test_handle_admin_promo_create_start_sets_state(self):
        await admin_promo_handlers.handle_admin_promo_create_start(self.update, self.context, 12345)
        self.assertEqual(self.context.user_data["state"], STATE_PROMO_CODE)
        self.assertTrue(self.context.user_data.get("admin_promo_create"))
        self.assertIn("Создать промокод", self.update.callback_query.edited_messages[0]["text"])

    async def test_handle_admin_promo_create_code_valid(self):
        self.context.user_data["state"] = STATE_PROMO_CODE
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "TESTCODE"

        await admin_promo_handlers.handle_admin_promo_create_code(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_DISCOUNT)
        self.assertEqual(self.context.user_data["promo_code"], "TESTCODE")
        self.assertIn("Введите процент скидки", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_code_invalid_state(self):
        self.context.user_data["state"] = STATE_PROMO_DISCOUNT
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "TESTCODE"

        await admin_promo_handlers.handle_admin_promo_create_code(self.update, self.context, 12345)

        # Should not process - wrong state
        self.assertEqual(len(self.update.message.replied_messages), 0)

    async def test_handle_admin_promo_create_code_without_admin_flag(self):
        self.context.user_data["state"] = STATE_PROMO_CODE
        self.update.message.text = "TESTCODE"

        await admin_promo_handlers.handle_admin_promo_create_code(self.update, self.context, 12345)

        # Should not process - missing admin_promo_create flag
        self.assertEqual(len(self.update.message.replied_messages), 0)

    async def test_handle_admin_promo_create_discount_valid(self):
        self.context.user_data["state"] = STATE_PROMO_DISCOUNT
        self.context.user_data["admin_promo_create"] = True
        self.context.user_data["promo_code"] = "TESTCODE"
        self.update.message.text = "20"

        await admin_promo_handlers.handle_admin_promo_create_discount(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_DAYS)
        self.assertEqual(self.context.user_data["promo_discount"], 20)
        self.assertIn("Введите количество бесплатных дней", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_discount_invalid(self):
        self.context.user_data["state"] = STATE_PROMO_DISCOUNT
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "150"

        await admin_promo_handlers.handle_admin_promo_create_discount(self.update, self.context, 12345)

        self.assertIn("Введите целое число от 0 до 100", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_days_valid(self):
        self.context.user_data["state"] = STATE_PROMO_DAYS
        self.context.user_data["admin_promo_create"] = True
        self.context.user_data["promo_code"] = "TESTCODE"
        self.context.user_data["promo_discount"] = 20
        self.update.message.text = "30"

        await admin_promo_handlers.handle_admin_promo_create_days(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_VALID_FROM)
        self.assertEqual(self.context.user_data["promo_days"], 30)
        self.assertIn("Введите дату начала действия", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_valid_from_valid(self):
        self.context.user_data["state"] = STATE_PROMO_VALID_FROM
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "2025-01-01"

        await admin_promo_handlers.handle_admin_promo_create_valid_from(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_VALID_UNTIL)
        self.assertEqual(self.context.user_data["promo_valid_from"], "2025-01-01T00:00:00+00:00")
        self.assertIn("Введите дату окончания действия", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_valid_until_valid(self):
        self.context.user_data["state"] = STATE_PROMO_VALID_UNTIL
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "2025-12-31"

        await admin_promo_handlers.handle_admin_promo_create_valid_until(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_MAX_ACTIVATIONS)
        self.assertEqual(self.context.user_data["promo_valid_until"], "2025-12-31T00:00:00+00:00")
        self.assertIn("Введите максимальное количество активаций", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_max_activations_valid(self):
        self.context.user_data["state"] = STATE_PROMO_MAX_ACTIVATIONS
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "100"

        await admin_promo_handlers.handle_admin_promo_create_max_activations(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_TARIFFS)
        self.assertEqual(self.context.user_data["promo_max_activations"], 100)
        self.assertIn("Введите тарифы", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_tariffs_all(self):
        self.context.user_data["state"] = STATE_PROMO_TARIFFS
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "all"

        await admin_promo_handlers.handle_admin_promo_create_tariffs(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_TEXT)
        self.assertIsNone(self.context.user_data["promo_tariffs"])
        self.assertIn("Введите текст активации", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_tariffs_specific(self):
        self.context.user_data["state"] = STATE_PROMO_TARIFFS
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "basic,premium"

        await admin_promo_handlers.handle_admin_promo_create_tariffs(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_TEXT)
        import json
        self.assertEqual(json.loads(self.context.user_data["promo_tariffs"]), ["basic", "premium"])

    async def test_handle_admin_promo_create_tariffs_invalid(self):
        self.context.user_data["state"] = STATE_PROMO_TARIFFS
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "invalid_tariff"

        await admin_promo_handlers.handle_admin_promo_create_tariffs(self.update, self.context, 12345)

        self.assertIn("Неизвестный тариф", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_text(self):
        self.context.user_data["state"] = STATE_PROMO_TEXT
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "Welcome bonus!"

        await admin_promo_handlers.handle_admin_promo_create_text(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_IDEMPOTENT)
        self.assertEqual(self.context.user_data["promo_text"], "Welcome bonus!")
        self.assertIn("Можно ли активировать несколько раз", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_text_empty(self):
        self.context.user_data["state"] = STATE_PROMO_TEXT
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = ""

        await admin_promo_handlers.handle_admin_promo_create_text(self.update, self.context, 12345)

        self.assertEqual(self.context.user_data["state"], STATE_PROMO_IDEMPOTENT)
        self.assertIsNone(self.context.user_data["promo_text"])

    async def test_handle_admin_promo_create_idempotent_yes(self):
        self.context.user_data["state"] = STATE_PROMO_IDEMPOTENT
        self.context.user_data["admin_promo_create"] = True
        self.context.user_data["promo_code"] = "TESTCODE"
        self.context.user_data["promo_discount"] = 20
        self.context.user_data["promo_days"] = 30
        self.context.user_data["promo_valid_from"] = "2025-01-01T00:00:00+00:00"
        self.context.user_data["promo_valid_until"] = "2025-12-31T00:00:00+00:00"
        self.context.user_data["promo_max_activations"] = 100
        self.context.user_data["promo_tariffs"] = None
        self.context.user_data["promo_text"] = "Welcome!"
        self.update.message.text = "да"

        await admin_promo_handlers.handle_admin_promo_create_idempotent(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertFalse(self.context.user_data.get("admin_promo_create"))
        self.assertIn("Промокод создан", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_idempotent_no(self):
        self.context.user_data["state"] = STATE_PROMO_IDEMPOTENT
        self.context.user_data["admin_promo_create"] = True
        self.context.user_data["promo_code"] = "TESTCODE"
        self.context.user_data["promo_discount"] = 20
        self.context.user_data["promo_days"] = 30
        self.context.user_data["promo_valid_from"] = "2025-01-01T00:00:00+00:00"
        self.context.user_data["promo_valid_until"] = "2025-12-31T00:00:00+00:00"
        self.context.user_data["promo_max_activations"] = 100
        self.context.user_data["promo_tariffs"] = None
        self.context.user_data["promo_text"] = "Welcome!"
        self.update.message.text = "нет"

        await admin_promo_handlers.handle_admin_promo_create_idempotent(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertFalse(self.context.user_data.get("admin_promo_create"))
        self.assertIn("Промокод создан", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_create_idempotent_invalid(self):
        self.context.user_data["state"] = STATE_PROMO_IDEMPOTENT
        self.context.user_data["admin_promo_create"] = True
        self.update.message.text = "maybe"

        await admin_promo_handlers.handle_admin_promo_create_idempotent(self.update, self.context, 12345)

        self.assertIn("Ответьте 'да' или 'нет'", self.update.message.replied_messages[0]["text"])

    # ===== Promo List =====
    async def test_handle_admin_promos_list_empty(self):
        await admin_promo_handlers.handle_admin_promos_list(self.update, self.context, 12345)
        self.assertIn("Промокоды не найдены", self.update.callback_query.edited_messages[0]["text"])

    async def test_handle_admin_promos_list_with_promos(self):
        # Add a promo code
        fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        await admin_promo_handlers.handle_admin_promos_list(self.update, self.context, 12345)
        self.assertIn("TEST1", self.update.callback_query.edited_messages[0]["text"])
        self.assertIn("10%", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Find =====
    async def test_handle_admin_promo_find_sets_state(self):
        await admin_promo_handlers.handle_admin_promo_find(self.update, self.context, 12345)
        self.assertEqual(self.context.user_data["state"], STATE_PROMO_CODE)
        self.assertTrue(self.context.user_data.get("admin_promo_find"))
        self.assertIn("Найти промокод", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Stats =====
    async def test_handle_admin_promo_stats_empty(self):
        await admin_promo_handlers.handle_admin_promo_stats(self.update, self.context, 12345)
        self.assertIn("Всего промокодов: <b>0</b>", self.update.callback_query.edited_messages[0]["text"])

    async def test_handle_admin_promo_stats_with_promos(self):
        fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7, is_active=1)
        fake_db_module.db.create_promo_code("TEST2", discount_percent=20, free_days=0, is_active=0)
        await admin_promo_handlers.handle_admin_promo_stats(self.update, self.context, 12345)
        self.assertIn("Всего промокодов: <b>2</b>", self.update.callback_query.edited_messages[0]["text"])
        self.assertIn("Активных: <b>1</b>", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Detail =====
    async def test_handle_admin_promo_detail(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.update.callback_query.data = f"admin_promo_detail_{promo_id}"
        await admin_promo_handlers.handle_admin_promo_detail(self.update, self.context, 12345, str(promo_id))
        self.assertIn("TEST1", self.update.callback_query.edited_messages[0]["text"])
        self.assertIn("10%", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Edit Menu =====
    async def test_handle_admin_promo_edit(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.update.callback_query.data = f"admin_promo_edit_{promo_id}"
        await admin_promo_handlers.handle_admin_promo_edit(self.update, self.context, 12345, str(promo_id))
        self.assertIn("Редактировать промокод", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Delete =====
    async def test_handle_admin_promo_delete_success(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.update.callback_query.data = f"admin_promo_delete_{promo_id}"
        await admin_promo_handlers.handle_admin_promo_delete(self.update, self.context, 12345, str(promo_id))
        self.assertIn("Промокод удален", self.update.callback_query.edited_messages[0]["text"])

    async def test_handle_admin_promo_delete_not_found(self):
        self.update.callback_query.data = "admin_promo_delete_999"
        await admin_promo_handlers.handle_admin_promo_delete(self.update, self.context, 12345, "999")
        self.assertIn("Ошибка удаления", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Activations =====
    async def test_handle_admin_promo_activations_empty(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.update.callback_query.data = f"admin_promo_activations_{promo_id}"
        await admin_promo_handlers.handle_admin_promo_activations(self.update, self.context, 12345, str(promo_id))
        self.assertIn("Активаций нет", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Toggle =====
    async def test_handle_admin_promo_toggle_active(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7, is_active=1)
        self.update.callback_query.data = f"admin_promo_toggle_{promo_id}"
        await admin_promo_handlers.handle_admin_promo_toggle_active(self.update, self.context, 12345, str(promo_id))
        self.assertIn("Неактивен", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Edit Field =====
    async def test_handle_admin_promo_edit_field(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.update.callback_query.data = f"admin_promo_edit_field_{promo_id}_discount_percent"
        await admin_promo_handlers.handle_admin_promo_edit_field(self.update, self.context, 12345, str(promo_id), "discount_percent")
        self.assertEqual(self.context.user_data["state"], "admin_promo_edit_discount_percent")
        self.assertEqual(self.context.user_data["admin_promo_edit_id"], str(promo_id))
        self.assertEqual(self.context.user_data["admin_promo_edit_field"], "discount_percent")
        self.assertIn("Редактирование: Скидка", self.update.callback_query.edited_messages[0]["text"])

    # ===== Promo Edit Field Value =====
    async def test_handle_admin_promo_edit_field_value_discount(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_discount_percent"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "discount_percent"
        self.update.message.text = "25"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_invalid_discount(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_discount_percent"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "discount_percent"
        self.update.message.text = "150"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIn("Скидка должна быть от 0 до 100", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_code(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_code"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "code"
        self.update.message.text = "NEWCODE"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_valid_from(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_valid_from"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "valid_from"
        self.update.message.text = "2025-06-15"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_valid_from_none(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_valid_from"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "valid_from"
        self.update.message.text = "none"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_tariffs_all(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_applicable_tariffs"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "applicable_tariffs"
        self.update.message.text = "all"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_tariffs_specific(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_applicable_tariffs"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "applicable_tariffs"
        self.update.message.text = "basic,premium"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_tariffs_invalid(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_applicable_tariffs"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "applicable_tariffs"
        self.update.message.text = "invalid"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIn("Неизвестный тариф", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_idempotent_yes(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_is_idempotent"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "is_idempotent"
        self.update.message.text = "да"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_idempotent_no(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_is_idempotent"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "is_idempotent"
        self.update.message.text = "нет"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_idempotent_invalid(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_is_idempotent"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "is_idempotent"
        self.update.message.text = "maybe"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIn("Ответьте 'да' или 'нет'", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_active(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_is_active"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "is_active"
        self.update.message.text = "0"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIsNone(self.context.user_data.get("state"))
        self.assertIn("Поле обновлено", self.update.message.replied_messages[0]["text"])

    async def test_handle_admin_promo_edit_field_value_active_invalid(self):
        promo_id = fake_db_module.db.create_promo_code("TEST1", discount_percent=10, free_days=7)
        self.context.user_data["state"] = "admin_promo_edit_is_active"
        self.context.user_data["admin_promo_edit_id"] = str(promo_id)
        self.context.user_data["admin_promo_edit_field"] = "is_active"
        self.update.message.text = "2"

        await admin_promo_handlers.handle_admin_promo_edit_field_value(self.update, self.context, 12345)

        self.assertIn("Статус должен быть 0 или 1", self.update.message.replied_messages[0]["text"])


if __name__ == "__main__":
    unittest.main()