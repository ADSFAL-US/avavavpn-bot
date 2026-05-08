# Avava VPN Bot - Redesigned UI (Single Message Interface)
import logging
import uuid
from datetime import datetime, timedelta

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
from yookassa import YooKassaAPI, PaymentStorage, PAYMENT_STATUS_SUCCEEDED, PAYMENT_STATUS_CANCELLED
from xcontroller_client import XControllerClient, SubscriptionManager

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ===== INITIALIZE CLIENTS =====
# YooKassa payment client
yookassa = None
if config.YOOKASSA_SHOP_ID and config.YOOKASSA_API_KEY:
    try:
        yookassa = YooKassaAPI(
            shop_id=config.YOOKASSA_SHOP_ID,
            api_key=config.YOOKASSA_API_KEY,
            test_mode=config.YOOKASSA_TEST_MODE,
        )
        logger.info("YooKassa client initialized (test_mode=%s)", config.YOOKASSA_TEST_MODE)
    except Exception as e:
        logger.error("Failed to initialize YooKassa: %s", e)
else:
    logger.warning("YooKassa not configured - payments will be disabled")

# Payment storage
payment_storage = PaymentStorage(db.conn)

# X-Controller client
xcontroller = None
if config.XCONTROLLER_URL and config.XCONTROLLER_PASSWORD:
    try:
        xcontroller = XControllerClient()
        logger.info("X-Controller client initialized: %s", config.XCONTROLLER_URL)
    except Exception as e:
        logger.error("Failed to initialize X-Controller: %s", e)
else:
    logger.warning("X-Controller not configured - subscription creation will be disabled")

# Subscription manager
subscription_manager = None
if xcontroller:
    subscription_manager = SubscriptionManager(db, xcontroller)

# ===== STATE MANAGEMENT =====
STATE_IDLE = "idle"
STATE_FIND_USER = "find_user"
STATE_BAN_REASON = "ban_reason"
STATE_PAYMENT_PENDING = "payment_pending"

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
        keyboard.append([btn("❌ Отменить подписку", f"confirm_cancel_{active_sub['id']}")])
    
    keyboard.append([btn("👥 Реферальная система", "menu_referral"), btn(" Поддержка", "menu_support")])
    
    if is_admin(user_id):
        keyboard.append([btn("👑 Админ-панель", "admin_panel")])
    
    return text, InlineKeyboardMarkup(keyboard)

