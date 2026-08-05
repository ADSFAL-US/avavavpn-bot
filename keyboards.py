"""Keyboard and menu builders for Avava VPN Bot."""
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging

import config
import app_context
from database import db, TARIFFS
from utils import btn, back_btn, safe_date_format, is_admin

logger = logging.getLogger(__name__)


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
    
    keyboard.append([btn("👥 Реферальная система", "menu_referral"), btn("🛠 Поддержка", "menu_support")])
    keyboard.append([btn("📡 Статус серверов", "user_node_status")])
    
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
    
    keyboard = []
    
    # Кнопка использования дней — только если есть дни
    if user["referral_days"] > 0:
        keyboard.append([btn("🪙 Использовать дни", "use_days_menu")])
    
    keyboard.append([btn("🔄 Обновить", "menu_referral")])
    keyboard.append([back_btn()])
    return text, InlineKeyboardMarkup(keyboard)


# ===== USE DAYS MENU =====
def build_use_days_menu(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build menu to apply referral days to a subscription."""
    user = db.get_user_by_id(user_id)
    if not user:
        return "Ошибка", InlineKeyboardMarkup([[back_btn("menu_referral")]])
    
    days = int(user.get("referral_days", 0))
    active_sub = db.get_active_subscription(user_id)
    
    text = (
        "🪙 <b>Использовать реферальные дни</b>\n\n"
        f"У вас накоплено: <b>{days}</b> дней\n"
    )
    
    keyboard = []
    
    if active_sub and days > 0:
        tariff = TARIFFS.get(active_sub["tariff_id"], {})
        
        # Для premium — коэффициент 0.8
        effective_days = days
        if tariff.get("id") == "premium":
            effective_days = int(days * 0.8)
            text += "💎 Для тарифа Premium применяется коэффициент 0.8\n"
            text += f"Реально будет добавлено: <b>{effective_days}</b> дней\n\n"
        else:
            text += "\n"
        
        text += (
            f"📌 Текущая подписка: <b>{tariff.get('name', '—')}</b>\n"
            f"⏱ Действует до: {safe_date_format(active_sub.get('ends_at'))}\n\n"
            f"После применения дни будут списаны, а дата окончания продлена."
        )
        
        keyboard.append([btn(f"✅ Применить все {effective_days} дней", f"use_days_apply_{active_sub['id']}")])
    elif days <= 0:
        text += "\n❌ У вас нет накопленных дней для использования."
        text += "\n\n⚠️ Для использования дней сначала оформите активную подписку."
    else:
        text += "\n❌ Нет активной подписки, к которой можно применить дни.\n"
        text += "Сначала оформите подписку через меню тарифов."
        text += "\n\n⚠️ У вас нет накопленных дней для использования в текущем сценарии."
    
    keyboard.append([back_btn("menu_referral")])
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
        "<b>Включено:</b>\n" + "\n".join(perks)
        + current
    )
    
    # Buttons
    keyboard = []
    if tariff["price"] == 0:
        keyboard.append([btn("✅ Активировать бесплатно", f"subscribe_{tariff_id}")])
    else:
        keyboard.append([btn("💳 Выбрать тариф", f"subscribe_{tariff_id}")])
    
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
    
    # Whitelist bypass traffic (глушилки)
    whitelist_traffic = ""
    panel_sub_id = active_sub.get("panel_subscription_id")
    if panel_sub_id and app_context.xcontroller:
        try:
            wt = app_context.xcontroller.get_whitelist_bypass_traffic(panel_sub_id)
            if wt.get("success"):
                used_wl = wt.get("used_gb", 0)
                limit_wl = wt.get("limit_gb", 50)
                remaining_wl = wt.get("remaining_gb", 50)
                configs_count = wt.get("configs_count", 0)
                is_exhausted = wt.get("is_exhausted", False)
                
                percent_wl = min(100, int((used_wl / limit_wl) * 100)) if limit_wl > 0 else 0
                bar_fill_wl = int(percent_wl / 10)
                bar_wl = "█" * bar_fill_wl + "░" * (10 - bar_fill_wl)
                
                status_emoji = "🔴" if is_exhausted else "🟢"
                
                whitelist_traffic = (
                    f"\n{status_emoji} <b>Трафик обхода белых списков (глушилки):</b>\n"
                    f"<code>[{bar_wl}] {percent_wl}%</code>\n"
                    f"Использовано: <b>{used_wl:.2f}</b> / {limit_wl:.1f} ГБ\n"
                    f"Осталось: <b>{remaining_wl:.2f}</b> ГБ\n"
                    f"Конфигов: <b>{configs_count}</b>"
                )
            else:
                whitelist_traffic = (
                    f"\n⚪ <b>Трафик обхода белых списков (глушилки):</b>\n"
                    f"Недоступно"
                )
        except Exception as e:
            logger.warning(f"Failed to get whitelist bypass traffic: {e}")
            whitelist_traffic = (
                f"\n⚪ <b>Трафик обхода белых списков (глушилки):</b>\n"
                f"Ошибка загрузки"
            )
    else:
        whitelist_traffic = (
            f"\n⚪ <b>Трафик обхода белых списков (глушилки):</b>\n"
            f"50.00 / 50.0 ГБ (нет конфигов)"
        )
    
    text = (
        f"📌 <b>{tariff.get('name', 'Подписка')}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Скорость:</b> {active_sub.get('speed_mbps', 0)} Мбит/с\n"
        f"🔰 <b>Warp:</b> {'✅ Вкл' if active_sub.get('warp_enabled') else '❌ Выкл'}\n"
        f"🧪 <b>Тестовые конфиги:</b> {'✅ Доступ' if active_sub.get('test_configs_enabled') else '❌ Нет доступа'}\n"
        f"⏱ <b>До:</b> {safe_date_format(active_sub.get('ends_at'))}"
        + traffic
        + whitelist_traffic
    )
    
    keyboard = [
        [btn("📋 Другие тарифы", "menu_tariffs"), btn("🔄 Сменить тариф", f"change_tariff_{active_sub['id']}")],
        [btn("🔁 Продлить", f"extend_{active_sub['id']}"), btn("🔗 Получить ссылку", f"get_link_{active_sub['id']}")],
        [btn("❌ Отменить подписку", f"confirm_cancel_{active_sub['id']}")],
        [back_btn()],
    ]
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
        [btn("🎁 Выдать подписку", "admin_give_subscription")],
        [btn("📝 Логи", "admin_logs")],
        [btn("🧪 Симуляция реферала", "admin_simulate_referral")],
        [btn("� Мониторинг панелей", "monitor_menu")],
        [btn("�🔙 В меню", "main_menu")],
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


# ===== MONITORING =====
def build_monitor_menu(panel_statuses: list) -> tuple[str, InlineKeyboardMarkup]:
    """Build monitoring dashboard menu."""
    text = (
        "📊 <b>Мониторинг панелей</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if not panel_statuses:
        text += "📭 Панелей не настроено в X-Controller"
    else:
        for item in panel_statuses:
            panel = item["panel"]
            health = item["health"]
            
            name = panel.get("name", "Unknown")
            host = panel.get("host", "unknown")
            priority = panel.get("priority", 0)
            max_clients = panel.get("max_clients", 0)
            
            status = health.get("status", "unknown")
            latency = health.get("latency_ms")
            error = health.get("error")
            
            # Status emoji
            if status == "healthy":
                emoji = "🟢"
            elif status == "degraded":
                emoji = "🟡"
            elif status == "unhealthy":
                emoji = "🔴"
            else:
                emoji = "⚪"
            
            text += f"{emoji} <b>{name}</b>\n"
            text += f"   🌐 <code>{host}</code> | Приоритет: {priority} | Макс. клиентов: {max_clients}\n"
            
            if latency is not None:
                text += f"   ⏱ Задержка: <b>{latency} мс</b>\n"
            
            if error:
                text += f"   ❌ <i>{error}</i>\n"
            
            text += "\n"
    
    text += f"🕐 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    
    keyboard = []
    for item in panel_statuses:
        panel = item["panel"]
        panel_id = panel.get("id")
        name = panel.get("name", "Unknown")
        if panel_id:
            keyboard.append([btn(f"📋 {name}", f"monitor_detail_{panel_id}")])
    
    keyboard.append([btn("🔄 Обновить", "monitor_refresh")])
    keyboard.append([back_btn("admin_panel")])
    
    return text, InlineKeyboardMarkup(keyboard)


def build_monitor_detail(panel: dict, health: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Build detailed panel view."""
    name = panel.get("name", "Unknown")
    host = panel.get("host", "unknown")
    panel_path = panel.get("panel_path", "")
    sub_path = panel.get("sub_path", "/sub")
    username = panel.get("username", "admin")
    priority = panel.get("priority", 0)
    max_clients = panel.get("max_clients", 0)
    panel_id = panel.get("id")
    
    status = health.get("status", "unknown")
    latency = health.get("latency_ms")
    error = health.get("error")
    last_checked = health.get("last_checked")
    
    # Status emoji and text
    if status == "healthy":
        status_emoji = "🟢"
        status_text = "Здорова"
    elif status == "degraded":
        status_emoji = "🟡"
        status_text = "Деградирована"
    elif status == "unhealthy":
        status_emoji = "🔴"
        status_text = "Недоступна"
    else:
        status_emoji = "⚪"
        status_text = "Неизвестно"
    
    text = (
        f"{status_emoji} <b>Панель: {name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 <b>Хост:</b> <code>{host}</code>\n"
    )
    
    if panel_path:
        text += f"📁 <b>Путь панели:</b> <code>{panel_path}</code>\n"
    text += f"🔗 <b>Путь подписки:</b> <code>{sub_path}</code>\n"
    text += f"👤 <b>Пользователь:</b> <code>{username}</code>\n"
    text += f"⭐ <b>Приоритет:</b> {priority}\n"
    text += f"👥 <b>Макс. клиентов:</b> {max_clients}\n\n"
    
    text += f"📊 <b>Статус:</b> {status_text} ({status})\n"
    
    if latency is not None:
        text += f"⏱ <b>Задержка:</b> {latency} мс\n"
    
    if last_checked:
        text += f"🕐 <b>Последняя проверка:</b> {last_checked}\n"
    
    if error:
        text += f"\n❌ <b>Ошибка:</b>\n<code>{error}</code>\n"
    
    keyboard = [
        [btn("🔄 Проверить сейчас", f"monitor_check_{panel_id}")],
        [back_btn("monitor_menu")],
    ]
    
    return text, InlineKeyboardMarkup(keyboard)


def build_user_node_status(panel_statuses: list) -> tuple[str, InlineKeyboardMarkup]:
    """Build simplified node status view for regular users."""
    text = (
        "📡 <b>Статус серверов</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if not panel_statuses:
        text += "📭 Серверов не настроено"
    else:
        for item in panel_statuses:
            panel = item["panel"]
            health = item["health"]
            
            name = panel.get("name", "Unknown")
            status = health.get("status", "unknown")
            latency = health.get("latency_ms")
            
            # Status emoji
            if status == "healthy":
                emoji = "🟢"
            elif status == "degraded":
                emoji = "🟡"
            elif status == "unhealthy":
                emoji = "🔴"
            else:
                emoji = "⚪"
            
            text += f"{emoji} <b>{name}</b>"
            if latency is not None:
                text += f" | ⏱ {latency} мс"
            text += "\n"
    
    text += f"\n🕐 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    
    keyboard = [
        [btn("🔄 Обновить", "user_monitor_refresh")],
        [btn("🏠 Главное меню", "main_menu")]
    ]
    
    return text, InlineKeyboardMarkup(keyboard)