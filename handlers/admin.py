# handlers/admin.py — Admin panel, user management, bans, give subscription, referral simulation
import logging

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db, TARIFFS
from utils import (
    STATE_FIND_USER, STATE_BAN_REASON, STATE_ADMIN_GIVE_USER_ID,
    STATE_ADMIN_GIVE_DAYS, STATE_SIMULATE_REFERRAL_USERID,
    back_btn,
)
from keyboards import (
    build_admin_panel, build_admin_stats, build_admin_users,
    build_admin_subscriptions, build_admin_logs,
)

logger = logging.getLogger(__name__)


async def handle_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_admin_panel(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_admin_stats()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_admin_users()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_admin_subscriptions()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    text, markup = build_admin_logs()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_give_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    context.user_data["state"] = STATE_ADMIN_GIVE_USER_ID
    text = (
        "🎁 <b>Выдать подписку пользователю</b>\n\n"
        "Введите числовой Telegram ID пользователя:"
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_admin_give_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, tariff_id: str):
    query = update.callback_query
    tariff = TARIFFS.get(tariff_id)
    if not tariff:
        await query.edit_message_text("❌ Тариф не найден")
        return

    target_user_id = context.user_data.get("admin_give_target")
    if not target_user_id:
        await query.edit_message_text("❌ Ошибка: ID пользователя не найден. Начните заново.")
        return

    context.user_data["admin_give_tariff"] = tariff_id
    context.user_data["state"] = STATE_ADMIN_GIVE_DAYS

    text = (
        f"🎁 <b>Выдача подписки</b>\n\n"
        f"👤 Пользователь: <code>{target_user_id}</code>\n"
        f"📌 Тариф: {tariff['name']}\n\n"
        f"Введите количество дней (целое число):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_admin_simulate_referral(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    context.user_data["state"] = STATE_SIMULATE_REFERRAL_USERID
    text = (
        "🧪 <b>Симуляция реферала</b>\n\n"
        "Введите числовой Telegram ID <b>тестового пользователя</b>, "
        "который будет «приглашён» вами."
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_admin_find(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    context.user_data["state"] = STATE_FIND_USER
    text = (
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите ID пользователя:"
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str):
    query = update.callback_query
    target_id = int(target_id_str)
    context.user_data["state"] = STATE_BAN_REASON
    context.user_data["ban_target"] = target_id
    text = (
        f"🔨 <b>Бан пользователя {target_id}</b>\n\n"
        "Введите причину или 'навсегда':"
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str):
    query = update.callback_query
    target_id = int(target_id_str)
    db.unban_user(target_id)
    db.log_admin_action(user_id, "unban", target_id)
    text = f"✅ Пользователь <code>{target_id}</code> разбанен"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_makeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str):
    query = update.callback_query
    target_id = int(target_id_str)
    db.set_admin(target_id)
    db.log_admin_action(user_id, "make_admin", target_id)
    text = f"✅ Пользователь <code>{target_id}</code> стал админом"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str):
    query = update.callback_query
    target_id = int(target_id_str)
    db.remove_admin(target_id)
    db.log_admin_action(user_id, "remove_admin", target_id)
    text = f"✅ Админка у <code>{target_id}</code> снята"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
