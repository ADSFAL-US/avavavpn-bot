# Avava VPN Bot - X-Controller (Subscription Panel) REST API Client
import requests
import logging
from typing import Optional, Dict, Any, List
import config

logger = logging.getLogger(__name__)


class XControllerError(Exception):
    """Base exception for X-Controller API errors."""
    pass


class XControllerAuthError(XControllerError):
    """Authentication error."""
    pass


class XControllerAPIError(XControllerError):
    """API request error."""
    
    def __init__(self, message: str, status_code: int = None, response: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class XControllerClient:
    """
    REST API client for X-Controller (Subscription Panel).
    
    Provides methods to manage subscriptions via the panel's REST API.
    """
    
    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None,
        timeout: int = 30,
    ):
        self.base_url = (base_url or config.XCONTROLLER_URL).rstrip("/")
        self.username = username or config.XCONTROLLER_USERNAME
        self.password = password or config.XCONTROLLER_PASSWORD
        self.timeout = timeout
        
        if not self.password:
            logger.warning("X-Controller password not set! API calls will fail.")
        
        self._auth = (self.username, self.password)
        self._session = requests.Session()
        self._session.auth = self._auth
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated request to API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            json_data: JSON body for POST/PUT
            params: Query parameters
        
        Returns:
            Parsed JSON response
        
        Raises:
            XControllerAuthError: If authentication fails
            XControllerAPIError: If API returns error
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            
            if response.status_code == 401:
                logger.error(f"X-Controller authentication failed for {endpoint}")
                raise XControllerAuthError("Invalid credentials for X-Controller")
            
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                data = response.json()
                return data
            except ValueError:
                # Non-JSON response
                return {"success": True, "raw_response": response.text}
                
        except requests.exceptions.Timeout:
            logger.error(f"X-Controller timeout: {endpoint}")
            raise XControllerAPIError(f"Request timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"X-Controller connection error: {e}")
            raise XControllerAPIError(f"Cannot connect to X-Controller: {e}")
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", str(e))
            except ValueError:
                error_msg = str(e)
                error_data = None
            
            logger.error(f"X-Controller API error {status_code}: {error_msg}")
            raise XControllerAPIError(error_msg, status_code, error_data)
        except Exception as e:
            logger.exception(f"Unexpected error calling X-Controller: {e}")
            raise XControllerAPIError(f"Internal error: {e}")
    
    # ============ Subscriptions API ============
    
    def create_subscription(
        self,
        email: str,
        total_gb: float = 0,
        expiry_days: int = 30,
        preset_id: Optional[int] = None,
        enabled: bool = True,
        flow: str = "xtls-rprx-vision",
        uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new subscription in the panel.
        
        Args:
            email: User email (unique identifier)
            total_gb: Traffic limit in GB (0 = unlimited)
            expiry_days: Subscription duration in days (0 = never expires)
            preset_id: Preset ID for config filtering (None = no preset)
            enabled: Whether subscription is active
            flow: VLESS flow type
            uuid: Optional UUID (auto-generated if not provided)
        
        Returns:
            Dict with created subscription data including:
            - id: Subscription ID in panel
            - sub_token: Token for subscription link
            - sub_id: subId for 3x-ui
            - uuid: Assigned UUID
        """
        data = {
            "email": email,
            "total_gb": total_gb,
            "expiry_days": expiry_days,
            "enabled": enabled,
            "flow": flow,
        }
        
        if preset_id is not None:
            data["preset_id"] = preset_id
        
        if uuid:
            data["uuid"] = uuid
        
        logger.info(f"Creating subscription: email={email}, preset={preset_id}")
        result = self._make_request("POST", "/api/subscriptions", json_data=data)
        
        if result.get("success"):
            sub = result.get("subscription", {})
            logger.info(
                f"Subscription created: id={sub.get('id')}, "
                f"token={sub.get('sub_token', 'N/A')[:10]}..."
            )
        
        return result
    
    def get_subscription(self, subscription_id: int) -> Dict[str, Any]:
        """Get subscription by ID."""
        return self._make_request("GET", f"/api/subscriptions/{subscription_id}")
    
    def update_subscription(
        self,
        subscription_id: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Update subscription fields.
        
        Supported fields: email, total_gb, expiry_days, preset_id, enabled, flow
        """
        return self._make_request(
            "PUT",
            f"/api/subscriptions/{subscription_id}",
            json_data=kwargs,
        )
    
    def delete_subscription(self, subscription_id: int) -> Dict[str, Any]:
        """Delete subscription from panel."""
        return self._make_request("DELETE", f"/api/subscriptions/{subscription_id}")
    
    def list_subscriptions(self) -> List[Dict[str, Any]]:
        """Get all subscriptions from panel."""
        result = self._make_request("GET", "/api/subscriptions")
        return result.get("subscriptions", [])
    
    def sync_subscription(self, subscription_id: int) -> Dict[str, Any]:
        """Force sync subscription with 3x-ui panels."""
        return self._make_request("POST", f"/api/sync/{subscription_id}")
    
    # ============ Presets API ============
    
    def list_presets(self) -> List[Dict[str, Any]]:
        """Get all available presets."""
        result = self._make_request("GET", "/api/presets")
        return result.get("presets", [])
    
    def get_preset(self, preset_id: int) -> Optional[Dict[str, Any]]:
        """Get preset by ID."""
        try:
            result = self._make_request("GET", f"/api/presets/{preset_id}")
            return result.get("preset")
        except XControllerAPIError:
            return None
    
    # ============ Health Check ============
    
    def health_check(self) -> Dict[str, Any]:
        """Check panel health and panel connectivity."""
        try:
            return self._make_request("GET", "/api/health")
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    # ============ Helper Methods ============
    
    def get_subscription_link(self, sub_token: str) -> str:
        """Generate subscription link URL."""
        return f"{self.base_url}/sub/{sub_token}"
    
    def create_user_subscription(
        self,
        telegram_user_id: int,
        tariff: Dict[str, Any],
        preset_id: Optional[int] = None,
        expiry_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create subscription for a Telegram user based on tariff.
        
        This is a high-level helper that creates email from user_id
        and applies tariff settings.
        
        Args:
            telegram_user_id: Telegram user ID
            tariff: Tariff dict from TARIFFS
            preset_id: Override preset (uses tariff preset if not specified)
            expiry_days: Override expiry days (uses tariff duration if not set)
        
        Returns:
            Dict with subscription data or error
        """
        email = f"user_{telegram_user_id}@avava.vpn"
        
        # Use tariff preset if not overridden
        if preset_id is None and "preset_id" in tariff:
            preset_id = tariff["preset_id"]
        
        # Calculate expiry based on tariff duration (or override)
        if expiry_days is None:
            expiry_days = tariff.get("duration_days", 30)
        
        # Traffic limit
        traffic_limit_gb = tariff.get("traffic_limit_gb", 0)
        
        return self.create_subscription(
            email=email,
            total_gb=traffic_limit_gb or 0,  # 0 = unlimited
            expiry_days=expiry_days,
            preset_id=preset_id,
            enabled=True,
        )


class SubscriptionManager:
    """
    High-level subscription manager that combines local DB and X-Controller.
    
    This class handles the full lifecycle:
    1. Create subscription in panel
    2. Save to local database
    3. Handle renewals and updates
    """
    
    def __init__(self, db, xcontroller: Optional[XControllerClient] = None):
        self.db = db
        self.xc = xcontroller or XControllerClient()
    
    def create_subscription(
        self,
        user_id: int,
        tariff_id: str,
        payment_id: Optional[str] = None,
        preset_id: Optional[int] = None,
        expiry_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create complete subscription for user.
        
        Args:
            user_id: Telegram user ID
            tariff_id: Selected tariff
            payment_id: Optional payment reference
            preset_id: Override preset
            expiry_days: Override duration in days (uses tariff default if None)
        
        Returns:
            Dict with success status, subscription data, and VPN link
        """
        from database import TARIFFS
        
        tariff = TARIFFS.get(tariff_id)
        if not tariff:
            return {"success": False, "error": "Invalid tariff"}
        
        try:
            # Determine effective duration
            effective_days = expiry_days if expiry_days is not None else tariff.get("duration_days", 30)
            
            # 1. Create in X-Controller
            xc_result = self.xc.create_user_subscription(
                telegram_user_id=user_id,
                tariff=tariff,
                preset_id=preset_id,
                expiry_days=effective_days,
            )
            
            if not xc_result.get("success"):
                error = xc_result.get("error", "Unknown error")
                logger.error(f"Failed to create subscription in panel: {error}")
                return {"success": False, "error": f"Panel error: {error}"}
            
            sub_data = xc_result.get("subscription", {})
            
            # 2. Save to local DB
            ends_at = None
            if effective_days:
                from datetime import datetime, timedelta
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
            
            # 3. Generate subscription link
            sub_link = self.xc.get_subscription_link(sub_data.get("sub_token", ""))
            
            logger.info(
                f"Subscription created successfully: "
                f"user={user_id}, tariff={tariff_id}, panel_id={sub_data.get('id')}"
            )
            
            return {
                "success": True,
                "subscription_id": db_sub_id,
                "panel_subscription_id": sub_data.get("id"),
                "sub_token": sub_data.get("sub_token"),
                "sub_link": sub_link,
                "uuid": sub_data.get("uuid"),
                "email": sub_data.get("email"),
            }
            
        except Exception as e:
            logger.exception(f"Failed to create subscription: {e}")
            return {"success": False, "error": str(e)}
    
    def get_user_subscription_link(self, user_id: int) -> Optional[str]:
        """Get subscription link for user."""
        sub = self.db.get_active_subscription(user_id)
        if not sub:
            return None
        
        sub_token = sub.get("panel_sub_token")
        if sub_token:
            return self.xc.get_subscription_link(sub_token)
        
        return None
    
    def extend_subscription(self, subscription_id: int, extra_days: int) -> dict:
        """
        Extend an existing subscription: update local DB + notify x-controller
        so panels get the new expiry date.

        Args:
            subscription_id: Local subscription ID
            extra_days: Number of days to add

        Returns:
            Dict with success status, new ends_at and sub_link
        """
        sub = self.db.get_subscription_by_id(subscription_id)
        if not sub:
            return {"success": False, "error": "Subscription not found"}

        # 1. Extend in local DB (this also recalculates ends_at)
        self.db.extend_subscription(subscription_id, extra_days)

        # 2. Refresh sub to get updated ends_at and calculate total expiry_days
        updated_sub = self.db.get_subscription_by_id(subscription_id)
        panel_id = updated_sub.get("panel_subscription_id")

        if panel_id:
            # Calculate total expiry days from creation or from now + extra
            from datetime import datetime
            ends_at_str = updated_sub.get("ends_at")
            if ends_at_str:
                try:
                    clean = ends_at_str.split("+")[0]
                    new_end = datetime.fromisoformat(clean)
                    # Calculate how many days from now to new end
                    total_expiry_days = max(1, (new_end - datetime.now()).days)
                except (ValueError, TypeError):
                    total_expiry_days = extra_days
            else:
                total_expiry_days = extra_days

            try:
                # 3. Update expiry on x-controller → triggers sync to panels
                self.xc.update_subscription(
                    subscription_id=panel_id,
                    expiry_days=total_expiry_days,
                )
                logger.info(
                    f"Extended panel subscription {panel_id} by {extra_days} days "
                    f"(total_expiry_days={total_expiry_days})"
                )
            except Exception as e:
                logger.error(f"Failed to update x-controller for extension: {e}")
                # Don't fail — local DB is updated, panel sync will catch up

        # 4. Build subscription link
        sub_token = updated_sub.get("panel_sub_token")
        sub_link = self.xc.get_subscription_link(sub_token) if sub_token else None

        logger.info(f"Subscription {subscription_id} extended by {extra_days} days")

        return {
            "success": True,
            "subscription_id": subscription_id,
            "sub_link": sub_link,
        }

    def cancel_subscription(self, subscription_id: int) -> bool:
        """Cancel subscription in both panel and local DB."""
        try:
            sub = self.db.get_subscription_by_id(subscription_id)
            if not sub:
                return False
            
            panel_id = sub.get("panel_subscription_id")
            if panel_id:
                try:
                    self.xc.delete_subscription(panel_id)
                except XControllerAPIError as e:
                    if e.status_code == 404:
                        logger.warning(f"Subscription {panel_id} not found in controller")
                    else:
                        raise
            
            self.db.cancel_subscription(subscription_id, sub['user_id'])
            return True
        except Exception as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False
    
    def change_subscription(
        self,
        subscription_id: int,
        new_tariff_id: str,
        expiry_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Change subscription to a new tariff.
        
        This will:
        1. Cancel old subscription in panel
        2. Create new subscription with new tariff
        3. Update existing DB record
        4. Generate new subscription link
        
        Args:
            subscription_id: Current subscription ID
            new_tariff_id: New tariff ID
            expiry_days: Override duration in days (uses tariff default if None)
            
        Returns:
            Dict with success status and new subscription data
        """
        from database import TARIFFS
        
        # Get current subscription
        current_sub = self.db.get_subscription_by_id(subscription_id)
        if not current_sub:
            return {"success": False, "error": "Current subscription not found"}
        
        user_id = current_sub["user_id"]
        new_tariff = TARIFFS.get(new_tariff_id)
        if not new_tariff:
            return {"success": False, "error": "Invalid tariff"}
        
        try:
            # Determine effective duration
            effective_days = expiry_days if expiry_days is not None else new_tariff.get("duration_days", 30)
            
            # 1. Cancel old subscription in panel
            old_panel_id = current_sub.get("panel_subscription_id")
            if old_panel_id:
                self.xc.delete_subscription(old_panel_id)
                logger.info(f"Deleted old panel subscription: {old_panel_id}")
            
            # 2. Create new subscription in panel
            xc_result = self.xc.create_user_subscription(
                telegram_user_id=user_id,
                tariff=new_tariff,
                preset_id=new_tariff.get("preset_id"),
                expiry_days=effective_days,
            )
            
            if not xc_result.get("success"):
                error = xc_result.get("error", "Unknown error")
                logger.error(f"Failed to create new subscription in panel: {error}")
                return {"success": False, "error": f"Panel error: {error}"}
            
            new_sub_data = xc_result.get("subscription", {})
            
            # 3. Update existing DB record with new tariff and panel data
            ends_at = None
            if effective_days:
                from datetime import datetime, timedelta
                ends_at = datetime.now() + timedelta(days=effective_days)
            
            # Update the existing subscription record
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
                )
            )
            self.db.conn.commit()
            
            # 4. Generate new subscription link
            sub_link = self.xc.get_subscription_link(new_sub_data.get("sub_token", ""))
            
            logger.info(
                f"Subscription changed successfully: "
                f"user={user_id}, old_tariff={current_sub['tariff_id']}, "
                f"new_tariff={new_tariff_id}, new_panel_id={new_sub_data.get('id')}"
            )
            
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
            }
            
        except Exception as e:
            logger.exception(f"Failed to change subscription: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_speed(self, speed_str: str) -> int:
        """Extract numeric speed from string like '50 Мбит/с'."""
        try:
            # Extract first number from string
            import re
            match = re.search(r'(\d+)', speed_str)
            if match:
                return int(match.group(1))
        except (ValueError, TypeError, AttributeError):
            pass
        return 0
