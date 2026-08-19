# handlers/admin.py — Admin panel, user management, bans, give subscription, referral simulation
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import TARIFFS, db
from keyboards import (
    build_admin_logs,
    build_admin_panel,
    build_admin_promos,
    build_admin_stats,
    build_admin_subscriptions,
    build_admin_users,
)
from utils import (
    STATE_ADMIN_GIVE_DAYS,
    STATE_ADMIN_GIVE_USER_ID,
    STATE_BAN_REASON,
    STATE_FIND_USER,
    STATE_PROMO_CODE,
    STATE_PROMO_DAYS,
    STATE_PROMO_DISCOUNT,
    STATE_PROMO_IDEMPOTENT,
    STATE_PROMO_MAX_ACTIVATIONS,
    STATE_PROMO_TARIFFS,
    STATE_PROMO_TEXT,
    STATE_PROMO_VALID_FROM,
    STATE_PROMO_VALID_UNTIL,
    STATE_SIMULATE_REFERRAL_USERID,
    back_btn,
)

logger = logging.getLogger(__name__)


async def handle_admin_panel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    text, markup = build_admin_panel(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_stats(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    text, markup = build_admin_stats()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_users(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    text, markup = build_admin_users()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_subscriptions(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    text, markup = build_admin_subscriptions()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_logs(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    text, markup = build_admin_logs()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_admin_give_subscription(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    context.user_data["state"] = STATE_ADMIN_GIVE_USER_ID
    text = (
        "🎁 <b>Выдать подписку пользователю</b>\n\n"
        "Введите числовой Telegram ID пользователя:"
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_give_tariff(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, tariff_id: str
):
    query = update.callback_query
    tariff = TARIFFS.get(tariff_id)
    if not tariff:
        await query.edit_message_text("❌ Тариф не найден")
        return

    target_user_id = context.user_data.get("admin_give_target")
    if not target_user_id:
        await query.edit_message_text(
            "❌ Ошибка: ID пользователя не найден. Начните заново."
        )
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
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_simulate_referral(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    context.user_data["state"] = STATE_SIMULATE_REFERRAL_USERID
    text = (
        "🧪 <b>Симуляция реферала</b>\n\n"
        "Введите числовой Telegram ID <b>тестового пользователя</b>, "
        "который будет «приглашён» вами."
    )
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_find(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    query = update.callback_query
    context.user_data["state"] = STATE_FIND_USER
    text = "🔍 <b>Поиск пользователя</b>\n\nВведите ID пользователя:"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_ban(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str
):
    query = update.callback_query
    target_id = int(target_id_str)
    context.user_data["state"] = STATE_BAN_REASON
    context.user_data["ban_target"] = target_id
    text = f"🔨 <b>Бан пользователя {target_id}</b>\n\nВведите причину или 'навсегда':"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_unban(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str
):
    query = update.callback_query
    target_id = int(target_id_str)
    db.unban_user(target_id)
    db.log_admin_action(user_id, "unban", target_id)
    text = f"✅ Пользователь <code>{target_id}</code> разбанен"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_makeadmin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str
):
    query = update.callback_query
    target_id = int(target_id_str)
    db.set_admin(target_id)
    db.log_admin_action(user_id, "make_admin", target_id)
    text = f"✅ Пользователь <code>{target_id}</code> стал админом"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_removeadmin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_id_str: str
):
    query = update.callback_query
    target_id = int(target_id_str)
    db.remove_admin(target_id)
    db.log_admin_action(user_id, "remove_admin", target_id)
    text = f"✅ Админка у <code>{target_id}</code> снята"
    keyboard = [[back_btn("admin_panel")]]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


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
    if context.user_data.get("state") != STATE_PROMO_CODE:
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
    if context.user_data.get("state") != STATE_PROMO_DISCOUNT:
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
    if context.user_data.get("state") != STATE_PROMO_DAYS:
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
    if context.user_data.get("state") != STATE_PROMO_VALID_FROM:
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
    if context.user_data.get("state") != STATE_PROMO_VALID_UNTIL:
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
    if context.user_data.get("state") != STATE_PROMO_MAX_ACTIVATIONS:
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
    if context.user_data.get("state") != STATE_PROMO_TARIFFS:
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
        import json

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
    if context.user_data.get("state") != STATE_PROMO_TEXT:
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
    if context.user_data.get("state") != STATE_PROMO_IDEMPOTENT:
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
