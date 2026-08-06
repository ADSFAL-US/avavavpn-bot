"""Safe subscription adapter for bot-side subscription operations.

This module centralizes all subscription lifecycle operations and hides
controller-specific error handling from handlers.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from database import TARIFFS
import xcontroller_client

logger = logging.getLogger(__name__)


class SubscriptionServiceError(Exception):
    """Base error for subscription service failures."""


class SubscriptionService:
    """Safe adapter around local DB and X-Controller subscription operations."""

    def __init__(self, db, xcontroller: Optional[xcontroller_client.XControllerClient] = None):
        self.db = db
        self.xc = xcontroller or xcontroller_client.XControllerClient()

    def create_subscription(
        self,
        user_id: int,
        tariff_id: str,
        payment_id: Optional[str] = None,
        preset_id: Optional[int] = None,
        expiry_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new subscription safely.

        Returns a structured result that does not leak controller-specific failures
        into the bot UI.
        """
        tariff = TARIFFS.get(tariff_id)
        if not tariff:
            return {"success": False, "error": "Invalid tariff", "retryable": False}

        try:
            health = self.xc.health_check()
            if not health or str(health.get("status", "")).lower() != "healthy":
                logger.warning("Panel unavailable during create_subscription: %s", health)
                return {
                    "success": False,
                    "error": "Панель подписок временно недоступна. Пожалуйста, попробуйте позже или обратитесь в поддержку.",
                    "retryable": True,
                    "manual_action_required": True,
                    "status": "panel_unavailable",
                    "details": health.get("error") if isinstance(health, dict) else None,
                }
        except Exception as exc:
            logger.warning("Health check failed during create_subscription: %s", exc)
            return {
                "success": False,
                "error": "Панель подписок временно недоступна. Пожалуйста, попробуйте позже или обратитесь в поддержку.",
                "retryable": True,
                "manual_action_required": True,
                "status": "panel_unavailable",
                "details": str(exc),
            }

        effective_days = expiry_days if expiry_days is not None else tariff.get("duration_days", 30)

        try:
            xc_result = self.xc.create_user_subscription(
                telegram_user_id=user_id,
                tariff=tariff,
                preset_id=preset_id,
                expiry_days=effective_days,
            )
        except xcontroller_client.XControllerAPIError as exc:
            logger.exception("Controller create failed for user %s", user_id)
            return {
                "success": False,
                "error": "Не удалось создать подписку в панели. Повторите попытку позже.",
                "retryable": True,
                "manual_action_required": True,
                "details": str(exc),
            }
        except Exception as exc:
            logger.exception("Unexpected create failure for user %s", user_id)
            return {
                "success": False,
                "error": "Не удалось создать подписку. Обратитесь в поддержку.",
                "retryable": False,
                "manual_action_required": True,
                "details": str(exc),
            }

        if not xc_result.get("success"):
            error = xc_result.get("error", "Unknown error")
            logger.error("Panel create failed: %s", error)
            return {
                "success": False,
                "error": "Не удалось создать подписку в панели.",
                "retryable": True,
                "manual_action_required": True,
                "details": error,
            }

        sub_data = xc_result.get("subscription", {})
        ends_at = None
        if effective_days:
            ends_at = datetime.now() + timedelta(days=effective_days)

        db_sub_id = self.db.create_subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            ends_at=ends_at,
            speed_mbps=self._extract_speed(tariff.get("speed", "0")),
            traffic_limit_mb=tariff.get("traffic_limit_gb", 0) * 1024 if tariff.get("traffic_limit_gb") else None,
            warp_enabled=tariff.get("warp", False),
            test_configs_enabled=tariff.get("test_configs", False),
            panel_subscription_id=sub_data.get("id"),
            panel_sub_token=sub_data.get("sub_token"),
            payment_id=payment_id,
        )

        sub_link = self.xc.get_subscription_link(sub_data.get("sub_token", ""))

        return {
            "success": True,
            "subscription_id": db_sub_id.get("id") if isinstance(db_sub_id, dict) else db_sub_id,
            "panel_subscription_id": sub_data.get("id"),
            "sub_token": sub_data.get("sub_token"),
            "sub_link": sub_link,
            "uuid": sub_data.get("uuid"),
            "email": sub_data.get("email"),
            "status": "active",
        }

    def get_user_subscription_link(self, user_id: int) -> Optional[str]:
        """Return a user subscription link if available."""
        sub = self.db.get_active_subscription(user_id)
        if not sub:
            return None
        sub_token = sub.get("panel_sub_token")
        if sub_token:
            return self.xc.get_subscription_link(sub_token)
        return None

    def extend_subscription(self, subscription_id: int, extra_days: int) -> Dict[str, Any]:
        """Extend an existing subscription safely.

        The service updates the panel first when possible, then updates the local DB.
        If the panel update fails, the local DB is not silently left as success.
        """
        sub = self.db.get_subscription_by_id(subscription_id)
        if not sub:
            return {"success": False, "error": "Subscription not found", "retryable": False}

        try:
            health = self.xc.health_check()
            if not health or str(health.get("status", "")).lower() != "healthy":
                logger.warning("Panel unavailable during extend_subscription: %s", health)
                return {
                    "success": False,
                    "error": "Панель подписок временно недоступна. Продление не выполнено.",
                    "retryable": True,
                    "manual_action_required": True,
                    "status": "panel_unavailable",
                    "details": health.get("error") if isinstance(health, dict) else None,
                }
        except Exception as exc:
            logger.warning("Health check failed during extend_subscription: %s", exc)
            return {
                "success": False,
                "error": "Панель подписок временно недоступна. Продление не выполнено.",
                "retryable": True,
                "manual_action_required": True,
                "status": "panel_unavailable",
                "details": str(exc),
            }

        panel_id = sub.get("panel_subscription_id")
        if panel_id:
            try:
                updated_sub = self.db.get_subscription_by_id(subscription_id)
                if updated_sub and updated_sub.get("ends_at"):
                    ends_at_str = updated_sub.get("ends_at")
                    try:
                        clean = ends_at_str.split("+")[0]
                        new_end = datetime.fromisoformat(clean)
                        # Calculate total days from now to NEW expiry (old expiry + extra_days)
                        remaining_days = max(1, (new_end - datetime.now()).days)
                        total_expiry_days = remaining_days + extra_days
                    except (ValueError, TypeError):
                        total_expiry_days = extra_days
                else:
                    total_expiry_days = extra_days

                self.xc.update_subscription(
                    subscription_id=panel_id,
                    expiry_days=total_expiry_days,
                )
            except xcontroller_client.XControllerAPIError as exc:
                logger.warning("Panel extension failed for sub %s: %s", subscription_id, exc)
                return {
                    "success": False,
                    "error": "Не удалось синхронизировать продление с панелью.",
                    "retryable": True,
                    "manual_action_required": True,
                    "details": str(exc),
                    "subscription_id": subscription_id,
                }
            except Exception as exc:
                logger.exception("Unexpected extension failure for sub %s", subscription_id)
                return {
                    "success": False,
                    "error": "Не удалось синхронизировать продление с панелью.",
                    "retryable": True,
                    "manual_action_required": True,
                    "details": str(exc),
                    "subscription_id": subscription_id,
                }

        self.db.extend_subscription(subscription_id, extra_days)
        updated_sub = self.db.get_subscription_by_id(subscription_id)
        sub_token = updated_sub.get("panel_sub_token") if updated_sub else None
        sub_link = self.xc.get_subscription_link(sub_token) if sub_token else None
        return {
            "success": True,
            "subscription_id": subscription_id,
            "sub_link": sub_link,
            "status": "active",
        }

    def cancel_subscription(self, subscription_id: int) -> Dict[str, Any]:
        """Cancel a subscription safely."""
        try:
            sub = self.db.get_subscription_by_id(subscription_id)
            if not sub:
                return {"success": False, "error": "Subscription not found", "retryable": False}

            panel_id = sub.get("panel_subscription_id")
            if panel_id:
                try:
                    self.xc.delete_subscription(panel_id)
                except xcontroller_client.XControllerAPIError as exc:
                    if exc.status_code == 404:
                        logger.warning("Controller subscription %s already missing", panel_id)
                    else:
                        logger.warning("Controller cancellation failed for sub %s: %s", subscription_id, exc)
                        return {
                            "success": False,
                            "error": "Не удалось отменить подписку в панели.",
                            "retryable": True,
                            "manual_action_required": True,
                            "details": str(exc),
                        }
                except Exception as exc:
                    logger.exception("Unexpected cancellation failure for sub %s", subscription_id)
                    return {
                        "success": False,
                        "error": "Не удалось отменить подписку.",
                        "retryable": True,
                        "manual_action_required": True,
                        "details": str(exc),
                    }

            self.db.cancel_subscription(subscription_id, sub["user_id"])
            return {"success": True, "status": "cancelled"}
        except Exception as exc:
            logger.exception("Failed to cancel subscription %s", subscription_id)
            return {"success": False, "error": "Не удалось отменить подписку.", "retryable": True, "manual_action_required": True, "details": str(exc)}

    def change_subscription(
        self,
        subscription_id: int,
        new_tariff_id: str,
        expiry_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Change tariff safely.

        Prefer updating the existing subscription in the controller when possible.
        Only fall back to create/delete if the controller cannot update an existing record.
        """
        from database import TARIFFS

        current_sub = self.db.get_subscription_by_id(subscription_id)
        if not current_sub:
            return {"success": False, "error": "Current subscription not found", "retryable": False}

        try:
            health = self.xc.health_check()
            if not health or str(health.get("status", "")).lower() != "healthy":
                logger.warning("Panel unavailable during change_subscription: %s", health)
                return {
                    "success": False,
                    "error": "Панель подписок временно недоступна. Смена тарифа не выполнена.",
                    "retryable": True,
                    "manual_action_required": True,
                    "status": "panel_unavailable",
                    "details": health.get("error") if isinstance(health, dict) else None,
                }
        except Exception as exc:
            logger.warning("Health check failed during change_subscription: %s", exc)
            return {
                "success": False,
                "error": "Панель подписок временно недоступна. Смена тарифа не выполнена.",
                "retryable": True,
                "manual_action_required": True,
                "status": "panel_unavailable",
                "details": str(exc),
            }

        user_id = current_sub["user_id"]
        new_tariff = TARIFFS.get(new_tariff_id)
        if not new_tariff:
            return {"success": False, "error": "Invalid tariff", "retryable": False}

        effective_days = expiry_days if expiry_days is not None else new_tariff.get("duration_days", 30)
        panel_id = current_sub.get("panel_subscription_id")

        try:
            if panel_id:
                self.xc.update_subscription(
                    subscription_id=panel_id,
                    expiry_days=effective_days,
                    preset_id=new_tariff.get("preset_id"),
                )
                logger.info("Updated existing panel subscription %s for tariff change", panel_id)
                changed_via_update = True
            else:
                changed_via_update = False
        except xcontroller_client.XControllerAPIError as exc:
            logger.warning("Panel update failed during tariff change for sub %s: %s", subscription_id, exc)
            changed_via_update = False
        except Exception as exc:
            logger.exception("Unexpected panel update failure during tariff change for sub %s", subscription_id)
            changed_via_update = False

        if not changed_via_update:
            try:
                old_panel_id = current_sub.get("panel_subscription_id")
                if old_panel_id:
                    self.xc.delete_subscription(old_panel_id)
                    logger.info("Deleted old panel subscription: %s", old_panel_id)

                xc_result = self.xc.create_user_subscription(
                    telegram_user_id=user_id,
                    tariff=new_tariff,
                    preset_id=new_tariff.get("preset_id"),
                    expiry_days=effective_days,
                )
            except xcontroller_client.XControllerAPIError as exc:
                logger.exception("Fallback create/delete change failed for sub %s", subscription_id)
                return {
                    "success": False,
                    "error": "Не удалось сменить тариф в панели.",
                    "retryable": True,
                    "manual_action_required": True,
                    "details": str(exc),
                }
            except Exception as exc:
                logger.exception("Unexpected fallback change failure for sub %s", subscription_id)
                return {
                    "success": False,
                    "error": "Не удалось сменить тариф.",
                    "retryable": True,
                    "manual_action_required": True,
                    "details": str(exc),
                }

            if not xc_result.get("success"):
                return {
                    "success": False,
                    "error": "Не удалось сменить тариф в панели.",
                    "retryable": True,
                    "manual_action_required": True,
                    "details": xc_result.get("error", "Unknown error"),
                }

            new_sub_data = xc_result.get("subscription", {})
        else:
            new_sub_data = {"id": panel_id, "sub_token": current_sub.get("panel_sub_token"), "uuid": None, "email": None}

        ends_at = None
        if effective_days:
            ends_at = datetime.now() + timedelta(days=effective_days)

        self.db.conn.execute(
            """UPDATE subscriptions SET 
               tariff_id = ?, ends_at = ?, speed_mbps = ?, 
               traffic_limit_mb = ?, warp_enabled = ?, test_configs_enabled = ?,
               panel_subscription_id = ?, panel_sub_token = ?
               WHERE id = ?""",
            (
                new_tariff_id,
                ends_at.isoformat() if ends_at else None,
                self._extract_speed(new_tariff.get("speed", "0")),
                new_tariff.get("traffic_limit_gb", 0) * 1024 if new_tariff.get("traffic_limit_gb") else None,
                new_tariff.get("warp", False),
                new_tariff.get("test_configs", False),
                new_sub_data.get("id"),
                new_sub_data.get("sub_token"),
                subscription_id,
            ),
        )
        self.db.conn.commit()

        sub_link = self.xc.get_subscription_link(new_sub_data.get("sub_token", "")) if new_sub_data.get("sub_token") else None

        return {
            "success": True,
            "subscription_id": subscription_id,
            "panel_subscription_id": new_sub_data.get("id"),
            "sub_token": new_sub_data.get("sub_token"),
            "sub_link": sub_link,
            "uuid": new_sub_data.get("uuid"),
            "email": new_sub_data.get("email"),
            "old_tariff": current_sub["tariff_id"],
            "new_tariff": new_tariff_id,
            "status": "active",
        }

    def _extract_speed(self, speed_str: str) -> int:
        """Extract numeric speed from a string like '50 Мбит/с'."""
        try:
            match = re.search(r'(\d+)', speed_str)
            if match:
                return int(match.group(1))
        except (ValueError, TypeError, AttributeError):
            pass
        return 0
