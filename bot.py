# Avava VPN Bot - Redesigned UI (Single Message Interface)
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

# ===== STATE MANAGEMENT =====
STATE_IDLE = "idle"
STATE_FIND_USER = "find_user"
STATE_BAN_REASON = "ban_reason"

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

# ===== UI HELPERS =====
def btn(text: str, callback: str) -> InlineKeyboardButton:
    """Create inline button."""
    return InlineKeyboardButton(text, callback_data=callback)

def back_btn(to: str = "main_menu") -> InlineKeyboardButton:
    """Create back button."""
    return InlineKeyboardButton("🔙 Назад", callback_data=to)

# ===== MAIN MENU =====
def build_main_menu(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build main menu with active subscription info."""
    active_sub = db.get_active_subscription(user_id)
    
    if active_sub:
        tariff = TARIFFS.get(active_sub["tariff_id"], {})
        sub_info = f"📌 <b>{tariff.get('name', 'Неизвестно')}</b>"
        speed = f"⚡ {active_sub.get('speed_mbps', 0)} Мбит/с"
        expires = safe_date_format(active_sub.get('ends_at'))
        status_line = f"{sub_info} │ {speed}\n⏱ До: {expires}"
    else:
        status_line = "📭 Нет активной подписки"
    
    text = (
        "🟢 <b>Avava VPN Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [
        [btn("📋 Тарифы", "menu_tariffs"), btn("📊 Моя подписка", "menu_subscription")],
    ]
    
    if active_sub:
        tariff = TARIFFS.get(active_sub["tariff_id"], {})
        if tariff.get("speed_upgrade"):
            keyboard.append([btn("⚡ Увеличить скорость", "menu_speed")])
        keyboard.append([btn("❌ Отменить подписку", f"confirm_cancel_{active_sub['id']}")])
    
    keyboard.append([btn("🛠 Поддержка", "menu_support")])
    
    if is_admin(user_id):
        keyboard.append([btn("👑 Админ-панель", "admin_panel")])
    
    return text, InlineKeyboardMarkup(keyboard)

# ===== TARIFFS MENU =====
def build_tariffs_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Build tariffs list menu."""
    text = "📋 <b>Выберите тариф:</b>\n"
    keyboard = []
    
    for tid, tariff in TARIFFS.items():
        price = "Бесплатно" if tariff["price"] == 0 else f"{tariff['price']}₽"
        keyboard.append([btn(f"{tariff['name']} — {price}", f"tariff_{tid}")])
    
    keyboard.append([back_btn()])
    return text, InlineKeyboardMarkup(keyboard)

def build_tariff_detail(tariff_id: str, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build tariff detail view."""
    tariff = TARIFFS.get(tariff_id)
    if not tariff:
        return "❌ Тариф не найден", InlineKeyboardMarkup([[back_btn("menu_tariffs")]])
    
    active_sub = db.get_active_subscription(user_id)
    
    # Price
    price = "<b>Бесплатно</b>" if tariff["price"] == 0 else f"<b>{tariff['price']} {tariff['currency']}</b>"
    
    # Features
    features = []
    features.append(f"⚡ <b>Скорость:</b> {tariff['speed']}")
    if tariff["traffic_limit_gb"]:
        features.append(f"📊 <b>Трафик:</b> до {tariff['traffic_limit_gb']} ГБ")
    else:
        features.append("📊 <b>Трафик:</b> без ограничений")
    features.append(f"⏱ <b>Срок:</b> {tariff['duration_days']} дней")
    
    # Perks with colors
    perks = []
    perks.append("✅ Warp" if tariff["warp"] else "❌ Warp")
    perks.append("✅ Whitelist" if tariff["whitelist"] else "❌ Whitelist")
    if tariff["priority_support"]:
        perks.append("⭐ Приоритетная поддержка")
    
    # Current subscription note
    current = ""
    if active_sub and active_sub["tariff_id"] == tariff_id:
        current = "\n🟢 <i>Это ваша текущая подписка</i>\n"
    elif active_sub:
        t = TARIFFS.get(active_sub["tariff_id"], {})
        current = f"\n📌 <i>У вас: {t.get('name', '—')}</i>\n"
    
    text = (
        f"<b>{tariff['name']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 {price}\n"
        + "\n".join(features) + "\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Включено:</b>\n" + "\n".join(perks)
        + current
    )
    
    # Buttons
    keyboard = []
    if tariff["price"] == 0:
        keyboard.append([btn("✅ Активировать бесплатно", f"subscribe_{tariff_id}")])
    else:
        keyboard.append([btn("💳 Выбрать тариф", f"subscribe_{tariff_id}")])
    
    if tariff.get("speed_upgrade"):
        keyboard.append([btn("📈 Рассчитать скорость", f"speed_calc_{tariff_id}")])
    
    keyboard.append([btn("🔙 К списку тарифов", "menu_tariffs")])
    
    return text, InlineKeyboardMarkup(keyboard)

# ===== SUBSCRIPTION VIEW =====
def build_subscription_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build subscription info view."""
    active_sub = db.get_active_subscription(user_id)
    
    if not active_sub:
        text = (
            "📭 <b>Нет активной подписки</b>\n\n"
            "Выберите тариф, чтобы начать пользоваться VPN."
        )
        keyboard = [[btn("📋 Смотреть тарифы", "menu_tariffs")], [back_btn()]]
        return text, InlineKeyboardMarkup(keyboard)
    
    tariff = TARIFFS.get(active_sub["tariff_id"], {})
    
    # Traffic info
    traffic = ""
    if active_sub.get("traffic_limit_mb"):
        used = (active_sub.get("traffic_used_mb") or 0) / 1024
        limit = active_sub["traffic_limit_mb"] / 1024
        remaining = max(0, limit - used)
        percent = min(100, int((used / limit) * 100)) if limit > 0 else 0
        
        # Progress bar
        bar_fill = int(percent / 10)
        bar = "█" * bar_fill + "░" * (10 - bar_fill)
        
        traffic = (
            f"\n📊 <b>Трафик:</b>\n"
            f"<code>[{bar}] {percent}%</code>\n"
            f"Использовано: <b>{used:.2f}</b> / {limit:.1f} ГБ\n"
            f"Осталось: <b>{remaining:.2f}</b> ГБ\n"
        )
    else:
        traffic = "\n📊 <b>Трафик:</b> без ограничений\n"
    
    text = (
        f"📌 <b>{tariff.get('name', 'Подписка')}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Скорость:</b> {active_sub.get('speed_mbps', 0)} Мбит/с\n"
        f"🔰 <b>Warp:</b> {'✅ Вкл' if active_sub.get('warp_enabled') else '❌ Выкл'}\n"
        f"📝 <b>Whitelist:</b> {'✅ Вкл' if active_sub.get('whitelist_enabled') else '❌ Выкл'}\n"
        f"⭐ <b>Поддержка:</b> {'Приоритет' if active_sub.get('priority_support') else 'Стандарт'}\n"
        f"⏱ <b>До:</b> {safe_date_format(active_sub.get('ends_at'))}"
        + traffic
    )
    
    keyboard = [[btn("📋 Другие тарифы", "menu_tariffs")]]
    
    if tariff.get("speed_upgrade"):
        keyboard.append([btn("⚡ Увеличить скорость", f"speed_calc_{active_sub['tariff_id']}")])
    
    keyboard.append([btn("❌ Отменить подписку", f"confirm_cancel_{active_sub['id']}")])
    keyboard.append([back_btn()])
    
    return text, InlineKeyboardMarkup(keyboard)

# ===== SPEED CALCULATOR =====
def build_speed_calc(tariff_id: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build speed upgrade calculator."""
    tariff = TARIFFS.get(tariff_id)
    if not tariff or not tariff.get("speed_upgrade"):
        return "❌ Нет опций апгрейда", InlineKeyboardMarkup([[back_btn(f"tariff_{tariff_id}")]])
    
    up = tariff["speed_upgrade"]
    base = up["base"]
    max_spd = up["max_mbps"]
    
    text = (
        f"⚡ <b>Расчет скорости: {tariff['name']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Базовая: <b>{base}</b> Мбит/с\n"
        f"Максимальная: <b>{max_spd}</b> Мбит/с\n\n"
    )
    
    if up.get("per_rub_mbps"):
        text += "💰 +1 Мбит/с = <b>1 ₽</b>\n\n"
        text += "<b>Примеры:</b>\n"
        text += f"• {base + 10} Мбит/с → +<b>10 ₽</b>\n"
        text += f"• {base + 30} Мбит/с → +<b>30 ₽</b>\n"
        text += f"• {max_spd} Мбит/с → +<b>{max_spd - base} ₽</b>\n"
    elif up.get("per_kop_mbps"):
        price = up["per_kop_mbps"] / 100
        text += f"💰 +1 Мбит/с = <b>{price:.2f} ₽</b>\n\n"
        text += "<b>Примеры:</b>\n"
        text += f"• 60 Мбит/с → +<b>{10 * price:.0f} ₽</b>\n"
        text += f"• 80 Мбит/с → +<b>{30 * price:.0f} ₽</b>\n"
        text += f"• {max_spd} Мбит/с → +<b>{(max_spd - base) * price:.0f} ₽</b>\n"
    
    keyboard = [[btn("🔙 К тарифу", f"tariff_{tariff_id}")]]
    return text, InlineKeyboardMarkup(keyboard)

# ===== ADMIN PANEL =====
def build_admin_panel(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build admin panel menu."""
    stats = db.get_subscription_stats()
    total_active = sum(s.get("active_count", 0) for s in stats.values())
    
    text = (
        "👑 <b>Админ-панель</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Пользователей: <b>{db.get_user_count()}</b>\n"
        f"🟢 Активных подписок: <b>{total_active}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [
        [btn("📊 Статистика", "admin_stats"), btn("👥 Пользователи", "admin_users")],
        [btn("📋 Подписки", "admin_subscriptions"), btn("🔍 Найти", "admin_find")],
        [btn("📝 Логи", "admin_logs")],
        [btn("🔙 В меню", "main_menu")],
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def build_admin_stats() -> tuple[str, InlineKeyboardMarkup]:
    """Build admin statistics view."""
    stats = db.get_subscription_stats()
    total_users = db.get_user_count()
    total_active = db.get_active_subscription_count()
    
    text = (
        "📊 <b>Статистика</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🟢 Активных подписок: <b>{total_active}</b>\n\n"
        "<b>По тарифам:</b>\n"
    )
    
    icons = {"youtube": "📺", "basic": "🛡️", "premium": "💎", "extreme": "🔥", "power": "⚡"}
    
    for tid, stat in stats.items():
        icon = icons.get(tid, "📦")
        text += f"{icon} {stat['name']}: <b>{stat.get('active_count', 0)}</b>\n"
    
    keyboard = [[back_btn("admin_panel")]]
    return text, InlineKeyboardMarkup(keyboard)

def build_admin_users() -> tuple[str, InlineKeyboardMarkup]:
    """Build users list view."""
    users = db.get_all_users(limit=15)
    
    if not users:
        return "👥 Пользователей пока нет", InlineKeyboardMarkup([[back_btn("admin_panel")]])
    
    text = "👥 <b>Последние пользователи:</b>\n\n"
    
    for user in users:
        status = "🔴" if user.get("banned") else "🟢"
        name = user.get("first_name") or f"ID:{user['user_id']}"
        username = user.get("username")
        uname = f" @{username}" if username else ""
        admin = " 👑" if user.get("is_admin") else ""
        text += f"{status} <code>{user['user_id']}</code> — {name}{uname}{admin}\n"
    
    keyboard = [[back_btn("admin_panel")]]
    return text, InlineKeyboardMarkup(keyboard)

def build_admin_subscriptions() -> tuple[str, InlineKeyboardMarkup]:
    """Build subscriptions management view."""
    stats = db.get_subscription_stats()
    
    text = "📋 <b>Подписки по тарифам:</b>\n\n"
    
    for tid, tariff in TARIFFS.items():
        count = stats.get(tid, {}).get("active_count", 0)
        text += f"{tariff['name']}: <b>{count}</b> активных\n"
    
    keyboard = [[back_btn("admin_panel")]]
    return text, InlineKeyboardMarkup(keyboard)

def build_admin_logs() -> tuple[str, InlineKeyboardMarkup]:
    """Build admin logs view."""
    logs = db.get_admin_logs(limit=20)
    
    if not logs:
        return "📝 Логов пока нет", InlineKeyboardMarkup([[back_btn("admin_panel")]])
    
    text = "📝 <b>Последние действия:</b>\n\n"
    
    for log in logs:
        admin = log.get("admin_first_name") or f"ID:{log['admin_id']}"
        action = log.get("action", "—")
        target = log.get("target_user_id")
        target_str = f" → ID:{target}" if target else ""
        time = safe_date_format(log.get("created_at"))
        text += f"• {admin}: {action}{target_str}\n  <i>{time}</i>\n\n"
    
    keyboard = [[back_btn("admin_panel")]]
    return text, InlineKeyboardMarkup(keyboard)

def build_user_detail(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build user detail view for admin."""
    user = db.get_user_by_id(user_id)
    if not user:
        return "❌ Пользователь не найден", InlineKeyboardMarkup([[back_btn("admin_panel")]])
    
    active_sub = db.get_active_subscription(user_id)
    sub_name = TARIFFS.get(active_sub["tariff_id"], {}).get("name", "Нет") if active_sub else "Нет"
    
    text = (
        f"👤 <b>Пользователь {user_id}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Имя: <b>{user.get('first_name') or '—'}</b>\n"
        f"Username: <b>@{user.get('username') or '—'}</b>\n"
        f"Админ: <b>{'✅ Да' if user.get('is_admin') else '❌ Нет'}</b>\n"
        f"Статус: <b>{'🔴 Забанен' if user.get('banned') else '🟢 Активен'}</b>\n"
        f"Бан: <i>{user.get('ban_reason') or '—'}</i>\n"
        f"Регистрация: <i>{safe_date_format(user.get('registered_at'))}</i>\n\n"
        f"📌 Подписка: <b>{sub_name}</b>"
    )
    
    keyboard = [
        [btn("🔨 Забанить", f"ban_{user_id}"), btn("🔓 Разбанить", f"unban_{user_id}")],
        [btn("➕ Админ", f"makeadmin_{user_id}"), btn("➖ Убрать админа", f"removeadmin_{user_id}")],
        [back_btn("admin_panel")],
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    context.user_data["state"] = STATE_IDLE
    
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name or "",
        "username": user.username or "",
        "last_name": user.last_name or "",
    }
    user_info = db.get_or_create_user(user_data)
    
    if user_info.get("banned", 0) == 1:
        await update.message.reply_text(
            "🚫 <b>Доступ заблокирован</b>\n\n"
            f"Причина: <i>{user_info.get('ban_reason') or 'Не указана'}</i>"
        )
        return
    
    text, reply_markup = build_main_menu(user.id)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified handler for text messages based on state."""
    state = context.user_data.get("state", STATE_IDLE)
    text = update.message.text.strip()
    
    if state == STATE_FIND_USER:
        # Handle find user input
        try:
            user_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID пользователя")
            return
        
        context.user_data["state"] = STATE_IDLE
        
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Нет доступа")
            return
        
        user = db.get_user_by_id(user_id)
        if not user:
            msg_text, markup = "❌ Пользователь не найден", InlineKeyboardMarkup([[back_btn("admin_panel")]])
        else:
            context.user_data["last_viewed_user"] = user_id
            msg_text, markup = build_user_detail(user_id)
        
        await update.message.reply_text(msg_text, parse_mode="HTML", reply_markup=markup)
    
    elif state == STATE_BAN_REASON:
        # Handle ban reason input
        if not context.user_data.get("ban_target"):
            context.user_data["state"] = STATE_IDLE
            return
        
        target_id = context.user_data.pop("ban_target")
        context.user_data["state"] = STATE_IDLE
        
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Нет доступа")
            return
        
        reason = text if text != "навсегда" else None
        db.ban_user(target_id, reason=reason)
        db.log_admin_action(update.effective_user.id, "ban", target_id, reason)
        
        await update.message.reply_text(
            f"✅ Пользователь <code>{target_id}</code> забанен",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[back_btn("admin_panel")]])
        )
    
    else:
        # Default - show menu
        text, reply_markup = build_main_menu(update.effective_user.id)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query router."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Check ban
    if await check_banned(user_id):
        await query.edit_message_text("🚫 Доступ заблокирован")
        return
    
    # ===== MAIN MENU =====
    if data == "main_menu":
        text, markup = build_main_menu(user_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "menu_tariffs":
        text, markup = build_tariffs_menu()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "menu_subscription":
        text, markup = build_subscription_view(user_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "menu_speed":
        active_sub = db.get_active_subscription(user_id)
        if active_sub:
            text, markup = build_speed_calc(active_sub["tariff_id"])
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            text, markup = build_main_menu(user_id)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "menu_support":
        text = (
            "🛠 <b>Поддержка Avava VPN</b>\n\n"
            "Опишите проблему и отправьте сообщение.\n\n"
            "Мы ответим в ближайшее время!"
        )
        keyboard = [[back_btn()]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== TARIFFS =====
    elif data.startswith("tariff_"):
        tariff_id = data[7:]  # Remove "tariff_"
        text, markup = build_tariff_detail(tariff_id, user_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data.startswith("speed_calc_"):
        tariff_id = data[11:]  # Remove "speed_calc_"
        text, markup = build_speed_calc(tariff_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data.startswith("subscribe_"):
        tariff_id = data[10:]  # Remove "subscribe_"
        tariff = TARIFFS.get(tariff_id)
        
        if not tariff:
            await query.edit_message_text("❌ Тариф не найден")
            return
        
        # Cancel existing subscription
        active_sub = db.get_active_subscription(user_id)
        if active_sub:
            db.cancel_subscription(active_sub["id"], user_id)
        
        try:
            db.create_subscription(user_id, tariff_id)
            text = (
                f"✅ <b>Подписка активирована!</b>\n\n"
                f"📌 {tariff['name']}\n"
                f"⚡ {tariff['speed']}\n"
                f"⏱ {tariff['duration_days']} дней\n\n"
                f"Приятного использования!"
            )
        except Exception as e:
            text = f"❌ Ошибка: {str(e)}"
        
        keyboard = [[btn("📊 Моя подписка", "menu_subscription"), back_btn()]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("confirm_cancel_"):
        sub_id = data[15:]  # Remove "confirm_cancel_"
        text = (
            "⚠️ <b>Отменить подписку?</b>\n\n"
            "Подписка будет деактивирована.\n"
            "Это действие нельзя отменить."
        )
        keyboard = [
            [btn("✅ Да, отменить", f"cancel_{sub_id}"), btn("❌ Нет", "menu_subscription")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("cancel_"):
        sub_id = data[7:]  # Remove "cancel_"
        try:
            sid = int(sub_id)
            success = db.cancel_subscription(sid, user_id)
            if success:
                text = "✅ Подписка отменена"
            else:
                text = "❌ Не удалось отменить"
        except ValueError:
            text = "❌ Ошибка ID подписки"
        
        keyboard = [[btn("📋 Тарифы", "menu_tariffs"), btn("📊 Подписка", "menu_subscription")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== ADMIN PANEL =====
    elif data == "admin_panel":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        text, markup = build_admin_panel(user_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "admin_stats":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        text, markup = build_admin_stats()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "admin_users":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        text, markup = build_admin_users()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "admin_subscriptions":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        text, markup = build_admin_subscriptions()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "admin_logs":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        text, markup = build_admin_logs()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    elif data == "admin_find":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        context.user_data["state"] = STATE_FIND_USER
        text = (
            "🔍 <b>Поиск пользователя</b>\n\n"
            "Введите ID пользователя:"
        )
        keyboard = [[back_btn("admin_panel")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== ADMIN ACTIONS =====
    elif data.startswith("ban_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        target_id = int(data[4:])
        context.user_data["state"] = STATE_BAN_REASON
        context.user_data["ban_target"] = target_id
        text = (
            f"🔨 <b>Бан пользователя {target_id}</b>\n\n"
            "Введите причину или 'навсегда':"
        )
        keyboard = [[back_btn("admin_panel")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("unban_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        target_id = int(data[6:])
        db.unban_user(target_id)
        db.log_admin_action(user_id, "unban", target_id)
        text = f"✅ Пользователь <code>{target_id}</code> разбанен"
        keyboard = [[back_btn("admin_panel")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("makeadmin_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        target_id = int(data[10:])
        db.set_admin(target_id)
        db.log_admin_action(user_id, "make_admin", target_id)
        text = f"✅ Пользователь <code>{target_id}</code> стал админом"
        keyboard = [[back_btn("admin_panel")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("removeadmin_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        target_id = int(data[12:])
        db.remove_admin(target_id)
        db.log_admin_action(user_id, "remove_admin", target_id)
        text = f"✅ Админка у <code>{target_id}</code> снята"
        keyboard = [[back_btn("admin_panel")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors."""
    logger.error("Exception while handling update:", exc_info=context.error)

def main():
    """Start the bot."""
    app = Application.builder().token(config.BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    
    # Text messages (unified state handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    # All callbacks go through router
    app.add_handler(CallbackQueryHandler(callback_router))
    
    # Errors
    app.add_error_handler(error_handler)
    
    logger.info("🚀 Bot started with new UI")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
