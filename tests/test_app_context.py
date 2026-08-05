import importlib
import unittest

import app_context


class AppContextTests(unittest.TestCase):
    def setUp(self):
        self._reset_state()

    def tearDown(self):
        self._reset_state()

    def _reset_state(self):
        app_context.yookassa = None
        app_context.payment_storage = None
        app_context.xcontroller = None
        app_context.subscription_manager = None

    def test_module_defaults_to_none(self):
        self.assertIsNone(app_context.yookassa)
        self.assertIsNone(app_context.payment_storage)
        self.assertIsNone(app_context.xcontroller)
        self.assertIsNone(app_context.subscription_manager)

    def test_module_allows_runtime_assignment(self):
        fake_service = object()
        app_context.yookassa = fake_service
        app_context.payment_storage = fake_service
        app_context.xcontroller = fake_service
        app_context.subscription_manager = fake_service

        self.assertIs(app_context.yookassa, fake_service)
        self.assertIs(app_context.payment_storage, fake_service)
        self.assertIs(app_context.xcontroller, fake_service)
        self.assertIs(app_context.subscription_manager, fake_service)

    def test_module_can_be_reloaded(self):
        reloaded = importlib.import_module("app_context")
        self.assertIs(reloaded, app_context)
        self.assertIsNotNone(reloaded.logger)
