import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from handlers import monitoring as monitoring_handlers


class DummyQuery:
    def __init__(self):
        self.edited_messages = []
        self.answers = []

    async def edit_message_text(self, text, **kwargs):
        self.edited_messages.append({"text": text, "kwargs": kwargs})

    async def answer(self, text=None, **kwargs):
        self.answers.append({"text": text, "kwargs": kwargs})


class DummyUpdate:
    def __init__(self):
        self.callback_query = DummyQuery()


class MonitoringTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_panel_statuses_uses_cache(self):
        monitoring_handlers._panel_status_cache = {"data": [{"panel": {"id": 1}, "health": {"status": "healthy"}}], "expiry": 9999999999}
        with patch.object(monitoring_handlers.app_context, "xcontroller", None):
            statuses = monitoring_handlers._get_panel_statuses()
        self.assertEqual(len(statuses), 1)

    async def test_handle_monitor_menu_blocks_non_admin(self):
        update = DummyUpdate()
        context = SimpleNamespace()
        with patch.object(monitoring_handlers, "is_admin", return_value=False):
            await monitoring_handlers.handle_monitor_menu(update, context, 1)
        self.assertIn("Нет доступа", update.callback_query.answers[0]["text"])

    async def test_handle_monitor_detail_returns_error_for_invalid_id(self):
        update = DummyUpdate()
        context = SimpleNamespace()
        with patch.object(monitoring_handlers, "is_admin", return_value=True):
            await monitoring_handlers.handle_monitor_detail(update, context, 1, "abc")
        self.assertIn("Неверный ID панели", update.callback_query.edited_messages[0]["text"])

    async def test_handle_user_monitor_menu_renders_without_panels(self):
        update = DummyUpdate()
        context = SimpleNamespace()
        monitoring_handlers._panel_status_cache = {"data": [], "expiry": 0}
        await monitoring_handlers.handle_user_monitor_menu(update, context, 1)
        self.assertIn("Серверов не настроено", update.callback_query.edited_messages[0]["text"])

    async def test_clear_panel_alert_state_clears_all(self):
        monitoring_handlers._panel_alert_state["panel1"] = monitoring_handlers.datetime.now()
        monitoring_handlers.clear_panel_alert_state()
        self.assertEqual(monitoring_handlers._panel_alert_state, {})

    async def test_check_all_panels_and_alert_sends_to_admins(self):
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        monitoring_handlers._panel_alert_state.clear()
        panel = {"id": 1, "name": "Alpha"}
        health = {"status": monitoring_handlers.PANEL_STATUS_UNHEALTHY, "error": "down"}

        with patch.object(monitoring_handlers.app_context, "xcontroller", SimpleNamespace(get_panels=lambda: [panel], check_panel_health=lambda panel_id: health)), \
             patch.object(monitoring_handlers.config, "ADMIN_IDS", [123]), \
             patch.object(monitoring_handlers.config, "ALERT_COOLDOWN_MINUTES", 0):
            await monitoring_handlers.check_all_panels_and_alert(context)

        self.assertTrue(context.bot.send_message.await_count > 0)


if __name__ == "__main__":
    unittest.main()
