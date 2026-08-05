# handlers/monitoring.py — Server monitoring for admin and user panel
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
import app_context
from database import db
from keyboards import (
    build_monitor_menu, build_monitor_detail,
    btn, back_btn,
)
from utils import is_admin

logger = logging.getLogger(__name__)

# Status constants for panel health
PANEL_STATUS_HEALTHY = "healthy"
PANEL_STATUS_DEGRADED = "degraded"
PANEL_STATUS_UNHEALTHY = "unhealthy"
PANEL_STATUS_UNKNOWN = "unknown"
PANEL_STATUS_ERROR = "error"

# In-memory alert state: panel_name -> last_alert_time
_panel_alert_state: Dict[str, datetime] = {}

# Cache for panel statuses (for user menu) with 10 second TTL
_panel_status_cache: Dict[str, Any] = {
    'data': None,
    'expiry': 0
}
_CACHE_TTL_SECONDS = 10
_CACHE_MAX_SIZE = 100  # Prevent memory leak


def _get_panel_statuses(force: bool = False) -> List[Dict[str, Any]]:
    """
    Get panel statuses, using cache if valid and not forced.
    Returns a list of dicts with keys: panel, health.
    """
    global _panel_status_cache
    now = time.time()
    if not force and _panel_status_cache['data'] is not None and now < _panel_status_cache['expiry']:
        return _panel_status_cache['data']
    
    # Fetch fresh data
    panels = []
    if app_context.xcontroller:
        try:
            panels = app_context.xcontroller.get_panels()
        except Exception as e:
            logger.exception(f"Failed to get panels: {e}")
    
    panel_statuses = []
    for panel in panels:
        panel_id = panel.get("id")
        # Validate panel_id
        if panel_id is None:
            logger.warning(f"Panel without ID found: {panel}")
            continue
            
        health = {"status": PANEL_STATUS_UNKNOWN, "latency_ms": None, "error": None}
        if app_context.xcontroller:
            try:
                health = app_context.xcontroller.check_panel_health(panel_id)
                # Validate health structure
                if not isinstance(health, dict):
                    logger.warning(f"Invalid health response for panel {panel_id}: {health}")
                    health = {"status": PANEL_STATUS_ERROR, "error": "Invalid health response"}
            except Exception as e:
                logger.exception(f"Failed to check panel health for panel {panel_id}: {e}")
                health = {"status": PANEL_STATUS_ERROR, "error": str(e)}
        
        panel_statuses.append({
            "panel": panel,
            "health": health
        })
    
    # Clean up cache if it gets too large
    if len(panel_statuses) > _CACHE_MAX_SIZE:
        logger.warning(f"Panel status cache size {len(panel_statuses)} exceeds limit {_CACHE_MAX_SIZE}")
        # Keep only recent entries (last 50%)
        keep_count = _CACHE_MAX_SIZE // 2
        panel_statuses = panel_statuses[-keep_count:]
    
    _panel_status_cache['data'] = panel_statuses
    _panel_status_cache['expiry'] = now + _CACHE_TTL_SECONDS
    return panel_statuses


