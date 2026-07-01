"""Integration tests for DatabaseContext and cross-repository operations."""
import pytest
from datetime import datetime, timedelta
from db.context import DatabaseContext


def unique_user_data(base_data, suffix):
    """Create unique user data for each test."""
    return {**base_data, "user_id": base_data["user_id"] + suffix, "username": f"{base_data['username']}{suffix}"}


class TestDatabaseContext:
    """Test DatabaseContext and transaction handling."""

    @pytest.mark.asyncio
    async def test_context_manager_commits(self, db_context, sample_user_data):
        """Test that context manager commits on success."""
        user_data = unique_user_data(sample_user_data, 1)
        async with db_context as db:
            user = await db.users.get_or_create(user_data)
            await db.users.add_referral_days(user.user_id, 7)
        
        # Verify commit happened - use a new context to query
        async with DatabaseContext() as db:
            found = await db.users.get_by_id(user_data["user_id"])
            assert found.referral_days == 7

    @pytest.mark.asyncio
    async def test_context_manager_rollbacks_on_exception(self, db_context, sample_user_data):
        """Test that context manager rolls back on exception."""
        user_data = unique_user_data(sample_user_data, 2)
        try:
            async with db_context as db:
                user = await db.users.get_or_create(user_data)
                await db.users.add_referral_days(user.user_id, 7)
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Verify rollback happened
        async with DatabaseContext() as db:
            found = await db.users.get_by_id(user_data["user_id"])
            assert found.referral_days == 0

    @pytest.mark.asyncio
    async def test_atomic_referrer_reward(self, db_context, sample_user_data, sample_referrer_data):
        """Test atomic referrer reward in single transaction."""
        referrer_data = unique_user_data(sample_referrer_data, 10)
        user_data = unique_user_data(sample_user_data, 11)
        user_data["referred_by"] = referrer_data["user_id"]
        
        async with db_context as db:
            referrer = await db.users.get_or_create(referrer_data)
            user = await db.users.get_or_create(user_data)
            
            # Reward referrer - should be atomic
            result = await db.users.reward_referrer(user.user_id, "basic")
            
            assert result is True
        
        # Verify both changes committed
        async with DatabaseContext() as db:
            referrer_updated = await db.users.get_by_id(referrer.user_id)
            user_updated = await db.users.get_by_id(user.user_id)
        
        assert referrer_updated.referral_days == 7
        assert user_updated.has_rewarded_referrer is True
        assert user_updated.has_used_discount is True
        
        # Verify both changes committed
        async with DatabaseContext() as db:
            referrer_updated = await db.users.get_by_id(referrer.user_id)
            user_updated = await db.users.get_by_id(user.user_id)
        
        assert referrer_updated.referral_days == 7
        assert user_updated.has_rewarded_referrer is True
        assert user_updated.has_used_discount is True

    @pytest.mark.asyncio
    async def test_subscription_create_and_extend_atomic(self, db_context, sample_user_data):
        """Test subscription creation and extension in transaction."""
        async with db_context as db:
            user = await db.users.get_or_create(sample_user_data)
            sub = await db.subscriptions.create(user.user_id, "basic")
            original_end = sub.ends_at
            
            await db.subscriptions.extend(sub.id, 30)
        
        # Verify both operations committed
        async with DatabaseContext() as db:
            extended = await db.subscriptions.get_by_id(sub.id)
        assert extended.ends_at > original_end
        assert (extended.ends_at - original_end).days == 30

    @pytest.mark.asyncio
    async def test_payment_atomic_mark_completed(self, db_context, sample_user_data):
        """Test atomic payment completion."""
        async with db_context as db:
            user = await db.users.get_or_create(sample_user_data)
            await db.payments.create(
                order_id="atomic_test",
                user_id=user.user_id,
                tariff_id="basic",
                amount=99.0,
                payment_id="pay_atomic",
            )
            
            # First completion should succeed
            result1 = await db.payments.mark_completed("atomic_test", "pay_atomic")
            assert result1 is True
            
            # Second should fail
            result2 = await db.payments.mark_completed("atomic_test", "pay_atomic")
            assert result2 is False

    @pytest.mark.asyncio
    async def test_change_tariff_atomic(self, db_context, user_repo, sample_user_data):
        """Test tariff change is atomic (cancel old + create new)."""
        async with db_context as db:
            user = await db.users.get_or_create(sample_user_data)
            old_sub = await db.subscriptions.create(user.user_id, "basic")
            
            new_sub = await db.subscriptions.change_tariff(old_sub.id, "premium")
        
        # Verify both operations committed
        old_check = await db_context.subscriptions.get_by_id(old_sub.id)
        new_check = await db_context.subscriptions.get_by_id(new_sub.id)
        
        assert old_check.status == "cancelled"
        assert new_check.tariff_id == "premium"
        assert new_check.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_concurrent_referrer_rewards(self, db_context, user_repo, sample_user_data, sample_referrer_data):
        """Test concurrent referrer rewards don't double count."""
        referrer = await user_repo.get_or_create(sample_referrer_data)
        
        # Create two users referred by same referrer
        user1_data = {**sample_user_data, "user_id": sample_user_data["user_id"] + 1, "referred_by": referrer.user_id}
        user2_data = {**sample_user_data, "user_id": sample_user_data["user_id"] + 2, "referred_by": referrer.user_id}
        
        user1 = await user_repo.get_or_create(user1_data)
        user2 = await user_repo.get_or_create(user2_data)
        
        # Reward both concurrently (simulated sequentially here)
        async with db_context as db:
            await db.users.reward_referrer(user1.user_id, "basic")
        
        async with db_context as db:
            await db.users.reward_referrer(user2.user_id, "basic")
        
        # Referrer should only get 7 days total (second reward should fail)
        referrer_updated = await user_repo.get_by_id(referrer.user_id)
        assert referrer_updated.referral_days == 7


class TestCrossRepositoryConsistency:
    """Test consistency across repositories."""

    @pytest.mark.asyncio
    async def test_user_subscription_link(self, db_context, user_repo, sample_user_data):
        """Test user-subscription relationship."""
        async with db_context as db:
            user = await db.users.get_or_create(sample_user_data)
            sub = await db.subscriptions.create(user.user_id, "basic")
        
        # Verify from user side
        active = await db_context.users.get_active_subscription(user.user_id)
        assert active is not None
        assert active.id == sub.id
        
        # Verify from subscription side
        sub_check = await db_context.subscriptions.get_by_id(sub.id)
        assert sub_check.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_payment_user_link(self, db_context, user_repo, sample_user_data):
        """Test payment-user relationship."""
        async with db_context as db:
            user = await db.users.get_or_create(sample_user_data)
            payment = await db.payments.create(
                order_id="link_test",
                user_id=user.user_id,
                tariff_id="basic",
                amount=99.0,
            )
        
        # Verify payment belongs to user
        found = await db_context.payments.get_by_order_id("link_test")
        assert found.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_admin_log_user_link(self, db_context, user_repo, sample_user_data, sample_referrer_data):
        """Test admin log links to users."""
        async with db_context as db:
            admin = await db.users.get_or_create(sample_referrer_data)
            target = await db.users.get_or_create(sample_user_data)
            
            await db.admin.log_action(admin.user_id, "ban", target.user_id, "Test")
        
        logs = await db_context.admin.get_logs(limit=10)
        assert len(logs) >= 1
        assert logs[0]["admin_id"] == admin.user_id
        assert logs[0]["target_user_id"] == target.user_id
        assert logs[0]["admin_first_name"] == admin.first_name