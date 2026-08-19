"""Admin promo code handlers for Avava VPN Bot."""

import json
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import db
from keyboards import (
    build_admin_promos,
    build_promo_detail,
    build_promo_edit_menu,
    build_promo_list,
)
from utils import (
    STATE_PROMO_CODE,
    STATE_PROMO_DAYS,
    STATE_PROMO_DISCOUNT,
    STATE_PROMO_IDEMPOTENT,
    STATE_PROMO_MAX_ACTIVATIONS,
    STATE_PROMO_TARIFFS,
    STATE_PROMO_TEXT,
    STATE_PROMO_VALID_FROM,
    STATE_PROMO_VALID_UNTIL,
    back_btn,
)

logger = logging.getLogger(__name__)


async def handle_admin_promos(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    text, markup = build_admin_promos()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_promo_create_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    context.user_data["state"] = STATE_PROMO_CODE
    context.user_data["admin_promo_create"] = True
    text = (
        "🎁 <b>Создать промокод</b>\n\nВведите промокод (буквы и цифры, без пробелов):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_code(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_CODE or not context.user_data.get("admin_promo_create"):
        return

    code = update.message.text.strip().upper()
    context.user_data["state"] = STATE_PROMO_DISCOUNT
    context.user_data["promo_code"] = code

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{code}</code>\n\n"
        f"Введите процент скидки (0-100):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_discount(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_DISCOUNT or not context.user_data.get("admin_promo_create"):
        return

    try:
        discount = int(update.message.text.strip())
        if discount < 0 or discount > 100:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ Введите целое число от 0 до 100")
        return

    context.user_data["promo_discount"] = discount
    context.user_data["state"] = STATE_PROMO_DAYS

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {discount}%\n\n"
        f"Введите количество бесплатных дней (0 для пропуска):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_days(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_DAYS or not context.user_data.get("admin_promo_create"):
        return

    try:
        days = int(update.message.text.strip())
        if days < 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ Введите неотрицательное целое число")
        return

    context.user_data["promo_days"] = days
    context.user_data["state"] = STATE_PROMO_VALID_FROM

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {days}\n\n"
        f"Введите дату начала действия (YYYY-MM-DD):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_valid_from(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_VALID_FROM or not context.user_data.get("admin_promo_create"):
        return

    try:
        valid_from = datetime.strptime(update.message.text.strip(), "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        context.user_data["promo_valid_from"] = valid_from.isoformat()
    except ValueError:
        await update.message.reply_text("❌ Введите дату в формате YYYY-MM-DD")
        return

    context.user_data["state"] = STATE_PROMO_VALID_UNTIL

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {context.user_data.get('promo_days', 0)}\n"
        f"Дата начала: {context.user_data.get('promo_valid_from')}\n\n"
        f"Введите дату окончания действия (YYYY-MM-DD):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_valid_until(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_VALID_UNTIL or not context.user_data.get("admin_promo_create"):
        return

    try:
        valid_until = datetime.strptime(
            update.message.text.strip(), "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)
        context.user_data["promo_valid_until"] = valid_until.isoformat()
    except ValueError:
        await update.message.reply_text("❌ Введите дату в формате YYYY-MM-DD")
        return

    context.user_data["state"] = STATE_PROMO_MAX_ACTIVATIONS

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {context.user_data.get('promo_days', 0)}\n"
        f"Дата начала: {context.user_data.get('promo_valid_from')}\n"
        f"Дата окончания: {context.user_data.get('promo_valid_until')}\n\n"
        f"Введите максимальное количество активаций (целое число):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_max_activations(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_MAX_ACTIVATIONS or not context.user_data.get("admin_promo_create"):
        return

    try:
        max_activations = int(update.message.text.strip())
        if max_activations < 1:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ Введите целое число больше 0")
        return

    context.user_data["promo_max_activations"] = max_activations
    context.user_data["state"] = STATE_PROMO_TARIFFS

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {context.user_data.get('promo_days', 0)}\n"
        f"Максимум активаций: {max_activations}\n\n"
        f"Введите тарифы, для которых промокод действителен (через запятую, например: basic,premium, или 'all' для всех):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_tariffs(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_TARIFFS or not context.user_data.get("admin_promo_create"):
        return

    tariffs_input = update.message.text.strip().lower()

    if tariffs_input == "all":
        applicable_tariffs = None  # None means all tariffs
    else:
        tariffs_list = [t.strip() for t in tariffs_input.split(",") if t.strip()]
        # Validate tariff names
        valid_tariffs = ["trial", "basic", "premium"]
        for tariff in tariffs_list:
            if tariff not in valid_tariffs:
                await update.message.reply_text(f"❌ Неизвестный тариф: {tariff}")
                return
        applicable_tariffs = json.dumps(tariffs_list)

    context.user_data["promo_tariffs"] = applicable_tariffs
    context.user_data["state"] = STATE_PROMO_TEXT

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {context.user_data.get('promo_days', 0)}\n"
        f"Максимум активаций: {context.user_data.get('promo_max_activations', 1)}\n"
        f"Тарифы: {tariffs_input}\n\n"
        f"Введите текст активации (или оставьте пустым):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_TEXT or not context.user_data.get("admin_promo_create"):
        return

    activation_text = update.message.text.strip()
    if not activation_text:
        activation_text = None

    context.user_data["promo_text"] = activation_text
    context.user_data["state"] = STATE_PROMO_IDEMPOTENT

    text = (
        f"🎁 <b>Создание промокода</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {context.user_data.get('promo_days', 0)}\n"
        f"Максимум активаций: {context.user_data.get('promo_max_activations', 1)}\n"
        f"Тарифы: {context.user_data.get('promo_tariffs', 'all')}\n"
        f"Текст активации: {activation_text or 'не указан'}\n\n"
        f"Можно ли активировать несколько раз одним пользователем? (да/нет):"
    )
    keyboard = [[back_btn("admin_panel")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_create_idempotent(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    if context.user_data.get("state") != STATE_PROMO_IDEMPOTENT or not context.user_data.get("admin_promo_create"):
        return

    answer = update.message.text.strip().lower()

    if answer in ["да", "yes", "true", "1"]:
        is_idempotent = 1
    elif answer in ["нет", "no", "false", "0"]:
        is_idempotent = 0
    else:
        await update.message.reply_text("❌ Ответьте 'да' или 'нет'")
        return

    context.user_data["promo_idempotent"] = is_idempotent

    # Create the promo code
    promo_id = db.create_promo_code(
        code=context.user_data["promo_code"],
        discount_percent=context.user_data["promo_discount"],
        free_days=context.user_data["promo_days"],
        valid_from=context.user_data.get("promo_valid_from"),
        valid_until=context.user_data.get("promo_valid_until"),
        max_activations=context.user_data["promo_max_activations"],
        applicable_tariffs=context.user_data["promo_tariffs"],
        activation_text=context.user_data["promo_text"],
        is_idempotent=is_idempotent,
        is_active=1,
    )

    # Clear promo data from user_data
    for key in [
        "promo_code",
        "promo_discount",
        "promo_days",
        "promo_valid_from",
        "promo_valid_until",
        "promo_max_activations",
        "promo_tariffs",
        "promo_text",
        "promo_idempotent",
        "admin_promo_create",
    ]:
        context.user_data.pop(key, None)

    context.user_data["state"] = None

    await update.message.reply_text(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"Код: <code>{context.user_data.get('promo_code', 'N/A')}</code>\n"
        f"Скидка: {context.user_data.get('promo_discount', 0)}%\n"
        f"Бесплатные дни: {context.user_data.get('promo_days', 0)}\n"
        f"Максимум активаций: {context.user_data.get('promo_max_activations', 1)}\n"
        f"Тарифы: {context.user_data.get('promo_tariffs', 'all')}\n"
        f"Идемпотентность: {'Да' if is_idempotent else 'Нет'}\n"
        f"ID: {promo_id}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[back_btn("admin_panel")]]),
    )


async def handle_admin_promo_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, promo_id: str
):
    """Show promo code detail."""
    query = update.callback_query
    promo = db.get_promo_code_by_id(int(promo_id))
    text, markup = build_promo_detail(promo)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_promo_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, promo_id: str
):
    """Show promo edit menu."""
    query = update.callback_query
    promo = db.get_promo_code_by_id(int(promo_id))
    text, markup = build_promo_edit_menu(promo)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_promo_delete(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, promo_id: str
):
    """Delete promo code."""
    query = update.callback_query
    success = db.delete_promo_code(int(promo_id))
    if success:
        await query.edit_message_text(
            "✅ Промокод удален",
            reply_markup=InlineKeyboardMarkup([[back_btn("admin_promos")]]),
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка удаления",
            reply_markup=InlineKeyboardMarkup([[back_btn("admin_promos")]]),
        )


async def handle_admin_promo_activations(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, promo_id: str
):
    """Show promo activations."""
    query = update.callback_query
    activations = db.get_promo_activations(int(promo_id))

    if not activations:
        text = "📋 Активаций нет"
    else:
        text = "📋 <b>Активации промокода</b>\n\n"
        for act in activations[:20]:
            user = db.get_user_by_id(act["user_id"])
            username = (
                f"@{user['username']}"
                if user and user.get("username")
                else f"ID: {act['user_id']}"
            )
            text += f"👤 {username} — {act['activated_at']}\n"

    keyboard = [[back_btn(f"admin_promo_detail_{promo_id}")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_toggle_active(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, promo_id: str
):
    """Toggle promo code active status."""
    query = update.callback_query
    promo = db.get_promo_code_by_id(int(promo_id))
    new_status = 0 if promo.get("is_active", 1) else 1
    db.update_promo_code(int(promo_id), is_active=new_status)

    promo = db.get_promo_code_by_id(int(promo_id))
    text, markup = build_promo_detail(promo)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_promos_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Show list of all promo codes."""
    query = update.callback_query
    promos = db.get_all_promo_codes()
    text, markup = build_promo_list(promos)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_promo_find(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Prompt admin to enter promo code to find."""
    query = update.callback_query
    context.user_data["state"] = STATE_PROMO_CODE
    context.user_data["admin_promo_find"] = True
    text = (
        "🔍 <b>Найти промокод</b>\n\n"
        "Введите код промокода для поиска:"
    )
    keyboard = [[back_btn("admin_promos")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_promo_stats(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Show promo codes statistics."""
    query = update.callback_query
    promos = db.get_all_promo_codes()
    total_promos = len(promos)
    active_promos = sum(1 for p in promos if p.get("is_active", 1))
    total_activations = sum(p.get("current_activations", 0) for p in promos)

    text = (
        "📊 <b>Статистика промокодов</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Всего промокодов: <b>{total_promos}</b>\n"
        f"🟢 Активных: <b>{active_promos}</b>\n"
        f"🔴 Неактивных: <b>{total_promos - active_promos}</b>\n"
        f"🔢 Всего активаций: <b>{total_activations}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [[back_btn("admin_promos")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )
