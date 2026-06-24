"""Subscription handlers for Avava VPN Bot."""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from database import db, TARIFFS
from utils import btn, back_btn
import app_context

logger = logging.getLogger(__name__)


async def handle_free_subscription(update: Update, user_id: int, tariff_id: str, tariff: dict):
    """Handle free subscription (trial tariff) creation."""
    query = update.callback_query
    
    try:
        if not app_context.subscription_manager:
            await query.edit_message_text("❌ Сервис подписок временно недоступен")
            return

        # Create subscription via SubscriptionManager
        result = app_context.subscription_manager.create_subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            preset_id=tariff.get("preset_id"),
        )
        
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Free subscription creation failed: {error}")
            await query.edit_message_text(
                f"❌ <b>Ошибка активации</b>\n\n{error}"
            )
            return
        
        sub_link = result.get("sub_link", "N/A")
        
        # Начисление реферальных дней за пробный тариф
        db.reward_referrer(user_id, tariff_id)
        
        text = (
            f"✅ <b>Подписка активирована!</b>\n\n"
            f"📌 {tariff['name']}\n"
            f"⚡ {tariff['speed']}\n"
            f"⏱ {tariff['duration_days']} дней\n\n"
            f"🔗 <b>Ваша ссылка для подключения:</b>\n"
            f"<code>{sub_link}</code>\n\n"
            f"Скопируйте ссылку и импортируйте в приложение VPN."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Инструкция по настройке", url=sub_link)],
            [btn("📊 Моя подписка", "menu_subscription"), back_btn()]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.exception(f"Error creating free subscription: {e}")
        await query.edit_message_text(f"❌ <b>Ошибка:</b> {str(e)}")


async def create_paid_subscription(update: Update, user_id: int, tariff_id: str, tariff: dict, payment_id: str):
    """Create subscription after successful payment."""
    query = update.callback_query
    
    try:
        if not app_context.subscription_manager:
            await query.edit_message_text(
                f"❌ <b>Сервис подписок недоступен</b>\n\n"
                f"Пожалуйста, обратитесь в поддержку с ID платежа: <code>{payment_id}</code>",
                parse_mode="HTML"
            )
            return

        result = app_context.subscription_manager.create_subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            payment_id=payment_id,
            preset_id=tariff.get("preset_id"),
        )
        
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Paid subscription creation failed: {error}")
            await query.edit_message_text(
                f"❌ <b>Ошибка активации подписки</b>\n\n"
                f"{error}\n\n"
                f"Пожалуйста, обратитесь в поддержку с ID платежа: <code>{payment_id}</code>",
                parse_mode="HTML"
            )
            return
        
        sub_link = result.get("sub_link", "N/A")
        text = (
            f"✅ <b>Оплата успешна!</b>\n\n"
            f"📌 {tariff['name']}\n"
            f"⚡ {tariff['speed']}\n"
            f"⏱ {tariff['duration_days']} дней\n\n"
            f"🔗 <b>Ваша ссылка для подключения:</b>\n"
            f"<code>{sub_link}</code>\n\n"
            f"Скопируйте ссылку и импортируйте в приложение VPN."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Инструкция по настройке", url=sub_link)],
            [btn("📊 Моя подписка", "menu_subscription"), back_btn()]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.exception(f"Error creating paid subscription: {e}")
        await query.edit_message_text(
            f"❌ <b>Ошибка активации</b>\n\n"
            f"Пожалуйста, обратитесь в поддержку с ID платежа: <code>{payment_id}</code>",
            parse_mode="HTML"
        )


async def handle_tariff_change(update: Update, user_id: int, sub_id: int, new_tariff_id: str, new_tariff: dict):
    """Handle tariff change after payment confirmation."""
    query = update.callback_query
    
    try:
        if not app_context.subscription_manager:
            await query.edit_message_text("❌ Сервис подписок недоступен")
            return
        
        result = app_context.subscription_manager.change_subscription(sub_id, new_tariff_id)
        
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Tariff change failed: {error}")
            await query.edit_message_text(
                f"❌ <b>Ошибка смены тарифа</b>\n\n{error}"
            )
            return
        
        sub_link = result.get("sub_link", "N/A")
        old_tariff_name = TARIFFS.get(result.get("old_tariff", ""), {}).get("name", "предыдущий")
        
        text = (
            f"✅ <b>Тариф изменен!</b>\n\n"
            f"🔄 С {old_tariff_name} на {new_tariff['name']}\n"
            f"⚡ {new_tariff['speed']}\n"
            f"⏱ {new_tariff['duration_days']} дней\n\n"
            f"🔗 <b>Ваша новая ссылка:</b>\n"
            f"<code>{sub_link}</code>\n\n"
            f"Скопируйте ссылку и импортируйте в приложение VPN."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Инструкция по настройке", url=sub_link)],
            [btn("📊 Моя подписка", "menu_subscription"), back_btn()]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.exception(f"Error changing tariff: {e}")
        await query.edit_message_text(f"❌ <b>Ошибка:</b> {str(e)}")