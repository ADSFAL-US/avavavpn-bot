"""
Unit tests for promo code activation and application flow using real SQLite database.

Tests the complete flow implemented in database.py:
1. Activate promo code stores discount/free days on user
2. Create subscription applies the stored promo
3. Pending values are cleared after application
4. Multiple subscriptions don't re-apply the same promo
5. Idempotent promo behavior
6. Non-existent promo code handling
7. Expired promo code handling
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from database import Database


class TestPromoActivationRealDB(unittest.TestCase):
    """Test that activate_promo_code stores promo details on user using real DB."""

    def setUp(self):
        """Create a fresh database for each test."""
        self.db_path = tempfile.gettempdir() + f'/test_avava_promo_{id(self)}.db'
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = Database(self.db_path)

    def tearDown(self):
        """Clean up database after each test."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_user(self, user_id=123):
        """Helper to create a test user."""
        return self.db.get_or_create_user({'user_id': user_id, 'first_name': 'Test', 'username': f'testuser{user_id}'})

    def _create_promo(self, discount_percent=20, free_days=3, is_idempotent=0):
        """Helper to create a promo code."""
        return self.db.create_promo_code(
            code=f"TEST{discount_percent}" if discount_percent > 0 else "FREEDAY",
            discount_percent=discount_percent,
            free_days=free_days,
            is_idempotent=is_idempotent
        )

    def test_activate_promo_stores_discount(self):
        """Activate promo should store discount_percent on user."""
        # Create user first
        self._create_user()
        
        # Create promo with 20% discount
        self._create_promo(discount_percent=20, free_days=3)

        # Activate for user 123
        result = self.db.activate_promo_code(user_id=123, code="TEST20")

        self.assertTrue(result["success"])
        # User should have pending discount stored (accumulated)
        user = self.db.get_user_by_id(123)
        self.assertIsNotNone(user)
        self.assertEqual(user["pending_discount_percent"], 20)
        # Free days should be added to referral_days, not pending_free_days
        self.assertEqual(user["referral_days"], 3)
        self.assertEqual(user["pending_free_days"], 0)

    def test_activate_promo_stores_free_days(self):
        """Activate promo should store free_days on user."""
        # Create user first
        self._create_user(user_id=456)
        
        # Create promo with 7 free days
        self._create_promo(discount_percent=0, free_days=7)

        result = self.db.activate_promo_code(user_id=456, code="FREEDAY")

        self.assertTrue(result["success"])
        user = self.db.get_user_by_id(456)
        self.assertIsNotNone(user)
        self.assertEqual(user["pending_discount_percent"], 0)
        # Free days should be added to referral_days, not pending_free_days
        self.assertEqual(user["referral_days"], 7)
        self.assertEqual(user["pending_free_days"], 0)

    def test_create_subscription_applies_discount(self):
        """Subscription should apply pending discount from promo activation."""
        # Create user first
        self._create_user()
        
        # Create and activate promo with 25% discount
        self._create_promo(discount_percent=25, free_days=0)
        self.db.activate_promo_code(user_id=123, code="TEST25")

        # Create subscription
        sub = self.db.create_subscription(user_id=123, tariff_id="basic")

        # Discount should be applied
        self.assertEqual(sub["applied_discount"], 25)
        # Pending should NOT be cleared by create_subscription (cleared after payment)
        user = self.db.get_user_by_id(123)
        self.assertIsNotNone(user)
        self.assertEqual(user["pending_discount_percent"], 25)
        self.assertEqual(user["pending_free_days"], 0)

    def test_create_subscription_applies_free_days(self):
        """Subscription should apply pending free days from promo activation."""
        # Create user first
        self._create_user()
        
        # Create and activate promo with 3 free days
        self._create_promo(discount_percent=0, free_days=3)
        self.db.activate_promo_code(user_id=123, code="FREEDAY")

        # Create subscription
        sub = self.db.create_subscription(user_id=123, tariff_id="basic")

        # Free days should NOT be applied to subscription (they are in referral_days)
        self.assertEqual(sub["applied_free_days"], 0)
        # Pending should NOT be cleared by create_subscription
        user = self.db.get_user_by_id(123)
        self.assertEqual(user["pending_free_days"], 0)
        # But referral_days should have been increased
        self.assertEqual(user["referral_days"], 3)

    def test_second_subscription_no_reapplication(self):
        """Second subscription should not re-apply the same promo."""
        # Create user first
        self._create_user()
        
        # Create and activate promo with 10% discount
        self._create_promo(discount_percent=10, free_days=0)
        self.db.activate_promo_code(user_id=123, code="TEST10")

        # First subscription
        sub1 = self.db.create_subscription(user_id=123, tariff_id="basic")
        self.assertEqual(sub1["applied_discount"], 10)

        # Second activation should fail because promo already activated
        result2 = self.db.activate_promo_code(user_id=123, code="TEST10")
        self.assertFalse(result2["success"])
        self.assertIn("уже активировали", result2["error"])


