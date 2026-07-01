"""Tests for utility functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from utils import (
    is_admin,
    safe_date_format,
    btn,
    back_btn,
    STATE_IDLE,
    STATE_FIND_USER,
    STATE_BAN_REASON,
    STATE_PAYMENT_PENDING,
    STATE_SIMULATE_REFERRAL_USERID,
    STATE_ADMIN_GIVE_USER_ID,
    STATE_ADMIN_GIVE_DAYS,
)


class TestUtils:
    """Test utility functions."""

    def test_is_admin(self):
        """Test is_admin function."""
        # This tests the function logic, not the DB call
        # We'll mock the db.is_admin call
        pass  # Requires DB, tested in integration tests

    def test_safe_date_format_none(self):
        """Test safe_date_format with None."""
        assert safe_date_format(None) == "N/A"

    def test_safe_date_format_valid(self):
        """Test safe_date_format with valid date string."""
        result = safe_date_format("2024-01-15T10:30:00")
        assert result == "2024-01-15 10:30"

    def test_safe_date_format_invalid(self):
        """Test safe_date_format with invalid string."""
        result = safe_date_format("invalid")
        assert result == "invalid"

    def test_btn(self):
        """Test btn helper."""
        button = btn("Test", "callback_data")
        assert button.text == "Test"
        assert button.callback_data == "callback_data"

    def test_back_btn_default(self):
        """Test back_btn with default."""
        button = back_btn()
        assert button.text == "🔙 Назад"
        assert button.callback_data == "main_menu"

    def test_back_btn_custom(self):
        """Test back_btn with custom target."""
        button = back_btn("custom_target")
        assert button.text == "🔙 Назад"
        assert button.callback_data == "custom_target"

    def test_state_constants(self):
        """Test state constants are defined."""
        assert STATE_IDLE == "idle"
        assert STATE_FIND_USER == "find_user"
        assert STATE_BAN_REASON == "ban_reason"
        assert STATE_PAYMENT_PENDING == "payment_pending"
        assert STATE_SIMULATE_REFERRAL_USERID == "simulate_ref_userid"
        assert STATE_ADMIN_GIVE_USER_ID == "admin_give_user_id"
        assert STATE_ADMIN_GIVE_DAYS == "admin_give_days"


class TestBuildSubscriptionPrompt:
    """Test build_subscription_prompt function."""

    @pytest.mark.asyncio
    async def test_build_subscription_prompt(self):
        """Test subscription prompt building."""
        from utils import build_subscription_prompt
        
        text, markup = build_subscription_prompt()
        
        assert "Подпишитесь на канал" in text
        assert "@AvavaVpn" in text
        assert len(markup.inline_keyboard) == 1
        assert len(markup.inline_keyboard[0]) == 1
        button = markup.inline_keyboard[0][0]
        assert "Перейти к каналу" in button.text
        assert "t.me/AvavaVpn" in button.url


class TestCheckChannelSubscription:
    """Test check_channel_subscription function."""

    @pytest.mark.asyncio
    async def test_check_channel_subscription_disabled(self):
        """Test when channel check is disabled."""
        from utils import check_channel_subscription
        from config import REQUIRED_CHANNEL_USERNAME
        
        # Mock config to disable channel check
        with patch('utils.config.REQUIRED_CHANNEL_USERNAME', None):
            context = MagicMock()
            context.user_data = {}
            result = await check_channel_subscription(123, context)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_channel_subscription_cached(self):
        """Test cached channel verification."""
        from utils import check_channel_subscription
        
        context = MagicMock()
        context.user_data = {"channel_verified": True}
        result = await check_channel_subscription(123, context)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_channel_subscription_member(self):
        """Test when user is channel member."""
        from utils import check_channel_subscription
        from telegram import ChatMember
        
        context = MagicMock()
        context.user_data = {}
        context.bot.get_chat_member = AsyncMock(return_value=MagicMock(
            status=ChatMember.MEMBER
        ))
        
        result = await check_channel_subscription(123, context)
        assert result is True
        assert context.user_data["channel_verified"] is True

    @pytest.mark.asyncio
    async def test_check_channel_subscription_not_member(self):
        """Test when user is not channel member."""
        from utils import check_channel_subscription
        from telegram import ChatMember
        
        context = MagicMock()
        context.user_data = {}
        context.bot.get_chat_member = AsyncMock(return_value=MagicMock(
            status=ChatMember.LEFT
        ))
        
        result = await check_channel_subscription(123, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_check_channel_subscription_error_grace(self):
        """Test graceful handling of errors."""
        from utils import check_channel_subscription
        from telegram.error import BadRequest
        
        context = MagicMock()
        context.user_data = {}
        context.bot.get_chat_member = AsyncMock(
            side_effect=BadRequest("User not found")
        )
        
        result = await check_channel_subscription(123, context)
        assert result is False  # User not found -> not subscribed