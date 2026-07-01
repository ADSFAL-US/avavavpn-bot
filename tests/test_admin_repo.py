"""Tests for AdminRepository."""
import pytest


class TestAdminRepository:
    """Test AdminRepository methods."""

    @pytest.mark.asyncio
    async def test_log_action(self, admin_repo, user_repo, sample_user_data, sample_referrer_data):
        """Test logging admin action."""
        admin = await user_repo.get_or_create(sample_referrer_data)
        target = await user_repo.get_or_create(sample_user_data)
        
        log = await admin_repo.log_action(admin.user_id, "ban", target.user_id, "Test reason")
        
        assert log.id is not None
        assert log.admin_id == admin.user_id
        assert log.action == "ban"
        assert log.target_user_id == target.user_id
        assert log.details == "Test reason"

    @pytest.mark.asyncio
    async def test_get_logs(self, admin_repo, user_repo, sample_user_data, sample_referrer_data):
        """Test getting admin logs."""
        admin = await user_repo.get_or_create(sample_referrer_data)
        target = await user_repo.get_or_create(sample_user_data)
        
        await admin_repo.log_action(admin.user_id, "ban", target.user_id, "Reason 1")
        await admin_repo.log_action(admin.user_id, "unban", target.user_id, "Reason 2")
        
        logs = await admin_repo.get_logs(limit=10)
        
        assert len(logs) >= 2
        assert logs[0]["action"] == "unban"  # Most recent first
        assert logs[1]["action"] == "ban"
        assert logs[0]["admin_first_name"] == admin.first_name

    @pytest.mark.asyncio
    async def test_get_logs_limit(self, admin_repo, user_repo, sample_user_data, sample_referrer_data):
        """Test admin logs limit."""
        admin = await user_repo.get_or_create(sample_referrer_data)
        target = await user_repo.get_or_create(sample_user_data)
        
        for i in range(5):
            await admin_repo.log_action(admin.user_id, f"action_{i}", target.user_id, f"Detail {i}")
        
        logs = await admin_repo.get_logs(limit=3)
        
        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_get_subscription_stats(self, admin_repo, user_repo, subscription_repo, sample_user_data, sample_referrer_data):
        """Test getting subscription statistics."""
        user1 = await user_repo.get_or_create(sample_user_data)
        user2 = await user_repo.get_or_create(sample_referrer_data)
        
        await subscription_repo.create(user1.user_id, "basic")
        await subscription_repo.create(user2.user_id, "premium")
        
        stats = await admin_repo.get_subscription_stats()
        
        assert "basic" in stats
        assert "premium" in stats
        assert stats["basic"]["active_count"] >= 1
        assert stats["premium"]["active_count"] >= 1

    @pytest.mark.asyncio
    async def test_get_user_count(self, admin_repo, user_repo, sample_user_data):
        """Test getting user count."""
        count_before = await admin_repo.get_user_count()
        await user_repo.get_or_create(sample_user_data)
        count_after = await admin_repo.get_user_count()
        assert count_after == count_before + 1

    @pytest.mark.asyncio
    async def test_get_active_subscription_count(self, admin_repo, user_repo, subscription_repo, sample_user_data):
        """Test getting active subscription count."""
        user = await user_repo.get_or_create(sample_user_data)
        
        count_before = await admin_repo.get_active_subscription_count()
        await subscription_repo.create(user.user_id, "basic")
        count_after = await admin_repo.get_active_subscription_count()
        assert count_after == count_before + 1