import unittest
from unittest.mock import Mock, patch

import xcontroller_client


class XControllerClientTests(unittest.TestCase):
    def test_make_request_returns_json_for_success(self):
        client = xcontroller_client.XControllerClient(base_url="https://example.test", username="u", password="p")
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"success": True, "subscription": {"id": 1}}
        response.text = "{}"
        response.raise_for_status.return_value = None

        with patch.object(client._session, "request", return_value=response):
            result = client._make_request("GET", "/api/health")

        self.assertTrue(result["success"])
        self.assertEqual(result["subscription"]["id"], 1)

    def test_make_request_raises_auth_error(self):
        client = xcontroller_client.XControllerClient(base_url="https://example.test", username="u", password="p")

        with patch.object(client._session, "request", side_effect=xcontroller_client.XControllerAuthError("Invalid credentials")):
            with self.assertRaises(xcontroller_client.XControllerAuthError):
                client._make_request("GET", "/api/health")

    def test_get_subscription_link_uses_base_url(self):
        client = xcontroller_client.XControllerClient(base_url="https://panel.test", username="u", password="p")
        self.assertEqual(client.get_subscription_link("abc"), "https://panel.test/sub/abc")

    def test_create_user_subscription_uses_tariff_defaults(self):
        client = xcontroller_client.XControllerClient(base_url="https://example.test", username="u", password="p")
        with patch.object(client, "create_subscription", return_value={"success": True}) as create_mock:
            result = client.create_user_subscription(123, {"preset_id": 3, "duration_days": 10, "traffic_limit_gb": 20})

        self.assertTrue(result["success"])
        create_mock.assert_called_once()

    def test_get_panel_details_returns_none_for_not_found(self):
        client = xcontroller_client.XControllerClient(base_url="https://example.test", username="u", password="p")
        with patch.object(client, "_make_request", side_effect=xcontroller_client.XControllerAPIError("missing", 404, {})):
            self.assertIsNone(client.get_panel_details(7))


if __name__ == "__main__":
    unittest.main()
