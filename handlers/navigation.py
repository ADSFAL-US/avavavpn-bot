# handlers/navigation.py — Main menu navigation, tariffs, subscriptions, referral
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db, TARIFFS
import app_context
from utils import (
    safe_date_format, btn, back_btn,
)
from keyboards import (
    build_main_menu, build_tariffs_menu, build_tariff_detail,
    build_subscription_view, build_referral_menu, build_use_days_menu,
)

logger = logging.getLogger(__name__)


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_main_menu(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_menu_tariffs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_tariffs_menu()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_menu_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_subscription_view(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_menu_support(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text = (
        "🛠 <b>Поддержка Avava VPN</b>\n\n"
        "Если у вас возникли вопросы или проблемы, "
        "перейдите в наш чат поддержки — там вам помогут!\n\n"
        "👇 Нажмите кнопку ниже, чтобы открыть чат."
    )
    keyboard = [
        [InlineKeyboardButton("📨 Открыть чат поддержки", url="https://t.me/+2I6sevlNpo5mMjcy")],
        [back_btn()],
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_menu_referral(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_referral_menu(user_id)
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        if "not modified" in str(e):
            await query.answer("📊 Данные актуальны")
        else:
            raise


async def handle_use_days_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_use_days_menu(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, tariff_id: str):
    query = update.callback_query
    text, markup = build_tariff_detail(tariff_id, user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_get_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: str):
    query = update.callback_query
    try:
        sid = int(sub_id)
        active_sub = db.get_subscription_by_id(sid)
        if not active_sub or active_sub["user_id"] != user_id:
            await query.edit_message_text("❌ Подписка не найдена")
            return

        link = app_context.subscription_manager.get_user_subscription_link(user_id)
        if link:
            text = (
                "🔗 <b>Ваша ссылка для подключения</b>\n\n"
                f"<code>{link}</code>\n\n"
                "Скопируйте ссылку и импортируйте в приложение VPN."
            )
            keyboard = [[btn("📊 Моя подписка", "menu_subscription"), back_btn()]]
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ Ссылка не найдена. Возможно, подписка неактивна.")
    except ValueError:
        await query.edit_message_text("❌ Ошибка ID подписки")


async def handle_confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: str):
    query = update.callback_query
    text = (
        "⚠️ <b>Отменить подписку?</b>\n\n"
        "Подписка будет деактивирована.\n"
        "Это действие нельзя отменить."
    )
    keyboard = [
        [btn("✅ Да, отменить", f"cancel_{sub_id}"), btn("❌ Нет", "menu_subscription")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: str):
    query = update.callback_query
    try:
        sid = int(sub_id)
        if app_context.subscription_manager:
            success = app_context.subscription_manager.cancel_subscription(sid)
        else:
            success = db.cancel_subscription(sid, user_id)

        if success:
            text = "✅ Подписка отменена"
        else:
            text = "❌ Не удалось отменить"
    except ValueError:
        text = "❌ Ошибка ID подписки"

    keyboard = [[btn("📋 Тарифы", "menu_tariffs"), btn("📊 Подписка", "menu_subscription")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_use_days_apply(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: str):
    query = update.callback_query
    try:
        sid = int(sub_id)
        active_sub = db.get_subscription_by_id(sid)
        if not active_sub or active_sub["user_id"] != user_id:
            await query.edit_message_text("❌ Подписка не найдена")
            return

        user_info = db.get_user_by_id(user_id)
        days_available = int(user_info.get("referral_days", 0))
        if not user_info or days_available <= 0:
            await query.edit_message_text("❌ У вас нет дней для использования")
            return

        tariff = TARIFFS.get(active_sub["tariff_id"])
        if not tariff:
            await query.edit_message_text("❌ Тариф не найден")
            return

        # Calculate effective days (premium = 0.8 multiplier)
        days_to_add = days_available
        if tariff["id"] == "premium":
            days_to_add = int(days_available * 0.8)

        # Extend subscription in local DB
        db.extend_subscription(sid, days_to_add)

        # Reset referral days
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE users SET referral_days = 0 WHERE user_id = ?",
            (user_id,)
        )
        db.conn.commit()

        # Refresh data to show new ends_at
        updated_sub = db.get_subscription_by_id(sid)
        new_ends = safe_date_format(updated_sub.get("ends_at")) if updated_sub else "N/A"

        await query.edit_message_text(
            f"✅ <b>Дни применены!</b>\n\n"
            f"📌 {tariff.get('name', 'Подписка')}\n"
            f"🪙 Списано дней: <b>{days_available}</b>\n"
            f"➕ Добавлено к подписке: <b>{days_to_add}</b> дней\n"
            f"⏱ Новая дата окончания: <b>{new_ends}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [btn("📊 Моя подписка", "menu_subscription")],
                [btn("👥 Реферальная система", "menu_referral")],
            ])
        )

    except Exception as e:
        logger.error(f"Error using referral days: {e}")
        await query.edit_message_text("❌ Ошибка при использовании дней")