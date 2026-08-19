"""Promo code handlers for Avava VPN Bot."""

import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import db
from utils import STATE_PROMO_CODE, back_btn, btn

logger = logging.getLogger(__name__)


async def handle_promo_activate(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Handle promo code activation from text input."""
    # Handle text input for promo code (when user types the code)
    if context.user_data.get("state") == STATE_PROMO_CODE:
        code = update.message.text.strip().upper()
        context.user_data["state"] = None  # Reset state

        # Activate promo code
        result = db.activate_promo_code(user_id, code)

        if not result.get("success"):
            error = result.get("error", "Неизвестная ошибка")
            await update.message.reply_text(f"❌ {error}", parse_mode="HTML")
            return

        promo = result.get("promo", {})
        result.get("activation_id")

        # Build success message
        text = f"✅ <b>{result.get('message', 'Промокод успешно активирован')}</b>\n\n"

        if promo.get("discount_percent", 0) > 0:
            text += f"💰 Скидка: {promo['discount_percent']}%\n"

        if promo.get("free_days", 0) > 0:
            text += f"⏱ Бесплатные дни: {promo['free_days']}\n"

        if promo.get("activation_text"):
            text += f"\n{promo['activation_text']}\n"

        text += "\n🎉 Промокод применен к вашей следующей подписке!"

        keyboard = [[btn("📋 Тарифы", "menu_tariffs"), back_btn("main_menu")]]
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return


async def handle_promo_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Show promo activation menu - directly prompt for code input."""
    query = update.callback_query

    # Set state to wait for promo code input
    context.user_data["state"] = STATE_PROMO_CODE

    text = (
        "🎁 <b>Активировать промокод</b>\n\n"
        "Введите промокод (буквы и цифры, без пробелов):\n\n"
        "💡 Пример: SAVE20, VPN15, или любой другой промокод"
    )

    keyboard = [[back_btn("main_menu")]]

    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )
