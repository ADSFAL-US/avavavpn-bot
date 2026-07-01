"""Tests for SubscriptionRepository."""
import pytest
from datetime import datetime, timedelta
from database import TARIFFS


class TestSubscriptionRepository:
    """Test SubscriptionRepository methods."""

    @pytest.mark.asyncio
    async def test_create_subscription(self, subscription_repo, user_repo, sample_user_data):
        """Test creating a subscription."""
        user = await user_repo.get_or_create(sample_user_data)
        
        sub = await subscription_repo.create(user.user_id, "basic")
        
        assert sub.id is not None
        assert sub.user_id == user.user_id
        assert sub.tariff_id == "basic"
        assert sub.status == "active"
        assert sub.ends_at is not None
        assert sub.speed_mbps == 50.0  # basic tariff speed
        assert sub.warp_enabled is False
        assert sub.test_configs_enabled is True

    @pytest.mark.asyncio
    async def test_create_subscription_with_custom_ends_at(self, subscription_repo, user_repo, sample_user_data):
        """Test creating subscription with custom end date."""
        user = await user_repo.get_or_create(sample_user_data)
        custom_end = datetime.now() + timedelta(days=60)
        
        sub = await subscription_repo.create(user.user_id, "basic", ends_at=custom_end)
        
        assert sub.ends_at is not None
        # Allow small time difference
        assert abs((sub.ends_at - custom_end).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_create_subscription_trial(self, subscription_repo, user_repo, sample_user_data):
        """Test creating trial subscription."""
        user = await user_repo.get_or_create(sample_user_data)
        
        sub = await subscription_repo.create(user.user_id, "trial")
        
        assert sub.tariff_id == "trial"
        assert sub.speed_mbps == 50.0
        assert sub.traffic_limit_mb == 50 * 1024  # 50 GB in MB
        assert sub.warp_enabled is False
        assert sub.test_configs_enabled is False

    @pytest.mark.asyncio
    async def test_create_subscription_premium(self, subscription_repo, user_repo, sample_user_data):
        """Test creating premium subscription."""
        user = await user_repo.get_or_create(sample_user_data)
        
        sub = await subscription_repo.create(user.user_id, "premium")
        
        assert sub.tariff_id == "premium"
        assert sub.speed_mbps == 100.0
        assert sub.traffic_limit_mb is None  # unlimited
        assert sub.warp_enabled is True
        assert sub.test_configs_enabled is True

    @pytest.mark.asyncio
    async def test_get_by_id(self, subscription_repo, user_repo, sample_user_data):
        """Test getting subscription by ID."""
        user = await user_repo.get_or_create(sample_user_data)
        created = await subscription_repo.create(user.user_id, "basic")
        
        found = await subscription_repo.get_by_id(created.id)
        
        assert found is not None
        assert found.id == created.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, subscription_repo):
        """Test getting non-existent subscription."""
        found = await subscription_repo.get_by_id(999999)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_active(self, subscription_repo, user_repo, sample_user_data):
        """Test getting active subscription."""
        user = await user_repo.get_or_create(sample_user_data)
        created = await subscription_repo.create(user.user_id, "basic")
        
        found = await subscription_repo.get_active(user.user_id)
        
        assert found is not None
        assert found.id == created.id

    @pytest.mark.asyncio
    async def test_get_active_none(self, subscription_repo, user_repo, sample_user_data):
        """Test getting active subscription when none exists."""
        user = await user_repo.get_or_create(sample_user_data)
        
        found = await subscription_repo.get_active(user.user_id)
        
        assert found is None

    @pytest.mark.asyncio
    async def test_get_user_subscriptions(self, subscription_repo, user_repo, sample_user_data):
        """Test getting all user subscriptions."""
        user = await user_repo.get_or_create(sample_user_data)
        
        await subscription_repo.create(user.user_id, "basic")
        await subscription_repo.create(user.user_id, "premium")
        
        subs = await subscription_repo.get_user_subscriptions(user.user_id)
        
        assert len(subs) == 2

    @pytest.mark.asyncio
    async def test_extend_subscription(self, subscription_repo, user_repo, sample_user_data):
        """Test extending subscription."""
        user = await user_repo.get_or_create(sample_user_data)
        sub = await subscription_repo.create(user.user_id, "basic")
        original_end = sub.ends_at
        
        result = await subscription_repo.extend(sub.id, 30)
        
        assert result is True
        extended = await subscription_repo.get_by_id(sub.id)
        assert extended.ends_at > original_end
        assert (extended.ends_at - original_end).days == 30

    @pytest.mark.asyncio
    async def test_extend_nonexistent(self, subscription_repo):
        """Test extending non-existent subscription."""
        result = await subscription_repo.extend(999999, 30)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, subscription_repo, user_repo, sample_user_data):
        """Test cancelling subscription."""
        user = await user_repo.get_or_create(sample_user_data)
        sub = await subscription_repo.create(user.user_id, "basic")
        
        result = await subscription_repo.cancel(sub.id, user.user_id)
        
        assert result is True
        cancelled = await subscription_repo.get_by_id(sub.id)
        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_subscription_wrong_user(self, subscription_repo, user_repo, sample_user_data, sample_referrer_data):
        """Test cancelling subscription with wrong user ID."""
        user = await user_repo.get_or_create(sample_user_data)
        other_user = await user_repo.get_or_create(sample_referrer_data)
        sub = await subscription_repo.create(user.user_id, "basic")
        
        result = await subscription_repo.cancel(sub.id, other_user.user_id)
        
        assert result is False
        sub_check = await subscription_repo.get_by_id(sub.id)
        assert sub_check.status == "active"

    @pytest.mark.asyncio
    async def test_change_tariff(self, subscription_repo, user_repo, sample_user_data):
        """Test changing tariff."""
        user = await user_repo.get_or_create(sample_user_data)
        sub = await subscription_repo.create(user.user_id, "basic")
        
        new_sub = await subscription_repo.change_tariff(sub.id, "premium")
        
        assert new_sub is not None
        assert new_sub.tariff_id == "premium"
        assert new_sub.user_id == user.user_id
        
        # Old subscription should be cancelled
        old_sub = await subscription_repo.get_by_id(sub.id)
        assert old_sub.status == "cancelled"

    @pytest.mark.asyncio
    async def test_change_tariff_with_expiry_days(self, subscription_repo, user_repo, sample_user_data):
        """Test changing tariff with custom expiry."""
        user = await user_repo.get_or_create(sample_user_data)
        sub = await subscription_repo.create(user.user_id, "basic")
        
        new_sub = await subscription_repo.change_tariff(sub.id, "premium", expiry_days=60)
        
        assert new_sub is not None
        assert (new_sub.ends_at - datetime.now()).days >= 59  # Allow small difference

    @pytest.mark.asyncio
    async def test_get_active_count(self, subscription_repo, user_repo, sample_user_data, sample_referrer_data):
        """Test getting active subscription count."""
        user1 = await user_repo.get_or_create(sample_user_data)
        user2 = await user_repo.get_or_create(sample_referrer_data)
        
        count_before = await subscription_repo.get_active_count()
        
        await subscription_repo.create(user1.user_id, "basic")
        await subscription_repo.create(user2.user_id, "premium")
        
        count_after = await subscription_repo.get_active_count()
        assert count_after == count_before + 2

    @pytest.mark.asyncio
    async def test_get_subscription_stats(self, subscription_repo, user_repo, sample_user_data, sample_referrer_data):
        """Test getting subscription statistics."""
        user1 = await user_repo.get_or_create(sample_user_data)
        user2 = await user_repo.get_or_create(sample_referrer_data)
        
        await subscription_repo.create(user1.user_id, "basic")
        await subscription_repo.create(user2.user_id, "premium")
        
        stats = await subscription_repo.get_subscription_stats()
        
        assert "basic" in stats
        assert "premium" in stats
        assert stats["basic"]["active_count"] >= 1
        assert stats["premium"]["active_count"] >= 1
        assert stats["basic"]["name"] == TARIFFS["basic"]["name"]