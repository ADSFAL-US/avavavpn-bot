# Avava VPN Bot - YooKassa Payment Integration
import requests
import datetime
import logging
import sqlite3
import uuid
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class YooKassaAPI:
    """YooKassa payment gateway integration with full functionality."""

    def __init__(self, shop_id: str, api_key: str, test_mode: bool = True):
        self.shop_id = shop_id.strip()
        self.api_key = api_key.strip()
        self.test_mode = test_mode
        self.base_url = "https://api.yookassa.ru/v3"
        self.auth = (self.shop_id, self.api_key)
        
        # Validate credentials
        if not self.shop_id or not self.api_key:
            raise ValueError("Shop ID and API key are required")

    def create_payment(
        self,
        amount: float,
        description: str,
        user_id: int,
        tariff_id: str,
        order_id: Optional[str] = None,
        return_url: Optional[str] = None,
        capture: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a payment link via YooKassa.
        
        Args:
            amount: Payment amount in rubles
            description: Payment description
            user_id: Telegram user ID
            tariff_id: Selected tariff ID
            order_id: Unique order ID (auto-generated if not provided)
            return_url: URL to redirect after payment
            capture: Auto-capture payment (True) or hold for manual capture (False)
        
        Returns:
            Dict with success status, payment_url, payment_id, order_id
        """
        # Generate unique order ID if not provided
        if not order_id:
            order_id = f"avava_{user_id}_{tariff_id}_{uuid.uuid4().hex[:8]}"
        
        # Validate amount
        if amount <= 0:
            return {
                "success": False,
                "error": "Amount must be greater than 0",
            }
        
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "capture": capture,
            "description": description[:128],  # YooKassa limit
            "metadata": {
                "user_id": str(user_id),
                "tariff_id": tariff_id,
                "order_id": order_id,
                "created_at": datetime.datetime.now().isoformat(),
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or "https://t.me/avava_vpn_bot",
            },
        }

        try:
            response = requests.post(
                f"{self.base_url}/payments",
                json=payload,
                auth=self.auth,
                timeout=30,
                headers={
                    "Content-Type": "application/json",
                    "Idempotence-Key": order_id,  # Prevent duplicate payments
                }
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") in ["pending", "waiting_for_capture"]:
                confirmation = data.get("confirmation", {})
                payment_url = confirmation.get("confirmation_url") or confirmation.get("url", "")
                payment_id = data.get("id", "")
                
                logger.info(
                    f"Payment created: order={order_id}, user={user_id}, "
                    f"tariff={tariff_id}, amount={amount}, url={payment_url[:50]}..."
                )
                return {
                    "success": True,
                    "payment_url": payment_url,
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "status": data.get("status"),
                }
            else:
                logger.error(f"Unexpected payment status: {data.get('status')}, data: {data}")
                return {
                    "success": False,
                    "error": f"Unexpected payment status: {data.get('status')}",
                    "data": data,
                }

        except requests.exceptions.Timeout:
            logger.error(f"YooKassa timeout for order {order_id}")
            return {
                "success": False,
                "error": "Payment gateway timeout. Please try again.",
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"YooKassa request failed: {e}")
            return {
                "success": False,
                "error": f"Payment gateway error: {str(e)}",
            }
        except (ValueError, TypeError, RuntimeError) as e:
            logger.exception(f"Unexpected error creating payment: {e}")
            return {
                "success": False,
                "error": "Internal error. Please contact support.",
            }

    def check_payment(self, payment_id: str) -> Dict[str, Any]:
        """
        Check payment status.
        
        Returns:
            Dict with payment status or error
        """
        if not payment_id:
            return {"error": "Payment ID is required"}
        
        try:
            response = requests.get(
                f"{self.base_url}/payments/{payment_id}",
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Payment check: {payment_id}, status={data.get('status')}")
            return {
                "success": True,
                "status": data.get("status"),
                "paid": data.get("paid", False),
                "amount": data.get("amount", {}),
                "metadata": data.get("metadata", {}),
                "created_at": data.get("created_at"),
                "captured_at": data.get("captured_at"),
                "refundable": data.get("refundable", False),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Payment check failed: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.exception(f"Unexpected error checking payment: {e}")
            return {"error": "Internal error"}

    def capture_payment(self, payment_id: str, amount: Optional[float] = None) -> Dict[str, Any]:
        """
        Capture a held payment (for two-stage payments).
        
        Args:
            payment_id: Payment ID to capture
            amount: Amount to capture (None = full amount)
        """
        if not payment_id:
            return {"error": "Payment ID is required"}
        
        payload = {}
        if amount is not None and amount > 0:
            payload["amount"] = {
                "value": f"{amount:.2f}",
                "currency": "RUB",
            }
        
        try:
            response = requests.post(
                f"{self.base_url}/payments/{payment_id}/capture",
                json=payload if payload else None,
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Payment captured: {payment_id}, status={data.get('status')}")
            return {
                "success": True,
                "status": data.get("status"),
                "data": data,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Payment capture failed: {e}")
            return {"error": str(e)}

    def cancel_payment(self, payment_id: str) -> Dict[str, Any]:
        """Cancel a pending or held payment."""
        if not payment_id:
            return {"error": "Payment ID is required"}
        
        try:
            response = requests.post(
                f"{self.base_url}/payments/{payment_id}/cancel",
                auth=self.auth,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Payment cancelled: {payment_id}")
            return {
                "success": True,
                "status": data.get("status"),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Payment cancel failed: {e}")
            return {"error": str(e)}

    def create_refund(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        description: str = "Refund"
    ) -> Dict[str, Any]:
        """
        Refund a payment.
        
        Args:
            payment_id: Payment to refund
            amount: Amount to refund (None = full refund)
            description: Refund reason
        """
        if not payment_id:
            return {"error": "Payment ID is required"}
        
        payload = {
            "payment_id": payment_id,
            "description": description[:128],
        }
        
        if amount is not None and amount > 0:
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
            data = response.json()
            
            logger.info(f"Refund created: payment={payment_id}, amount={amount}")
            return {
                "success": True,
                "refund_id": data.get("id"),
                "status": data.get("status"),
                "amount": data.get("amount", {}),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Refund failed: {e}")
            return {"error": str(e)}


class PaymentStorage:
    """Persistent storage for payment state (replaces in-memory storage)."""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self._ensure_table()
    
    def _ensure_table(self):
        """Create payments table if not exists."""
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                tariff_id TEXT NOT NULL,
                payment_id TEXT,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(payment_id)
        """)
        self.db.commit()
    
    def create_payment_record(
        self,
        order_id: str,
        user_id: int,
        tariff_id: str,
        amount: float,
        payment_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Create a new payment record."""
        try:
            cursor = self.db.cursor()
            import json
            cursor.execute("""
                INSERT INTO payments (order_id, user_id, tariff_id, payment_id, amount, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                user_id,
                tariff_id,
                payment_id,
                amount,
                json.dumps(metadata) if metadata else None,
            ))
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create payment record: {e}")
            return False
    
    def update_payment_status(
        self,
        order_id: str,
        status: str,
        payment_id: Optional[str] = None,
    ) -> bool:
        """Update payment status."""
        try:
            cursor = self.db.cursor()
            if payment_id:
                cursor.execute("""
                    UPDATE payments 
                    SET status = ?, payment_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                """, (status, payment_id, order_id))
            else:
                cursor.execute("""
                    UPDATE payments 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                """, (status, order_id))
            self.db.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update payment status: {e}")
            return False
    
    def get_payment_by_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get payment by order ID."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT * FROM payments WHERE order_id = ?
            """, (order_id,))
            row = cursor.fetchone()
            if row:
                import json
                result = dict(row)
                if result.get("metadata"):
                    try:
                        result["metadata"] = json.loads(result["metadata"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                return result
            return None
        except (sqlite3.Error, AttributeError) as e:
            logger.error(f"Failed to get payment: {e}")
            return None

    def get_payment_by_payment_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Get payment by YooKassa payment ID."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT * FROM payments WHERE payment_id = ?
            """, (payment_id,))
            row = cursor.fetchone()
            if row:
                import json
                result = dict(row)
                if result.get("metadata"):
                    try:
                        result["metadata"] = json.loads(result["metadata"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                return result
            return None
        except (sqlite3.Error, AttributeError) as e:
            logger.error(f"Failed to get payment: {e}")
            return None
    
    def get_pending_payments(self, user_id: int) -> list:
        """Get all pending payments for a user."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT * FROM payments 
                WHERE user_id = ? AND status = 'pending'
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
            import json
            result = []
            for row in rows:
                item = dict(row)
                if item.get("metadata"):
                    try:
                        item["metadata"] = json.loads(item["metadata"])
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                result.append(item)
            return result
        except (sqlite3.Error, AttributeError) as e:
            logger.error(f"Failed to get pending payments: {e}")
            return []
    
    def clean_old_payments(self, hours: int = 24) -> int:
        """Clean expired pending payments."""
        try:
            cursor = self.db.cursor()
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
            cursor.execute("""
                DELETE FROM payments 
                WHERE status = 'pending' AND created_at < ?
            """, (cutoff.isoformat(),))
            self.db.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleaned {count} expired payments")
            return count
        except Exception as e:
            logger.error(f"Failed to clean old payments: {e}")
            return 0


# Payment status constants
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_WAITING = "waiting_for_capture"
PAYMENT_STATUS_SUCCEEDED = "succeeded"
PAYMENT_STATUS_CANCELLED = "canceled"
PAYMENT_STATUS_REFUNDED = "refunded"