async def handle_monitor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Show monitoring dashboard with all panels status."""
    query = update.callback_query
    
    if not is_admin(user_id):
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    # Get panels from X-Controller
    panel_statuses = _get_panel_statuses()
    
    text, markup = build_monitor_menu(panel_statuses)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_monitor_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Refresh monitoring data."""
    query = update.callback_query
    
    if not is_admin(user_id):
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    await query.answer("🔄 Обновление...")
    
    # Get fresh panel statuses
    panel_statuses = _get_panel_statuses(force=True)
    
    text, markup = build_monitor_menu(panel_statuses)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_monitor_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, panel_id_str: str):
    """Show detailed panel information."""
    query = update.callback_query
    
    if not is_admin(user_id):
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    try:
        panel_id = int(panel_id_str)
    except ValueError:
        await query.edit_message_text("❌ Неверный ID панели")
        return
    
    panel = None
    health = {"status": "unknown", "latency_ms": None, "error": None}
    
    if app_context.xcontroller:
        try:
            panel = app_context.xcontroller.get_panel_details(panel_id)
            if panel:
                health = app_context.xcontroller.check_panel_health(panel_id)
        except Exception as e:
            logger.error(f"Failed to get panel {panel_id}: {e}")
            health = {"status": "error", "error": str(e)}
    
    if not panel:
        await query.edit_message_text(
            "❌ Панель не найдена",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[back_btn("monitor_menu")]])
        )
        return
    
    text, markup = build_monitor_detail(panel, health)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_user_monitor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Show monitoring dashboard for regular users."""
    query = update.callback_query
    await query.answer()
    
    # Get cached panel statuses (shared with admin cache)
    panel_statuses = _get_panel_statuses()
    
    # Build simplified text for users
    text = (
        "📊 <b>Статус серверов</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if not panel_statuses:
        text += "📭 Серверов не настроено"
    else:
        for item in panel_statuses:
            panel = item["panel"]
            health = item["health"]
            
            name = panel.get("name", "Unknown")
            status = health.get("status", PANEL_STATUS_UNKNOWN)
            latency = health.get("latency_ms")
            
            # Status emoji using constants
            if status == PANEL_STATUS_HEALTHY:
                emoji = "🟢"
            elif status == PANEL_STATUS_DEGRADED:
                emoji = "🟡"
            elif status == PANEL_STATUS_UNHEALTHY:
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
    markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_user_monitor_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Refresh monitoring data for user view."""
    query = update.callback_query
    await query.answer("🔄 Обновление...")
    
    # Force refresh of cache
    panel_statuses = _get_panel_statuses(force=True)
    
    # Build same text as in user menu
    text = (
        "📊 <b>Статус серверов</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if not panel_statuses:
        text += "📭 Серверов не настроено"
    else:
        for item in panel_statuses:
            panel = item["panel"]
            health = item["health"]
            
            name = panel.get("name", "Unknown")
            status = health.get("status", PANEL_STATUS_UNKNOWN)
            latency = health.get("latency_ms")
            
            # Status emoji using constants
            if status == PANEL_STATUS_HEALTHY:
                emoji = "🟢"
            elif status == PANEL_STATUS_DEGRADED:
                emoji = "🟡"
            elif status == PANEL_STATUS_UNHEALTHY:
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
    markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


def get_panel_alert_state() -> Dict[str, datetime]:
    """Get current alert state (for testing/debugging)."""
    return _panel_alert_state.copy()


async def check_all_panels_and_alert(context: ContextTypes.DEFAULT_TYPE):
    """
    Background job to check all panels and send alerts if needed.
    Runs periodically based on MONITOR_INTERVAL_SECONDS config.
    """
    if not app_context.xcontroller:
        logger.warning("X-Controller not configured, skipping panel monitoring")
        return
    
    try:
        panels = app_context.xcontroller.get_panels()
    except Exception as e:
        logger.error(f"Failed to get panels for monitoring: {e}")
        return
    
    for panel in panels:
        panel_id = panel.get("id")
        panel_name = panel.get("name", "Unknown")
        
        if panel_id is None:
            continue
        
        try:
            health = app_context.xcontroller.check_panel_health(panel_id)
        except Exception as e:
            logger.error(f"Failed to check panel {panel_name} ({panel_id}): {e}")
            health = {"status": "error", "error": str(e)}
        
        status = health.get("status", PANEL_STATUS_UNKNOWN)
        
        # Validate status
        valid_statuses = {PANEL_STATUS_HEALTHY, PANEL_STATUS_DEGRADED, PANEL_STATUS_UNHEALTHY, PANEL_STATUS_ERROR, PANEL_STATUS_UNKNOWN}
        if status not in valid_statuses:
            logger.warning(f"Invalid panel status '{status}' for panel {panel_name}, treating as unknown")
            status = PANEL_STATUS_UNKNOWN
        
        # Check if we should alert
        if status in (PANEL_STATUS_UNHEALTHY, PANEL_STATUS_ERROR):
            # Check cooldown - use consistent time types
            last_alert = _panel_alert_state.get(panel_name)
            now = datetime.now()
            
            if last_alert is None or (now - last_alert).total_seconds() >= config.ALERT_COOLDOWN_MINUTES * 60:
                # Send alert to admins
                alert_text = (
                    f"🚨 <b>АЛЕРТ: Панель недоступна</b>\n\n"
                    f"📋 <b>Панель:</b> {panel_name}\n"
                    f"📊 <b>Статус:</b> {status}\n"
                )
                
                if health.get("error"):
                    alert_text += f"❌ <b>Ошибка:</b> {health.get('error', 'Unknown error')}\n"
                
                alert_text += f"🕐 <b>Время:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}"
                
                # Validate admin IDs before sending alerts
                if not config.ADMIN_IDS:
                    logger.warning("No admin IDs configured, skipping alert for panel {panel_name}")
                else:
                    # Send to all admins
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id,
                                text=alert_text,
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.exception(f"Failed to send alert to admin {admin_id}: {e}")
                
                # Update alert state
                _panel_alert_state[panel_name] = now
                logger.warning(f"Alert sent for panel {panel_name}: {status}")
        
        elif status == PANEL_STATUS_DEGRADED and config.ALERT_ON_DEGRADED:
            # Check cooldown for degraded
            last_alert = _panel_alert_state.get(panel_name)
            now = datetime.now()
            
            if last_alert is None or (now - last_alert).total_seconds() >= config.ALERT_COOLDOWN_MINUTES * 60:
                alert_text = (
                    f"⚠️ <b>ПРЕДУПРЕЖДЕНИЕ: Панель деградировала</b>\n\n"
                    f"📋 <b>Панель:</b> {panel_name}\n"
                    f"📊 <b>Статус:</b> {status}\n"
                )
                
                if health.get("latency_ms") is not None:
                    alert_text += f"⏱ <b>Задержка:</b> {health['latency_ms']} мс\n"
                
                alert_text += f"🕐 <b>Время:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}"
                
                # Validate admin IDs before sending alerts
                if not config.ADMIN_IDS:
                    logger.warning(f"No admin IDs configured, skipping degraded alert for panel {panel_name}")
                else:
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id,
                                text=alert_text,
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.exception(f"Failed to send degraded alert to admin {admin_id}: {e}")
                
                _panel_alert_state[panel_name] = now
                logger.warning(f"Degraded alert sent for panel {panel_name}: {status}")
        
        elif status == "healthy":
            # Clear alert state when panel recovers
            if panel_name in _panel_alert_state:
                del _panel_alert_state[panel_name]
                logger.info(f"Panel {panel_name} recovered, alert state cleared")


def clear_panel_alert_state(panel_name: str = None):
    """Clear alert state for a panel or all panels."""
    global _panel_alert_state
    if panel_name:
        _panel_alert_state.pop(panel_name, None)
    else:
        _panel_alert_state.clear()