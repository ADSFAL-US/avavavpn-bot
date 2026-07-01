"""Tests for UserRepository."""
import pytest
from sqlalchemy import select


class TestUserRepository:
    """Test UserRepository methods."""

    @pytest.mark.asyncio
    async def test_get_or_create_user_creates_new(self, user_repo, sample_user_data):
        """Test creating a new user."""
        user = await user_repo.get_or_create(sample_user_data)
        
        assert user.user_id == sample_user_data["user_id"]
        assert user.username == sample_user_data["username"]
        assert user.first_name == sample_user_data["first_name"]
        assert user.last_name == sample_user_data["last_name"]
        assert user.referral_code is not None
        assert user.referral_code.startswith("REF_")
        assert user.referral_days == 0
        assert user.has_used_discount is False
        assert user.has_rewarded_referrer is False

    @pytest.mark.asyncio
    async def test_get_or_create_user_returns_existing(self, user_repo, sample_user_data):
        """Test getting existing user."""
        user1 = await user_repo.get_or_create(sample_user_data)
        user2 = await user_repo.get_or_create(sample_user_data)
        
        assert user1.user_id == user2.user_id
        assert user1.referral_code == user2.referral_code

    @pytest.mark.asyncio
    async def test_get_by_id(self, user_repo, sample_user_data):
        """Test getting user by ID."""
        created = await user_repo.get_or_create(sample_user_data)
        found = await user_repo.get_by_id(sample_user_data["user_id"])
        
        assert found is not None
        assert found.user_id == created.user_id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, user_repo):
        """Test getting non-existent user."""
        found = await user_repo.get_by_id(999999999)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_referral_code(self, user_repo, sample_user_data):
        """Test getting user by referral code."""
        created = await user_repo.get_or_create(sample_user_data)
        found = await user_repo.get_by_referral_code(created.referral_code)
        
        assert found is not None
        assert found.user_id == created.user_id

    @pytest.mark.asyncio
    async def test_is_admin(self, user_repo, sample_user_data):
        """Test admin check."""
        user = await user_repo.get_or_create(sample_user_data)
        assert await user_repo.is_admin(user.user_id) is False
        
        await user_repo.set_admin(user.user_id)
        assert await user_repo.is_admin(user.user_id) is True

    @pytest.mark.asyncio
    async def test_set_remove_admin(self, user_repo, sample_user_data):
        """Test setting and removing admin."""
        user = await user_repo.get_or_create(sample_user_data)
        
        await user_repo.set_admin(user.user_id)
        found = await user_repo.get_by_id(user.user_id)
        assert found.is_admin is True
        
        await user_repo.remove_admin(user.user_id)
        found = await user_repo.get_by_id(user.user_id)
        assert found.is_admin is False

    @pytest.mark.asyncio
    async def test_add_referral_days(self, user_repo, sample_user_data):
        """Test adding referral days."""
        user = await user_repo.get_or_create(sample_user_data)
        
        await user_repo.add_referral_days(user.user_id, 7)
        found = await user_repo.get_by_id(user.user_id)
        assert found.referral_days == 7
        
        await user_repo.add_referral_days(user.user_id, 3)
        found = await user_repo.get_by_id(user.user_id)
        assert found.referral_days == 10

    @pytest.mark.asyncio
    async def test_reward_referrer(self, user_repo, sample_user_data, sample_referrer_data):
        """Test rewarding referrer."""
        referrer = await user_repo.get_or_create(sample_referrer_data)
        user_data = {**sample_user_data, "referred_by": referrer.user_id}
        user = await user_repo.get_or_create(user_data)
        
        # Reward referrer
        result = await user_repo.reward_referrer(user.user_id, "basic")
        
        assert result is True
        referrer_updated = await user_repo.get_by_id(referrer.user_id)
        assert referrer_updated.referral_days == 7
        
        user_updated = await user_repo.get_by_id(user.user_id)
        assert user_updated.has_rewarded_referrer is True
        assert user_updated.has_used_discount is True  # basic is paid tariff

    @pytest.mark.asyncio
    async def test_reward_referrer_no_referrer(self, user_repo, sample_user_data):
        """Test rewarding when no referrer."""
        user = await user_repo.get_or_create(sample_user_data)
        result = await user_repo.reward_referrer(user.user_id, "basic")
        assert result is False

    @pytest.mark.asyncio
    async def test_reward_referrer_self_referral(self, user_repo, sample_user_data):
        """Test self-referral protection."""
        user_data = {**sample_user_data, "referred_by": sample_user_data["user_id"]}
        user = await user_repo.get_or_create(user_data)
        result = await user_repo.reward_referrer(user.user_id, "basic")
        assert result is False

    @pytest.mark.asyncio
    async def test_reward_referrer_already_rewarded(self, user_repo, sample_user_data, sample_referrer_data):
        """Test that referrer is only rewarded once."""
        referrer = await user_repo.get_or_create(sample_referrer_data)
        user_data = {**sample_user_data, "referred_by": referrer.user_id}
        user = await user_repo.get_or_create(user_data)
        
        await user_repo.reward_referrer(user.user_id, "basic")
        result = await user_repo.reward_referrer(user.user_id, "basic")
        
        assert result is False
        referrer_updated = await user_repo.get_by_id(referrer.user_id)
        assert referrer_updated.referral_days == 7  # Not 14

    @pytest.mark.asyncio
    async def test_reward_referrer_trial_no_discount(self, user_repo, sample_user_data, sample_referrer_data):
        """Test trial tariff doesn't mark discount as used."""
        referrer = await user_repo.get_or_create(sample_referrer_data)
        user_data = {**sample_user_data, "referred_by": referrer.user_id}
        user = await user_repo.get_or_create(user_data)
        
        await user_repo.reward_referrer(user.user_id, "trial")
        
        user_updated = await user_repo.get_by_id(user.user_id)
        assert user_updated.has_used_discount is False  # trial doesn't use discount

    @pytest.mark.asyncio
    async def test_ban_unban_user(self, user_repo, sample_user_data):
        """Test banning and unbanning user."""
        user = await user_repo.get_or_create(sample_user_data)
        
        await user_repo.ban_user(user.user_id, "Test reason", 7)
        found = await user_repo.get_by_id(user.user_id)
        assert found.banned is True
        assert found.ban_reason == "Test reason"
        assert found.ban_expires is not None
        
        await user_repo.unban_user(user.user_id)
        found = await user_repo.get_by_id(user.user_id)
        assert found.banned is False
        assert found.ban_reason is None
        assert found.ban_expires is None

    @pytest.mark.asyncio
    async def test_get_all_users_pagination(self, user_repo, sample_user_data):
        """Test getting users with pagination."""
        # Create multiple users
        for i in range(5):
            await user_repo.get_or_create({
                **sample_user_data,
                "user_id": sample_user_data["user_id"] + i,
                "username": f"user{i}",
            })
        
        users = await user_repo.get_all_users(limit=2, offset=0)
        assert len(users) == 2
        
        users = await user_repo.get_all_users(limit=2, offset=2)
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_get_user_count(self, user_repo, sample_user_data):
        """Test getting user count."""
        count_before = await user_repo.get_user_count()
        await user_repo.get_or_create(sample_user_data)
        count_after = await user_repo.get_user_count()
        assert count_after == count_before + 1

    @pytest.mark.asyncio
    async def test_has_user_ever_had_tariff(self, user_repo, sample_user_data, subscription_repo):
        """Test checking if user ever had a tariff."""
        user = await user_repo.get_or_create(sample_user_data)
        
        # Initially false
        assert await user_repo.has_user_ever_had_tariff(user.user_id, "trial") is False
        
        # Create subscription
        await subscription_repo.create(user.user_id, "trial")
        
        # Now true
        assert await user_repo.has_user_ever_had_tariff(user.user_id, "trial") is True
        assert await user_repo.has_user_ever_had_tariff(user.user_id, "basic") is False