# ===== REFERRAL MENU =====
def build_referral_menu(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build referral menu."""
    user = db.get_user_by_id(user_id)
    if not user:
        return "Ошибка", InlineKeyboardMarkup([[back_btn()]])
    
    text = (
        "👥 <b>Реферальная система</b>\n\n"
        f"Ваша реферальная ссылка:\n<code>https://t.me/{config.BOT_USERNAME}?start=ref_{user['referral_code']}</code>\n\n"
        f"Накоплено дней: <b>{user['referral_days']}</b>\n\n"
        "За каждого привлеченного друга, который активирует пробный тариф, вы получите 7 дней.\n"
        "Дни можно использовать для продления подписки."
    )
    
    keyboard = [
        [btn("🔄 Обновить", "menu_referral")],
        [back_btn()]
    ]
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
    perks.append("✅ Тестовые конфиги" if tariff.get("test_configs", False) else "❌ Тестовые конфиги")
    
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
    
    # No speed upgrades available
    
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
        f"🧪 <b>Тестовые конфиги:</b> {'✅ Доступ' if active_sub.get('test_configs_enabled') else '❌ Нет доступа'}\n"
        f"⏱ <b>До:</b> {safe_date_format(active_sub.get('ends_at'))}"
        + traffic
    )
    
    keyboard = [
        [btn("📋 Другие тарифы", "menu_tariffs"), btn("🔄 Сменить тариф", f"change_tariff_{active_sub['id']}")],
        [btn("🔁 Продлить", f"extend_{active_sub['id']}"), btn("🔗 Получить ссылку", f"get_link_{active_sub['id']}")],
        [btn("🪙 Использовать дни", f"use_days_{active_sub['id']}")],
        [btn("❌ Отменить подписку", f"confirm_cancel_{active_sub['id']}")],
        [back_btn()],
    ]
    return text, InlineKeyboardMarkup(keyboard)

# Speed calculator removed - no longer supported

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
    
    icons = {"trial": "🧪", "basic": "🛡️", "premium": "💎"}
    
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
    
    # Check for referral code
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        ref_code = context.args[0][4:]
        cursor = db.conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,))
        ref_user = cursor.fetchone()
        # Prevent self-referral
        if ref_user and ref_user["user_id"] != user.id:
            referred_by = ref_user["user_id"]
    
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name or "",
        "username": user.username or "",
        "last_name": user.last_name or "",
        "referred_by": referred_by
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

async def _handle_free_subscription(update: Update, user_id: int, tariff_id: str, tariff: dict):
    """Handle free subscription (trial tariff) creation."""
    query = update.callback_query
    
    try:
        # Create subscription via SubscriptionManager
        result = subscription_manager.create_subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            preset_id=tariff.get("preset_id"),  # Use preset_id from tariff
        )
        
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Free subscription creation failed: {error}")
            await query.edit_message_text(
                f"❌ <b>Ошибка активации</b>\n\n{error}"
            )
            return
        
        sub_link = result.get("sub_link", "N/A")
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


async def _create_paid_subscription(update: Update, user_id: int, tariff_id: str, tariff: dict, payment_id: str):
    """Create subscription after successful payment."""
    query = update.callback_query
    
    try:
        # Create subscription via SubscriptionManager
        result = subscription_manager.create_subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            payment_id=payment_id,
            preset_id=tariff.get("preset_id"),  # Use preset_id from tariff
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


async def _handle_tariff_change(update: Update, user_id: int, sub_id: int, new_tariff_id: str, new_tariff: dict):
    """Handle tariff change after payment confirmation."""
    query = update.callback_query
    
    try:
        # Use SubscriptionManager to change tariff
        if not subscription_manager:
            await query.edit_message_text("❌ Сервис подписок недоступен")
            return
        
        result = subscription_manager.change_subscription(sub_id, new_tariff_id)
        
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
    
    # Speed upgrades removed
    
    elif data == "menu_support":
        text = (
            "🛠 <b>Поддержка Avava VPN</b>\n\n"
            "Опишите проблему и отправьте сообщение.\n\n"
            "Мы ответим в ближайшее время!"
        )
        keyboard = [[back_btn()]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_referral":
        text, markup = build_referral_menu(user_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    # ===== TARIFFS =====
    elif data.startswith("tariff_"):
        tariff_id = data[7:]  # Remove "tariff_"
        text, markup = build_tariff_detail(tariff_id, user_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    
    # Speed calculator removed
    
    elif data.startswith("subscribe_"):
        tariff_id = data[10:]  # Remove "subscribe_"
        tariff = TARIFFS.get(tariff_id)
        
        if not tariff:
            await query.edit_message_text("❌ Тариф не найден")
            return
        
        # Check if user already has active subscription
        active_sub = db.get_active_subscription(user_id)
        if active_sub:
            active_tariff = TARIFFS.get(active_sub["tariff_id"], {})
            await query.edit_message_text(
                f"❌ <b>У вас уже есть активная подписка</b>\n\n"
                f"📌 Текущий тариф: {active_tariff.get('name', 'Неизвестный')}\n"
                f"⏱ Действует до: {safe_date_format(active_sub.get('ends_at'))}\n\n"
                f"Для смены тарифа отмените текущую подписку в меню «Моя подписка»."
            )
            return
            
        # For trial tariff, check if user has ever had a trial before
        if tariff_id == "trial":
            if db.has_user_ever_had_tariff(user_id, "trial"):
                await query.edit_message_text(
                    "❌ <b>Пробный тариф можно активировать только один раз</b>\n\n"
                    "Вы уже использовали пробный период ранее."
                )
                return
        
        # Check if X-Controller is configured
        if not subscription_manager:
            await query.edit_message_text(
                "❌ <b>Сервис временно недоступен</b>\n\n"
                "Система подписок не настроена.\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку."
            )
            return
        
        # Free tariff (youtube) - create immediately without payment
        if tariff.get("price", 0) == 0:
            await _handle_free_subscription(update, user_id, tariff_id, tariff)
            return
        
        # Paid tariff - create payment
        if not yookassa:
            await query.edit_message_text(
                "❌ <b>Платежная система недоступна</b>\n\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку."
            )
            return
        
        amount = tariff.get("price", 0)
        
        # Apply 10% discount for new referred users (only for paid tariffs)
        discount = 0
        user_info = db.get_user_by_id(user_id)
        if user_info.get("referred_by") and not user_info.get("has_used_discount") and tariff_id not in ["trial", "basic", "premium"]:
            discount = amount * 0.1
            amount -= discount
            
        # Create YooKassa payment
        order_id = f"avava_{user_id}_{tariff_id}_{uuid.uuid4().hex[:8]}"
        
        payment_result = yookassa.create_payment(
            amount=amount,
            description=f"Avava VPN - {tariff['name']}",
            user_id=user_id,
            tariff_id=tariff_id,
            order_id=order_id,
        )
        
        if not payment_result.get("success"):
            error_msg = payment_result.get("error", "Unknown error")
            logger.error(f"Payment creation failed: {error_msg}")
            await query.edit_message_text(
                f"❌ <b>Ошибка создания платежа</b>\n\n"
                f"{error_msg}\n\n"
                f"Пожалуйста, попробуйте позже или обратитесь в поддержку."
            )
            return
        
        # Store payment in database
        payment_storage.create_payment_record(
            order_id=order_id,
            user_id=user_id,
            tariff_id=tariff_id,
            amount=amount,
            payment_id=payment_result.get("payment_id"),
        )
        
        # Show payment link
        payment_url = payment_result.get("payment_url")
        text = (
            f"💳 <b>Оплата тарифа</b>\n\n"
            f"📌 {tariff['name']}\n"
            f"💰 Сумма: {amount} руб.\n\n"
            f"Нажмите кнопку ниже для оплаты.\n"
            f"После оплаты нажмите «Проверить оплату»."
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
            [btn("🔄 Проверить оплату", f"check_payment_{order_id}")],
            [back_btn("menu_tariffs")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Store state for payment check
        context.user_data["pending_order_id"] = order_id
        context.user_data["state"] = STATE_PAYMENT_PENDING
    
    elif data.startswith("check_payment_"):
        order_id = data[14:]  # Remove "check_payment_"
        
        # Get payment from database
        payment_record = payment_storage.get_payment_by_order(order_id)
        if not payment_record:
            await query.edit_message_text("❌ Платеж не найден")
            return
        
        # Check if already processed
        if payment_record.get("status") == "completed":
            await query.edit_message_text(
                "✅ <b>Платеж уже обработан</b>\n\n"
                "Ваша подписка активна."
            )
            return
        
        # Check payment status with YooKassa
        payment_id = payment_record.get("payment_id")
        if not payment_id:
            await query.edit_message_text("❌ Ошибка: ID платежа не найден")
            return
        
        check_result = yookassa.check_payment(payment_id)
        
        if check_result.get("error"):
            await query.edit_message_text(
                f"❌ <b>Ошибка проверки</b>\n\n"
                f"{check_result['error']}"
            )
            return
        
        status = check_result.get("status")
        paid = check_result.get("paid", False)
        
        if status == PAYMENT_STATUS_SUCCEEDED and paid:
            # Payment successful - create subscription
            tariff_id = payment_record.get("tariff_id")
            tariff = TARIFFS.get(tariff_id)
            
            if not tariff:
                await query.edit_message_text("❌ Тариф не найден")
                return
            
            # Update payment status
            payment_storage.update_payment_status(order_id, "completed", payment_id)
            
            # Create subscription
            await _create_paid_subscription(update, user_id, tariff_id, tariff, payment_id)
            
            # Award referral only once per referred user
            user_info = db.get_user_by_id(user_id)
            if user_info.get("referred_by") and not user_info.get("has_rewarded_referrer") and tariff_id != "trial":
                # Prevent self-reward
                if user_info["referred_by"] != user_id:
                    # Award referrer
                    db.add_referral_days(user_info["referred_by"], 7)
                    
                    # Mark as rewarded
                    cursor = db.conn.cursor()
                    cursor.execute(
                        "UPDATE users SET has_rewarded_referrer = 1 WHERE user_id = ?",
                        (user_id,)
                    )
                    db.conn.commit()
                
                # Mark discount as used
                if discount > 0:
                    db.set_discount_used(user_id)
            
            # If extending, cancel old subscription
            if order_id.startswith("extend_"):
                try:
                    old_sub_id = int(order_id.split("_")[1])
                    if subscription_manager.cancel_subscription(old_sub_id):
                        logger.info(f"Extended: canceled old subscription {old_sub_id}")
                    else:
                        logger.error(f"Failed to cancel old subscription {old_sub_id} for extension")
                except (IndexError, ValueError) as e:
                    logger.error(f"Error parsing old_sub_id from order_id {order_id}: {e}")
                    
        elif status == PAYMENT_STATUS_CANCELLED:
            payment_storage.update_payment_status(order_id, "cancelled", payment_id)
            await query.edit_message_text(
                "❌ <b>Платеж отменен</b>\n\n"
                "Вы можете попробовать снова."
            )
        else:
            # Still pending
            await query.answer("⏳ Платеж в обработке...")
            await query.edit_message_text(
                f"⏳ <b>Платеж в обработке</b>\n\n"
                f"Статус: {status}\n\n"
                f"Если вы уже оплатили, подождите несколько минут и проверьте снова.",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🔄 Проверить снова", f"check_payment_{order_id}")],
                    [back_btn("menu_tariffs")],
                ])
            )
    
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
    
    elif data.startswith("change_tariff_"):
        sub_id = data[14:]  # Remove "change_tariff_"
        try:
            sid = int(sub_id)
            # Show available tariffs for change
            active_sub = db.get_subscription_by_id(sid)
            if not active_sub or active_sub["user_id"] != user_id:
                await query.edit_message_text("❌ Подписка не найдена")
                return
            
            current_tariff_id = active_sub["tariff_id"]
            text = "🔄 <b>Выберите новый тариф:</b>\n\n"
            keyboard = []
            
            for tid, tariff in TARIFFS.items():
                if tid != current_tariff_id:  # Don't show current tariff
                    price = "Бесплатно" if tariff["price"] == 0 else f"{tariff['price']}₽"
                    keyboard.append([btn(f"{tariff['name']} — {price}", f"confirm_change_{sid}_{tid}")])
            
            keyboard.append([btn("❌ Отмена", "menu_subscription")])
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except ValueError:
            await query.edit_message_text("❌ Ошибка ID подписки")
    
    elif data.startswith("confirm_change_"):
        parts = data[15:].split("_")  # Remove "confirm_change_" and split
        if len(parts) != 2:
            await query.edit_message_text("❌ Ошибка данных")
            return
        
        sub_id = int(parts[0])
        new_tariff_id = parts[1]
        new_tariff = TARIFFS.get(new_tariff_id)
        
        if not new_tariff:
            await query.edit_message_text("❌ Тариф не найден")
            return
        
        # Check if paid tariff
        if new_tariff["price"] > 0:
            # Show payment options
            text = (
                f"🔄 <b>Смена тарифа</b>\n\n"
                f"С {TARIFFS.get(db.get_subscription_by_id(sub_id)['tariff_id'], {}).get('name', 'текущего')} "
                f"на {new_tariff['name']}\n\n"
                f"💰 Стоимость: <b>{new_tariff['price']} {new_tariff['currency']}</b>\n\n"
                "Нажмите «Оплатить смену» для продолжения."
            )
            keyboard = [
                [btn("💳 Оплатить смену", f"pay_change_{sub_id}_{new_tariff_id}")],
                [btn("❌ Отмена", "menu_subscription")]
            ]
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # Free tariff - change immediately
            await _handle_tariff_change(update, user_id, sub_id, new_tariff_id, new_tariff)
    
    elif data.startswith("pay_change_"):
        parts = data[11:].split("_")  # Remove "pay_change_" and split
        if len(parts) != 2:
            await query.edit_message_text("❌ Ошибка данных")
            return
        
        sub_id = int(parts[0])
        new_tariff_id = parts[1]
        new_tariff = TARIFFS.get(new_tariff_id)
        
        if not new_tariff:
            await query.edit_message_text("❌ Тариф не найден")
            return
        
        # Create payment for tariff change
        order_id = f"change_{user_id}_{sub_id}_{new_tariff_id}"
        
        payment_result = yookassa.create_payment(
            amount=new_tariff["price"],
            description=f"Смена тарифа на {new_tariff['name']}",
            user_id=user_id,
            tariff_id=new_tariff_id,
            order_id=order_id,
        )
        
        if not payment_result.get("success"):
            error_msg = payment_result.get("error", "Unknown error")
            await query.edit_message_text(
                f"❌ <b>Ошибка создания платежа</b>\n\n{error_msg}"
            )
            return
        
        # Store payment
        payment_storage.create_payment_record(
            order_id=order_id,
            user_id=user_id,
            tariff_id=new_tariff_id,
            amount=new_tariff["price"],
            payment_id=payment_result.get("payment_id"),
        )
        
        # Show payment link
        payment_url = payment_result.get("payment_url")
        text = (
            f"💳 <b>Оплата смены тарифа</b>\n\n"
            f"📌 {new_tariff['name']}\n"
            f"💰 Сумма: {new_tariff['price']} руб.\n\n"
            f"Нажмите кнопку ниже для оплаты."
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
            [btn("🔄 Проверить оплату", f"check_change_payment_{order_id}")],
            [btn("❌ Отмена", "menu_subscription")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("check_change_payment_"):
        order_id = data[20:]  # Remove "check_change_payment_"
        
        # Get payment from database
        payment_record = payment_storage.get_payment_by_order(order_id)
        if not payment_record:
            await query.edit_message_text("❌ Платеж не найден")
            return
        
        # Check if already processed
        if payment_record.get("status") == "completed":
            await query.edit_message_text(
                "✅ <b>Платеж уже обработан</b>\n\n"
                "Тариф изменен."
            )
            return
        
        # Check payment status with YooKassa
        payment_id = payment_record.get("payment_id")
        if not payment_id:
            await query.edit_message_text("❌ Ошибка: ID платежа не найден")
            return
        
        check_result = yookassa.check_payment(payment_id)
        
        if check_result.get("error"):
            await query.edit_message_text(
                f"❌ <b>Ошибка проверки</b>\n\n{check_result['error']}"
            )
            return
        
        status = check_result.get("status")
        paid = check_result.get("paid", False)
        
        if status == PAYMENT_STATUS_SUCCEEDED and paid:
            # Payment successful - extract subscription and new tariff from order_id
            parts = order_id.split("_")
            if len(parts) >= 4:
                sub_id = int(parts[2])
                new_tariff_id = parts[3]
                new_tariff = TARIFFS.get(new_tariff_id)
                
                if new_tariff:
                    # Update payment status
                    payment_storage.update_payment_status(order_id, "completed", payment_id)
                    
                    # Change tariff
                    await _handle_tariff_change(update, user_id, sub_id, new_tariff_id, new_tariff)
                else:
                    await query.edit_message_text("❌ Тариф не найден")
            else:
                await query.edit_message_text("❌ Ошибка данных заказа")
        elif status == PAYMENT_STATUS_CANCELLED:
            payment_storage.update_payment_status(order_id, "cancelled", payment_id)
            await query.edit_message_text(
                "❌ <b>Платеж отменен</b>\n\n"
                "Вы можете попробовать снова."
            )
        else:
            # Still pending
            await query.answer("⏳ Платеж в обработке...")
    
    elif data.startswith("get_link_"):
        sub_id = data[9:]  # Remove "get_link_"
        try:
            sid = int(sub_id)
            active_sub = db.get_subscription_by_id(sid)
            if not active_sub or active_sub["user_id"] != user_id:
                await query.edit_message_text("❌ Подписка не найдена")
                return
                
            link = subscription_manager.get_user_subscription_link(user_id)
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
            
    elif data.startswith("use_days_"):
        sub_id = data[10:]  # Remove "use_days_"
        try:
            sid = int(sub_id)
            active_sub = db.get_subscription_by_id(sid)
            if not active_sub or active_sub["user_id"] != user_id:
                await query.edit_message_text("❌ Подписка не найдена")
                return
                
            user_info = db.get_user_by_id(user_id)
            if not user_info or user_info["referral_days"] <= 0:
                await query.edit_message_text("❌ У вас нет дней для использования")
                return
                
            tariff = TARIFFS.get(active_sub["tariff_id"])
            if not tariff:
                await query.edit_message_text("❌ Тариф не найден")
                return
                
            # Calculate days to add based on tariff
            days_to_add = user_info["referral_days"]
            if tariff["id"] == "premium":
                days_to_add = int(user_info["referral_days"] * 0.8)
            
            # Update subscription end date
            # Handle date format
            ends_at = active_sub["ends_at"]
            if not ends_at:
                ends_at = datetime.now().isoformat()
            
            # Strip timezone info if present
            if "+" in ends_at:
                ends_at = ends_at.split("+")[0]
            
            new_end = datetime.fromisoformat(ends_at) + timedelta(days=days_to_add)
            cursor = db.conn.cursor()
            cursor.execute(
                "UPDATE subscriptions SET ends_at = ? WHERE id = ?",
                (new_end.isoformat(), sid)
            )
            db.conn.commit()
            
            # Reset referral days
            cursor.execute(
                "UPDATE users SET referral_days = 0 WHERE user_id = ?",
                (user_id,)
            )
            db.conn.commit()
            
            await query.edit_message_text(
                f"✅ Использовано {user_info['referral_days']} дней\n"
                f"Добавлено {days_to_add} дней к подписке\n"
                f"Новая дата окончания: {safe_date_format(new_end.isoformat())}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[btn("📊 Моя подписка", "menu_subscription")]])
            )
            
        except Exception as e:
            logger.error(f"Error using referral days: {e}")
            await query.edit_message_text("❌ Ошибка при использовании дней")
            
    elif data.startswith("extend_"):
        sub_id = data[7:]  # Remove "extend_"
        try:
            sid = int(sub_id)
            active_sub = db.get_subscription_by_id(sid)
            if not active_sub or active_sub["user_id"] != user_id:
                await query.edit_message_text("❌ Подписка не найдена")
                return
                
            tariff_id = active_sub["tariff_id"]
            tariff = TARIFFS.get(tariff_id)
            if not tariff:
                await query.edit_message_text("❌ Тариф не найден")
                return
                
            # Check if free tariff - cannot extend free
            if tariff.get("price", 0) == 0:
                await query.edit_message_text("❌ Бесплатный тариф нельзя продлить")
                return
                
            # Check if X-Controller is configured
            if not subscription_manager:
                await query.edit_message_text("❌ Сервис подписок недоступен")
                return
                
            # Check if YooKassa is available
            if not yookassa:
                await query.edit_message_text("❌ Платежная система недоступна")
                return
                
            # Create order_id with prefix "extend_"
            order_id = f"extend_{sid}_{uuid.uuid4().hex[:8]}"
            amount = tariff.get("price", 0)
            
            # Create payment
            payment_result = yookassa.create_payment(
                amount=amount,
                description=f"Avava VPN - Продление {tariff['name']}",
                user_id=user_id,
                tariff_id=tariff_id,
                order_id=order_id,
            )
            
            if not payment_result.get("success"):
                error_msg = payment_result.get("error", "Unknown error")
                logger.error(f"Payment creation failed: {error_msg}")
                await query.edit_message_text(
                    f"❌ <b>Ошибка создания платежа</b>\n\n{error_msg}"
                )
                return
                
            # Store payment
            payment_storage.create_payment_record(
                order_id=order_id,
                user_id=user_id,
                tariff_id=tariff_id,
                amount=amount,
                payment_id=payment_result.get("payment_id"),
            )
            
            # Show payment link
            payment_url = payment_result.get("payment_url")
            text = (
                f"💳 <b>Продление тарифа</b>\n\n"
                f"📌 {tariff['name']}\n"
                f"💰 Сумма: {amount} руб.\n\n"
                f"Нажмите кнопку ниже для оплаты.\n"
                f"После оплаты нажмите «Проверить оплату»."
            )
            
            keyboard = [
                [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
                [btn("🔄 Проверить оплату", f"check_payment_{order_id}")],
                [back_btn("menu_subscription")],
            ]
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            
            # Store state for payment check
            context.user_data["pending_order_id"] = order_id
            context.user_data["state"] = STATE_PAYMENT_PENDING
            
        except ValueError:
            await query.edit_message_text("❌ Ошибка ID подписки")
            
    elif data.startswith("cancel_"):
        sub_id = data[7:]  # Remove "cancel_"
        try:
            sid = int(sub_id)
            # Use SubscriptionManager to cancel from both panel and DB
            if subscription_manager:
                success = subscription_manager.cancel_subscription(sid)
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