class TestPromoActivationIdempotencyRealDB(unittest.TestCase):
    """Test idempotent promo behavior using real SQLite database."""

    def setUp(self):
        """Create a fresh database for each test."""
        self.db_path = tempfile.gettempdir() + f'/test_avava_idempotent_{id(self)}.db'
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = Database(self.db_path)

    def tearDown(self):
        """Clean up database after each test."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_user(self):
        """Helper to create a test user."""
        return self.db.get_or_create_user({'user_id': 123, 'first_name': 'Test', 'username': 'testuser'})

    def _create_promo(self, discount_percent=20, free_days=3, is_idempotent=0):
        """Helper to create a promo code."""
        return self.db.create_promo_code(
            code=f"TEST{discount_percent}" if discount_percent > 0 else "FREEDAY",
            discount_percent=discount_percent,
            free_days=free_days,
            is_idempotent=is_idempotent
        )

    def _create_idempotent_promo(self):
        """Helper to create an idempotent promo."""
        return self.db.create_promo_code("IDEMPOTENT", discount_percent=10,
                                          free_days=5, is_idempotent=1)

    def test_idempotent_promo_cannot_activate_twice(self):
        """Idempotent promo should fail on second activation."""
        # Create user first
        self._create_user()
        
        # Create idempotent promo
        self._create_idempotent_promo()

        # First activation should succeed
        result1 = self.db.activate_promo_code(user_id=123, code="IDEMPOTENT")
        self.assertTrue(result1["success"])

        # Second activation should fail (idempotent)
        result2 = self.db.activate_promo_code(user_id=123, code="IDEMPOTENT")
        self.assertFalse(result2["success"])
        self.assertIn("уже активировали", result2["error"])

    def test_discount_accumulation(self):
        """Multiple promo activations should accumulate discounts (capped at 50%)."""
        # Create user first
        self._create_user()
        
        # Create first promo with 20% discount
        self._create_promo(discount_percent=20, free_days=0)
        result1 = self.db.activate_promo_code(user_id=123, code="TEST20")
        self.assertTrue(result1["success"])
        user = self.db.get_user_by_id(123)
        self.assertEqual(user["pending_discount_percent"], 20)

        # Create second promo with 30% discount
        self._create_promo(discount_percent=30, free_days=0)
        result2 = self.db.activate_promo_code(user_id=123, code="TEST30")
        self.assertTrue(result2["success"])
        user = self.db.get_user_by_id(123)
        # Should accumulate to 50% (capped at 50%)
        self.assertEqual(user["pending_discount_percent"], 50)

    def test_clear_pending_discount(self):
        """clear_pending_discount should return and reset the discount."""
        # Create user first
        self._create_user()
        
        # Create and activate promo with 25% discount
        self._create_promo(discount_percent=25, free_days=0)
        self.db.activate_promo_code(user_id=123, code="TEST25")
        user = self.db.get_user_by_id(123)
        self.assertEqual(user["pending_discount_percent"], 25)

        # Clear pending discount
        cleared = self.db.clear_pending_discount(user_id=123)
        self.assertEqual(cleared, 25)
        user = self.db.get_user_by_id(123)
        self.assertEqual(user["pending_discount_percent"], 0)

    def test_get_pending_discount(self):
        """get_pending_discount should return current discount without modifying it."""
        # Create user first
        self._create_user()
        
        # Initially should be 0
        self.assertEqual(self.db.get_pending_discount(user_id=123), 0)

        # Create and activate promo with 15% discount
        self._create_promo(discount_percent=15, free_days=0)
        self.db.activate_promo_code(user_id=123, code="TEST15")
        self.assertEqual(self.db.get_pending_discount(user_id=123), 15)

        # Should not be cleared
        user = self.db.get_user_by_id(123)
        self.assertEqual(user["pending_discount_percent"], 15)


class TestPromoCodeExistenceRealDB(unittest.TestCase):
    """Test promo code that doesn't exist."""

    def setUp(self):
        """Create a fresh database for each test."""
        self.db_path = tempfile.gettempdir() + f'/test_avava_nonexist_{id(self)}.db'
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = Database(self.db_path)

    def tearDown(self):
        """Clean up database after each test."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_user(self):
        """Helper to create a test user."""
        return self.db.get_or_create_user({'user_id': 123, 'first_name': 'Test', 'username': 'testuser'})

    def test_activate_nonexistent_promo(self):
        """Should fail when activating a non-existent promo code."""
        # Create user first
        self._create_user()
        
        result = self.db.activate_promo_code(user_id=123, code="NONEXISTENT")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Похоже такого промокода не существует")


class TestPromoCodeValidityRealDB(unittest.TestCase):
    """Test promo code validity period."""

    def setUp(self):
        """Create a fresh database for each test."""
        self.db_path = tempfile.gettempdir() + f'/test_avava_validity_{id(self)}.db'
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = Database(self.db_path)

    def tearDown(self):
        """Clean up database after each test."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_user(self):
        """Helper to create a test user."""
        return self.db.get_or_create_user({'user_id': 123, 'first_name': 'Test', 'username': 'testuser'})

    def test_activate_expired_promo(self):
        """Should fail when activating an expired promo."""
        # Create user first
        self._create_user()
        
        # Create promo that expired yesterday
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.db.create_promo_code("EXPIRED", discount_percent=10,
                                  valid_until=yesterday)

        result = self.db.activate_promo_code(user_id=123, code="EXPIRED")
        self.assertFalse(result["success"])
        self.assertIn("недействителен", result["error"])


if __name__ == "__main__":
    unittest.main()
