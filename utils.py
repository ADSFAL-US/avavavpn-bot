"""Utility functions and constants for Avava VPN Bot."""
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
)
from telegram.error import BadRequest

import config
from database import db

logger = logging.getLogger(__name__)

# ===== STATE CONSTANTS =====
STATE_IDLE = "idle"
STATE_FIND_USER = "find_user"
STATE_BAN_REASON = "ban_reason"
STATE_PAYMENT_PENDING = "payment_pending"
STATE_SIMULATE_REFERRAL_USERID = "simulate_ref_userid"
STATE_ADMIN_GIVE_USER_ID = "admin_give_user_id"
STATE_ADMIN_GIVE_DAYS = "admin_give_days"


# ===== HELPERS =====
def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return db.is_admin(user_id) or user_id in config.ADMIN_IDS


async def check_banned(user_id: int) -> bool:
    """Check if user is banned."""
    user = db.get_user_by_id(user_id)
    return user and user.get("banned", 0) == 1


def safe_date_format(date_str: str | None) -> str:
    """Safely format date string."""
    if not date_str:
        return "N/A"
    try:
        return date_str[:16].replace("T", " ")
    except (IndexError, AttributeError):
        return str(date_str)


def btn(text: str, callback: str) -> InlineKeyboardButton:
    """Create inline button."""
    return InlineKeyboardButton(text, callback_data=callback)


def back_btn(to: str = "main_menu") -> InlineKeyboardButton:
    """Create back button."""
    return InlineKeyboardButton("🔙 Назад", callback_data=to)


# ===== CHANNEL SUBSCRIPTION SOFTLOCK =====
async def check_channel_subscription(user_id: int, context) -> bool:
    """Check if user is subscribed to the required channel.
    Returns True if subscribed (or check fails gracefully), False if not subscribed.
    """
    # Cache check — already verified this session
    if context.user_data.get("channel_verified"):
        return True

    channel = config.REQUIRED_CHANNEL_USERNAME
    if not channel:
        return True  # feature disabled

    try:
        member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
            context.user_data["channel_verified"] = True
            return True
        return False
    except BadRequest as e:
        err_msg = str(e).lower()
        logger.info("BadRequest checking subscription for user %s: %s", user_id, e)
        if "user not found" in err_msg or "not found" in err_msg:
            return False
        return True
    except Exception as e:
        logger.warning("Channel subscription check failed for user %s: %s", user_id, e)
        return True  # grace — don't block on errors


def build_subscription_prompt() -> tuple[str, InlineKeyboardMarkup]:
    """Build the subscription prompt message."""
    channel = config.REQUIRED_CHANNEL_USERNAME
    text = (
        "🚫 <b>Подпишитесь на канал</b>\n\n"
        f"Для использования бота необходимо быть подписанным на наш канал "
        f"<a href=\"https://t.me/{channel.lstrip('@')}\">{channel}</a>.\n\n"
        "👇 Перейдите по ссылке ниже, подпишитесь, а затем отправьте <b>любое сообщение</b> боту."
    )
    keyboard = [
        [InlineKeyboardButton("🔗 Перейти к каналу", url=f"https://t.me/{channel.lstrip('@')}")],
    ]
    return text, InlineKeyboardMarkup(keyboard)