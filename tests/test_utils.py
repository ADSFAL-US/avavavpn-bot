import unittest
from unittest.mock import patch

from utils import build_subscription_prompt, safe_date_format


class UtilsTests(unittest.TestCase):
    def test_safe_date_format_returns_na_for_blank_values(self):
        self.assertEqual(safe_date_format(None), "N/A")
        self.assertEqual(safe_date_format(""), "N/A")

    def test_safe_date_format_replaces_separator(self):
        self.assertEqual(safe_date_format("2026-08-05T14:30:00"), "2026-08-05 14:30:00")

    def test_build_subscription_prompt_uses_configured_channel(self):
        with patch("utils.config.REQUIRED_CHANNEL_USERNAME", "@AvavaVpn"):
            text, keyboard = build_subscription_prompt()

        self.assertIn("AvavaVpn", text)
        self.assertIn("https://t.me/AvavaVpn", text)
        self.assertEqual(len(keyboard.inline_keyboard), 1)

    def test_build_subscription_prompt_without_channel_is_graceful(self):
        with patch("utils.config.REQUIRED_CHANNEL_USERNAME", ""):
            text, keyboard = build_subscription_prompt()

        self.assertIn("Подпишитесь на канал", text)
        self.assertEqual(len(keyboard.inline_keyboard), 0)


if __name__ == "__main__":
    unittest.main()
