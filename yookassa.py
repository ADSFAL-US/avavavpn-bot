# Avava VPN Bot - YooKassa Payment Integration
import requests
import datetime
import logging

logger = logging.getLogger(__name__)


class YooKassa:
    """YooKassa payment gateway integration."""
    
    def __init__(self, shop_id: str, api_key: str, test_mode: bool = True):
        self.shop_id = shop_id
        self.api_key = api_key
        self.test_mode = test_mode
        self.base_url = "https://api.yookassa.ru/v3" if test_mode else "https://api.yookassa.ru/v3"
        self.auth = (shop_id, api_key)
    
    def create_payment(
        self,
        order_id: str,
        amount: float,
        description: str,
        user_id: int,
        tariff_id: str,
        capture: bool = True,
        return_url: str = None,
    ) -> dict:
        """
        Create a payment link via YooKassa.
        
        Returns payment URL to redirect user to.
        """
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "capture_order": capture,
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "tariff_id": tariff_id,
                "order_id": order_id,
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or "",
            },
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/payments",
                json=payload,
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "pending" and data.get("confirmation"):
                payment_url = data["confirmation"].get("url", "")
                payment_id = data.get("id", "")
                logger.info(f"Payment created: order={order_id}, user={user_id}, url={payment_url}")
                return {
                    "success": True,
                    "payment_url": payment_url,
                    "payment_id": payment_id,
                    "order_id": order_id,
                }
            else:
                logger.error(f"Payment not pending: {data}")
                return {
                    "success": False,
                    "error": "Payment status is not pending",
                    "data": data,
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"YooKassa request failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def check_payment(self, payment_id: str) -> dict:
        """Check payment status."""
        try:
            response = requests.get(
                f"{self.base_url}/payments/{payment_id}",
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Payment check failed: {e}")
            return {"error": str(e)}
    
    def refund(self, payment_id: str, amount: float = None) -> dict:
        """Refund a payment."""
        payload = {}
        if amount is not None:
            payload["amount"] = {
                "value": f"{amount:.2f}",
                "currency": "RUB",
            }
        
        try:
            response = requests.post(
                f"{self.base_url}/refunds",
                json=payload,
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Refund failed: {e}")
            return {"error": str(e)}


# Payment state tracking in user data
PAYMENT_PENDING = "payment_pending"
PAYMENT_CONFIRMED = "payment_confirmed"

# In-memory store for pending payments (use Redis/db in production)
_pending_payments = {}


def set_pending_payment(order_id: str, data: dict):
    """Store pending payment info."""
    _pending_payments[order_id] = {
        **data,
        "created_at": datetime.datetime.now().isoformat(),
    }


def get_pending_payment(order_id: str) -> dict | None:
    """Get pending payment info."""
    return _pending_payments.get(order_id)


def remove_pending_payment(order_id: str):
    """Remove pending payment after confirmation."""
    _pending_payments.pop(order_id, None)


def clean_old_payments(hours: int = 24):
    """Clean expired pending payments."""
    now = datetime.datetime.now()
    expired = []
    for order_id, data in _pending_payments.items():
        created = datetime.datetime.fromisoformat(data["created_at"])
        if (now - created).total_seconds() > hours * 3600:
            expired.append(order_id)
    
    for order_id in expired:
        del _pending_payments[order_id]
    logger.info(f"Cleaned {len(expired)} expired payments")