import unittest
from unittest.mock import patch

import yookassa


class YooKassaTests(unittest.TestCase):
    def test_init_requires_credentials(self):
        with self.assertRaises(ValueError):
            yookassa.YooKassaAPI("", "")

    @patch("yookassa.requests.post")
    def test_create_payment_returns_success(self, post_mock):
        post_mock.return_value.raise_for_status.return_value = None
        post_mock.return_value.json.return_value = {"status": "pending", "id": "pay_1", "confirmation": {"confirmation_url": "https://pay.test"}}

        client = yookassa.YooKassaAPI("shop", "key")
        result = client.create_payment(amount=99, description="test", user_id=1, tariff_id="basic")

        self.assertTrue(result["success"])
        self.assertEqual(result["payment_id"], "pay_1")

    def test_create_payment_rejects_non_positive_amount(self):
        client = yookassa.YooKassaAPI("shop", "key")
        result = client.create_payment(amount=0, description="test", user_id=1, tariff_id="basic")
        self.assertFalse(result["success"])
        self.assertIn("greater", result["error"])

    def test_check_payment_returns_error_for_missing_id(self):
        client = yookassa.YooKassaAPI("shop", "key")
        result = client.check_payment("")
        self.assertIn("required", result["error"])

    def test_capture_payment_handles_empty_id(self):
        client = yookassa.YooKassaAPI("shop", "key")
        result = client.capture_payment("")
        self.assertIn("required", result["error"])


if __name__ == "__main__":
    unittest.main()
