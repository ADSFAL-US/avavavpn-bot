# Avava VPN Bot - Main Bot File
import logging
import os
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
from database import db, TARIFFS


# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def is_admin(user_id):
    """Check if user is admin."""
    return db.is_admin(int(user_id)) or int(user_id) in config.ADMIN_IDS


# ==================== USER COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name or "",
        "username": user.username or "",
        "last_name": user.last_name or "",
    }

    # Create/get user
    user_info = db.get_or_create_user(user_data)

    # Check if banned
    if user_info["banned"]:
        await update.message.reply_text(
            "🚫 Вы забанены!\n"
            f"Причина: {user_info['ban_reason'] or 'Не указана'}\n\n"
            "Обратитесь в поддержку."
        )
        return

    # Welcome message
    keyboard = [
        [KeyboardButton("/tariffs"), KeyboardButton("/my_subscription")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🟢 <b>Добро пожаловать в Avava VPN Bot!</b>\n\n"
        "Я помогу вам выбрать тариф и управлять подпиской.\n\n"
        "<b>Возможные команды:</b>\n"
        "• /tariffs - список тарифов\n"
        "• /my_subscription - моя подписка\n"
        "• /speed_upgrade - увеличить скорость\n"
        "• /support - поддержка\n" +
        ("• /admin - админ панель" if is_admin(user.id) else ""),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def tariffs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available tariffs."""
    keyboard = []

    for tariff_id, tariff in TARIFFS.items():
        price_text = f"{tariff['price']} {tariff['currency']}" if tariff["price"] > 0 else "Бесплатно"
        keyboard.append([
            InlineKeyboardButton(
                f"{tariff['name']} - {price_text}",
                callback_data=f"tariff_{tariff_id}",
            )
        ])

    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📋 <b>Доступные тарифы Avava VPN:</b>\n\n"
        "Выберите интересующий вас тариф:",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def tariff_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tariff detail and subscribe."""
    query = update.callback_query
    await query.answer()

    tariff_id = query.data.replace("tariff_", "", 1)
    tariff = TARIFFS.get(tariff_id)

    if not tariff:
        await query.edit_message_text("❌ Тариф не найден.")
        return

    user_id = query.from_user.id
    active_sub = db.get_active_subscription(user_id)

    price_text = f"💰 <b>Стоимость:</b> {tariff['price']} {tariff['currency']}" if tariff["price"] > 0 else "💰 <b>Стоимость:</b> Бесплатно"
    
    speed_text = f"⚡ <b>Скорость:</b> {tariff['speed']}\n"

    traffic_text = ""
    if tariff["traffic_limit_gb"]:
        traffic_text = f"📊 <b>Трафик:</b> до {tariff['traffic_limit_gb']} ГБ\n"
    else:
        traffic_text = "📊 <b>Трафик:</b> без ограничений\n"

    duration_text = f"⏱ <b>Срок доступа:</b> {tariff['duration_days']} дней\n\n"

    perks = []
    if tariff["warp"]:
        perks.append("✅ Warp")
    else:
        perks.append("❌ Warp")
    
    if tariff["whitelist"]:
        perks.append("✅ Whitelist")
    else:
        perks.append("❌ Whitelist")

    if tariff["priority_support"]:
        perks.append("⭐ Приоритетная поддержка")
    
    perks_text = "\n".join(perks)

    current_status = ""
    if active_sub:
        sub_tariff = TARIFFS.get(active_sub["tariff_id"], {})
        current_status = (
            f"\n📌 <b>Текущая подписка:</b> {sub_tariff['name']}\n"
            f"⏱ Заканчивается: {active_sub['ends_at'][:16].replace('T', ' ')}\n\n"
        )

    text = (
        f"{tariff['description']}\n\n"
        f"{price_text}\n"
        f"{speed_text}"
        f"{traffic_text}"
        f"{duration_text}"
        f"<b>Привилегии:</b>\n{perks_text}"
        f"{current_status}"
    )

    keyboard = []

    if tariff["price"] > 0:
        keyboard.append([
            InlineKeyboardButton("💳 Подключить (без платёжки)", callback_data=f"subscribe_{tariff_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("📈 Увеличить скорость", callback_data=f"speed_config_{tariff_id}"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Подключить бесплатно", callback_data=f"subscribe_{tariff_id}"),
        ])

    keyboard.append([InlineKeyboardButton("🔙 К списку тарифов", callback_data="show_tariffs")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to a tariff."""
    query = update.callback_query
    await query.answer()

    tariff_id = query.data.replace("subscribe_", "", 1)
    tariff = TARIFFS.get(tariff_id)

    if not tariff:
        await query.edit_message_text("❌ Тариф не найден.")
        return

    user_id = query.from_user.id

    # Cancel existing active subscription if any
    active_sub = db.get_active_subscription(user_id)
    if active_sub:
        db.cancel_subscription(active_sub["id"], user_id)

    try:
        result = db.create_subscription(user_id, tariff_id)
        
        await query.edit_message_text(
            f"✅ <b>Подписка активирована!</b>\n\n"
            f"Тариф: {tariff['name']}\n"
            f"Скорость: {tariff['speed']}\n"
            f"Трафик: {'без ограничений' if not tariff['traffic_limit_gb'] else 'до ' + str(tariff['traffic_limit_gb']) + ' ГБ'}\n"
            f"Срок: {tariff['duration_days']} дней\n\n"
            "Ваша подписка активна. Приятного использования Avava VPN!",
            parse_mode="HTML",
        )

    except Exception as e:
        await query.edit_message_text(
            f"❌ Ошибка при подключении тарифа: {str(e)}",
        )


async def speed_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Speed configuration page for tariffs with upgrade options."""
    query = update.callback_query
    await query.answer()

    tariff_id = query.data.replace("speed_config_", "", 1)
    tariff = TARIFFS.get(tariff_id)

    if not tariff or not tariff.get("speed_upgrade"):
        await query.edit_message_text("❌ Этот тариф не поддерживает повышение скорости.")
        return

    upgrade = tariff["speed_upgrade"]
    base_speed = upgrade["base"]
    max_speed = upgrade["max_mbps"]

    text = (
        f"⚡ <b>Настройка скорости: {tariff['name']}</b>\n\n"
        f"Базовая скорость: {base_speed} Мбит/с\n"
        f"Максимальная скорость: {max_speed} Мбит/с\n\n"
    )

    if upgrade.get("per_rub_mbps"):
        text += (
            f"Доплата: +1 Мбит/с за 1 рубль\n"
            f"\n<b>Примеры:</b>\n"
            f"• 30 Мбит/с = +10 Мбит → 10 руб\n"
            f"• 50 Мбит/с = +30 Мбит → 30 руб\n"
            f"• {max_speed} Мбит/с = +{max_speed - base_speed} Мбит → {max_speed - base_speed} руб\n"
        )
    elif upgrade.get("per_kop_mbps"):
        kop_per_mbit = upgrade["per_kop_mbps"]
        text += (
            f"Доплата: +1 Мбит/с за {kop_per_mbit / 100:.2f} руб ({kop_per_mbit} коп.)\n"
            f"\n<b>Примеры:</b>\n"
            f"• 60 Мбит/с = +10 Мбит → {10 * kop_per_mbit / 100:.2f} руб\n"
            f"• 80 Мбит/с = +30 Мбит → {30 * kop_per_mbit / 100:.2f} руб\n"
            f"• {max_speed} Мбит/с = +{max_speed - base_speed} Мбит → {(max_speed - base_speed) * kop_per_mbit / 100:.2f} руб\n"
        )

    keyboard = [
        InlineKeyboardButton("🔙 К тарифу", callback_data=f"tariff_{tariff_id}"),
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def my_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's current subscription."""
    user_id = update.effective_user.id

    active_sub = db.get_active_subscription(user_id)

    if not active_sub:
        await update.message.reply_text(
            "📭 У вас нет активной подписки.\n\n"
            "Используйте /tariffs чтобы выбрать тариф.",
        )
        return

    tariff = TARIFFS.get(active_sub["tariff_id"], {})

    traffic_info = ""
    if active_sub["traffic_limit_mb"]:
        used_mb = active_sub["traffic_used_mb"] or 0
        limit_mb = active_sub["traffic_limit_mb"]
        used_gb = used_mb / 1024
        limit_gb = limit_mb / 1024
        remaining = max(0, limit_mb - used_mb) / 1024
        traffic_info = (
            f"\n📊 <b>Использованный трафик:</b>\n"
            f"   Использовано: {used_gb:.2f} ГБ\n"
            f"   Лимит: {limit_gb:.1f} ГБ\n"
            f"   Осталось: {remaining:.2f} ГБ"
        )

    text = (
        f"📌 <b>Ваша текущая подписка:</b>\n\n"
        f"<b>Тариф:</b> {tariff.get('name', 'Неизвестно')}\n"
        f"<b>Скорость:</b> {active_sub['speed_mbps'] or tariff.get('speed', 'N/A')} Мбит/с\n"
        f"<b>Warp:</b> {'✅' if active_sub['warp_enabled'] else '❌'}\n"
        f"<b>Whitelist:</b> {'✅' if active_sub['whitelist_enabled'] else '❌'}\n"
        f"<b>Приоритетная поддержка:</b> {'✅' if active_sub['priority_support'] else '❌'}\n"
        f"<b>Начало:</b> {active_sub['started_at'][:16].replace('T', ' ') if active_sub.get('started_at') else 'N/A'}\n"
        f"<b>Окончание:</b> {active_sub['ends_at'][:16].replace('T', ' ') if active_sub.get('ends_at') else 'N/A'}"
        + traffic_info
    )

    keyboard = [
        [InlineKeyboardButton("📋 Другие тарифы", callback_data="show_tariffs")],
        [InlineKeyboardButton("⚡ Увеличить скорость", callback_data=f"speed_config_{active_sub['tariff_id']}")],
        [InlineKeyboardButton("❌ Отменить подписку", callback_data=f"cancel_{active_sub['id']}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel subscription."""
    query = update.callback_query
    await query.answer()

    sub_id = int(query.data.replace("cancel_", "").replace("cancel_sub_", ""))
    
    # Handle both formats - with and without user check (for admin)
    if context.args:
        user_id = int(context.args[0])
    else:
        user_id = query.from_user.id

    success = db.cancel_subscription(sub_id, user_id)

    if success:
        await query.edit_message_text("✅ Подписка отменена.")
    else:
        await query.edit_message_text("❌ Не удалось отменить подписку. Возможно, она уже отменена или не найдена.")


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Support command."""
    await update.message.reply_text(
        "🛠 <b>Поддержка Avava VPN</b>\n\n"
        "Если у вас возникли проблемы:\n"
        "• Опишите вашу проблему\n"
        "• Укажите ваш тариф\n"
        "• Приложите скриншот (если есть)\n\n"
        "Мы ответим в кратчайшие сроки!",
        parse_mode="HTML",
    )


# ==================== ADMIN COMMANDS ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет доступа к панели администратора.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📋 Подписки", callback_data="admin_subscriptions")],
        [InlineKeyboardButton("🔍 Найти пользователя", callback_data="admin_find_user")],
        [InlineKeyboardButton("📝 Логи", callback_data="admin_logs")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin statistics."""
    query = update.callback_query
    await query.answer()

    total_users = db.get_user_count()
    active_subs = db.get_active_subscription_count()
    stats = db.get_subscription_stats()

    text = "📊 <b>Статистика</b>\n\n"
    text += f"👥 Всего пользователей: {total_users}\n"
    text += f"🟢 Активных подписок: {active_subs}\n\n"
    text += "<b>По тарифам:</b>\n"

    for tariff_id, stat in stats.items():
        icon = {"youtube": "📺", "basic": "🛡️", "premium": "💎", "extreme": "🔥", "power": "⚡"}.get(
            tariff_id, "❓"
        )
        text += f"\n{icon} <b>{stat['name']}</b>\n   Активных: {stat['active_count']}\n"

    text += "\n🔙 Используйте кнопки для навигации."

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user list."""
    query = update.callback_query
    await query.answer()

    users = db.get_all_users(limit=20)

    if not users:
        await query.edit_message_text("👥 Пользователей пока нет.")
        return

    text = "👥 <b>Последние зарегистрированные пользователи:</b>\n\n"

    for user in users[:15]:
        name = user["first_name"] or f"ID:{user['user_id']}"
        username = f"@{user['username']}" if user.get("username") else "нет username"
        status = "🔴 забанен" if user["banned"] else "🟢 активен"
        
        text += f"• {name}\n  @{username} | статус: {status}\n\n"

    text += "🔙 Используйте кнопки для навигации."

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def admin_find_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Find user by ID."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 <b>Введите ID пользователя:</b>\n\n"
        "Отправьте ID пользователя для просмотра информации.",
        parse_mode="HTML",
    )

    # Store state for next message handler
    context.user_data["find_user_state"] = True


async def admin_find_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ID input for find user."""
    if not context.user_data.get("find_user_state"):
        return

    user_id_str = update.message.text.strip()
    
    try:
        user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID. Отправьте числовой ID.")
        return

    user = db.get_user_by_id(user_id)

    if not user:
        await update.message.reply_text(f"❌ Пользователь с ID {user_id} не найден.")
        context.user_data["find_user_state"] = False
        return

    active_sub = db.get_active_subscription(user_id)
    tariff_name = "Нет активной подписки"
    if active_sub:
        t = TARIFFS.get(active_sub["tariff_id"], {})
        tariff_name = t.get("name", "Неизвестно")

    text = (
        f"👤 <b>Информация о пользователе:</b>\n\n"
        f"<b>ID:</b> {user['user_id']}\n"
        f"<b>Имя:</b> {user['first_name'] or 'N/A'}\n"
        f"<b>Username:</b> @{user.get('username') or 'N/A'}\n"
        f"<b>Последнее имя:</b> {user.get('last_name', '')}\n"
        f"<b>Админ:</b> {'✅ Да' if user['is_admin'] else '❌ Нет'}\n"
        f"<b>Статус:</b> {'🔴 Забанен' if user['banned'] else '🟢 Активен'}\n"
        f"<b>Зарегистрирован:</b> {user.get('registered_at', 'N/A')[:16]}\n\n"
        f"<b>Подписка:</b> {tariff_name}\n"
    )

    keyboard = [
        [InlineKeyboardButton("🔨 Забанить", callback_data=f"ban_{user_id}")],
        [InlineKeyboardButton("🔓 Разбанить", callback_data=f"unban_{user_id}")],
        [InlineKeyboardButton("➕ Сделать админом", callback_data=f"makeadmin_{user_id}")],
        [InlineKeyboardButton("➖ Убрать админку", callback_data=f"removeadmin_{user_id}")],
        [InlineKeyboardButton("📧 Написать пользователю", url=f"https://t.me/{user.get('username') or ''}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

    context.user_data["find_user_state"] = False


async def admin_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription management."""
    query = update.callback_query
    await query.answer()

    text = "📋 <b>Управление подписками</b>\n\n"
    text += "Выберите тариф для управления:\n\n"

    keyboard = []
    for tariff_id, tariff in TARIFFS.items():
        count = 0
        try:
            stats = db.get_subscription_stats()
            count = stats.get(tariff_id, {}).get("active_count", 0)
        except:
            pass
        
        text += f"• {tariff['name']}: {count} активных\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin logs."""
    query = update.callback_query
    await query.answer()

    logs = db.get_admin_logs(limit=30)

    if not logs:
        await query.edit_message_text("📝 Логов действий администраторов пока нет.")
        return

    text = "📝 <b>Последние действия администраторов:</b>\n\n"

    for log in logs[:25]:
        admin_name = log.get('admin_first_name') or f"ID:{log['admin_id']}"
        target = log.get('target_user_id', 'N/A')
        
        text += f"• {admin_name}\n"
        text += f"  Действие: {log['action']}\n"
        if log.get('details'):
            text += f"  Детали: {log['details'][:50]}\n"
        text += f"  Время: {log['created_at'][:16].replace('T', ' ') if log.get('created_at') else 'N/A'}\n\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


# ==================== ADMIN ACTIONS ====================

async def ban_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban user action."""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.replace("ban_", "").replace("_reason", ""))
    
    # Wait for reason
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔨 <b>Забанить пользователя {user_id}?</b>\n\n"
        "Введите причину бана (или 'навсегда'):\n\n"
        "⚠️ Пользователь не сможет использовать бота.",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )

    context.user_data["ban_state"] = {"user_id": user_id}


async def ban_user_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ban reason input."""
    if not context.user_data.get("ban_state"):
        return

    state = context.user_data.pop("ban_state")
    user_id = state["user_id"]
    reason = update.message.text.strip()

    db.ban_user(user_id, reason=reason)
    db.log_admin_action(update.effective_user.id, "ban", user_id, reason)

    await update.message.reply_text(
        f"✅ Пользователь {user_id} забанен.\nПричина: {reason}"
    )


async def unban_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban user action."""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.replace("unban_", ""))

    db.unban_user(user_id)
    db.log_admin_action(update.effective_user.id, "unban", user_id)

    await query.edit_message_text(f"✅ Пользователь {user_id} разбанен.")


async def make_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Make user admin action."""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.replace("makeadmin_", ""))

    db.set_admin(user_id)
    db.log_admin_action(update.effective_user.id, "make_admin", user_id)

    await query.edit_message_text(f"✅ Пользователь {user_id} теперь администратор.")


async def remove_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove admin action."""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.replace("removeadmin_", ""))

    db.remove_admin(user_id)
    db.log_admin_action(update.effective_user.id, "remove_admin", user_id)

    await query.edit_message_text(f"✅ Администратор {user_id} снят с должности.")


# ==================== CALLBACK HANDLERS ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard buttons."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "back_menu":
        keyboard = [
            [KeyboardButton("/tariffs"), KeyboardButton("/my_subscription")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.edit_message_text(
            "🔙 Главное меню:",
            reply_markup=reply_markup,
        )

    elif data == "show_tariffs":
        await tariffs(update, context)

    elif data.startswith("admin_panel"):
        await admin_panel(update, context)

    elif data.startswith("admin_stats") or data == "statistics":
        await admin_stats(update, context)

    elif data.startswith("admin_users") or data == "user_list":
        await admin_users(update, context)

    elif data.startswith("admin_subscriptions") or data == "subscriptions_mgmt":
        await admin_subscriptions(update, context)

    elif data.startswith("admin_logs") or data == "logs":
        await admin_logs(update, context)


# ==================== MAIN ====================

def main():
    """Start the bot."""
    # Get application
    app = Application.builder().token(config.BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tariffs", tariffs))
    app.add_handler(CommandHandler("my_subscription", my_subscription))
    app.add_handler(CommandHandler("speed_upgrade", lambda u, c: u.message.reply_text(
        "Используйте /my_subscription для управления скоростью."
    )))
    app.add_handler(CommandHandler("support", support))

    # Admin commands (only for admins)
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", lambda u, c: admin_stats(u, c) if is_admin(u.effective_user.id) else u.message.reply_text("Используйте /admin")))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(button_handler, pattern=r"^(back_menu|show_tariffs)$"))
    app.add_handler(CallbackQueryHandler(tariff_detail, pattern=r"^tariff_"))
    app.add_handler(CallbackQueryHandler(subscribe, pattern=r"^subscribe_"))
    app.add_handler(CallbackQueryHandler(speed_config, pattern=r"^speed_config_"))
    
    # Admin callbacks
    app.add_handler(CallbackQueryHandler(admin_stats, pattern=r"^(admin_)?stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern=r"^(admin_)?users$"))
    app.add_handler(CallbackQueryHandler(admin_subscriptions, pattern=r"^(admin_)?subscriptions$"))
    app.add_handler(CallbackQueryHandler(admin_logs, pattern=r"^(admin_)?logs$"))

    # Cancel subscription callback
    app.add_handler(CallbackQueryHandler(cancel_subscription, pattern=r"^cancel_"))

    # Admin action callbacks
    app.add_handler(CallbackQueryHandler(ban_user_action, pattern=r"^ban_\d+$"))
    app.add_handler(CallbackQueryHandler(unban_user_action, pattern=r"^unban_\d+$"))
    app.add_handler(CallbackQueryHandler(make_admin_action, pattern=r"^makeadmin_\d+$"))
    app.add_handler(CallbackQueryHandler(remove_admin_action, pattern=r"^removeadmin_\d+$"))

    # Find user flow
    app.add_handler(CallbackQueryHandler(admin_find_user, pattern=r"^admin_find_user$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_find_user_handler))

    # Ban reason flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_reason))

    # Log all errors
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error("Exception while handling an update:", exc_info=context.error)

    app.add_error_handler(error_handler)

    logger.info("🚀 Avava VPN Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()