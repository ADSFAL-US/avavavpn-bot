# handlers/monitoring.py — Server monitoring for admin and user panel
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import app_context
import cache
import config
from keyboards import (
    back_btn,
    btn,
    build_monitor_detail,
    build_monitor_menu,
)
from utils import is_admin

logger = logging.getLogger(__name__)


def _spawn_background(context, coro) -> None:
    """Schedule a background task, tolerating mocked contexts in tests."""
    app = getattr(context, "application", None)
    if app is not None and hasattr(app, "create_task"):
        app.create_task(coro)
    else:
        asyncio.create_task(coro)


async def _safe_edit(query, text: str, markup: InlineKeyboardMarkup) -> None:
    """Edit message, swallowing the harmless 'message is not modified' error."""
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        if "not modified" not in str(e):
            raise


def _placeholder_statuses(
    statuses: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Statuses to render while a background refresh is in flight.

    If we have stale data, show it as-is (better than nothing);
    otherwise return an empty list so the menu renders a loading state.
    """
    return statuses or []

# Status constants for panel health
PANEL_STATUS_HEALTHY = "healthy"
PANEL_STATUS_DEGRADED = "degraded"
PANEL_STATUS_UNHEALTHY = "unhealthy"
PANEL_STATUS_UNKNOWN = "unknown"
PANEL_STATUS_ERROR = "error"

# In-memory alert state: panel_name -> last_alert_time
_panel_alert_state: dict[str, datetime] = {}

# Cache for panel statuses lives in Redis (global, user-independent).
# In-memory copy is only a fallback for when Redis is unavailable.
_panel_status_cache: dict[str, Any] = {
    "data": None,
    "expiry": 0,
}
_CACHE_TTL_SECONDS = 10
_CACHE_MAX_SIZE = 100  # Prevent memory leak

# Guards against concurrent background refreshes (self-DoS protection)
_refresh_in_progress = False


def _fetch_panel_statuses() -> list[dict[str, Any]]:
    """Fetch fresh panel statuses from X-Controller (slow, blocking)."""
    panels = []
    if app_context.xcontroller:
        try:
            panels = app_context.xcontroller.get_panels()
        except (requests.RequestException, ValueError):
            logger.exception("Failed to get panels")

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
                    logger.warning(
                        f"Invalid health response for panel {panel_id}: {health}"
                    )
                    health = {
                        "status": PANEL_STATUS_ERROR,
                        "error": "Invalid health response",
                    }
            except (requests.RequestException, ValueError):
                logger.exception(f"Failed to check panel health for panel {panel_id}")
                health = {"status": PANEL_STATUS_ERROR, "error": "Health check failed"}

        panel_statuses.append({"panel": panel, "health": health})

    # Clean up cache if it gets too large
    if len(panel_statuses) > _CACHE_MAX_SIZE:
        logger.warning(
            f"Panel status cache size {len(panel_statuses)} exceeds limit {_CACHE_MAX_SIZE}"
        )
        # Keep only recent entries (last 50%)
        keep_count = _CACHE_MAX_SIZE // 2
        panel_statuses = panel_statuses[-keep_count:]

    return panel_statuses


def _store_panel_statuses(panel_statuses: list[dict[str, Any]]) -> None:
    """Persist panel statuses to Redis (global) and in-memory fallback."""
    _panel_status_cache["data"] = panel_statuses
    _panel_status_cache["expiry"] = time.time() + config.PANEL_STATUS_CACHE_TTL
    cache.set_json(
        cache.panel_statuses_key(), panel_statuses, ttl=config.PANEL_STATUS_CACHE_TTL
    )


def _get_panel_statuses(force: bool = False) -> list[dict[str, Any]]:
    """
    Get panel statuses, using the global Redis cache if valid and not forced.
    Returns a list of dicts with keys: panel, health.
    """
    if not force:
        cached = cache.get_json(cache.panel_statuses_key())
        if cached is not None:
            return cached
        # Redis miss — fall back to in-memory copy (may be stale but usable)
        if (
            _panel_status_cache["data"] is not None
            and time.time() < _panel_status_cache["expiry"]
        ):
            return _panel_status_cache["data"]

    return _fetch_panel_statuses()


def _get_panel_statuses_cached_or_stale() -> tuple[list[dict[str, Any]] | None, bool]:
    """
    Fast path for UI handlers (stale-while-revalidate).

    Returns (statuses, is_fresh):
      - statuses is None only if there is no data at all (never fetched)
      - is_fresh=True  -> data came from a valid cache, no refresh needed
      - is_fresh=False -> data is stale/missing; caller should refresh in background
    """
    cached = cache.get_json(cache.panel_statuses_key())
    if cached is not None:
        return cached, True
    if _panel_status_cache["data"] is not None:
        # Stale in-memory data — show it, refresh in background
        return _panel_status_cache["data"], False
    return None, False


async def refresh_panel_statuses_background() -> list[dict[str, Any]] | None:
    """
    Refresh panel statuses in the background (single-flight).

    Runs the blocking fetch in a thread, stores the result in Redis and
    returns it. Returns None if another refresh is already running or
    the fetch produced no data.
    """
    global _refresh_in_progress
    if _refresh_in_progress:
        return None
    _refresh_in_progress = True
    try:
        statuses = await asyncio.to_thread(_fetch_panel_statuses)
        if statuses:
            _store_panel_statuses(statuses)
            return statuses
        return None
    finally:
        _refresh_in_progress = False


async def handle_monitor_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Show monitoring dashboard with all panels status (cached, non-blocking)."""
    query = update.callback_query

    if not is_admin(user_id):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    await query.answer()

    statuses, is_fresh = _get_panel_statuses_cached_or_stale()

    if is_fresh:
        text, markup = build_monitor_menu(statuses or [])
        await _safe_edit(query, text, markup)
        return

    # Stale/missing — render placeholder instantly, refresh in background
    text, markup = build_monitor_menu(_placeholder_statuses(statuses))
    await _safe_edit(query, text, markup)

    async def _refresh_and_rerender():
        fresh = await refresh_panel_statuses_background()
        if fresh is None:
            return
        new_text, new_markup = build_monitor_menu(fresh)
        await _safe_edit(query, new_text, new_markup)

    _spawn_background(context, _refresh_and_rerender())


async def handle_monitor_refresh(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Refresh monitoring data."""
    query = update.callback_query

    if not is_admin(user_id):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    await query.answer("🔄 Обновление...")

    # Get fresh panel statuses
    panel_statuses = await refresh_panel_statuses_background()
    if panel_statuses is None:
        # Another refresh in progress or fetch failed — fall back to cache
        panel_statuses = _get_panel_statuses()

    text, markup = build_monitor_menu(panel_statuses)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_monitor_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, panel_id_str: str
):
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
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to get panel {panel_id}: {e}")
            health = {"status": "error", "error": str(e)}

    if not panel:
        await query.edit_message_text(
            "❌ Панель не найдена",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[back_btn("monitor_menu")]]),
        )
        return

    text, markup = build_monitor_detail(panel, health)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_user_monitor_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Show monitoring dashboard for regular users (cached, non-blocking)."""
    query = update.callback_query
    await query.answer()

    statuses, is_fresh = _get_panel_statuses_cached_or_stale()

    text, markup = _build_user_monitor_view(statuses, loading=not is_fresh)
    await _safe_edit(query, text, markup)

    if is_fresh:
        return

    async def _refresh_and_rerender():
        fresh = await refresh_panel_statuses_background()
        if fresh is None:
            return
        new_text, new_markup = _build_user_monitor_view(fresh, loading=False)
        await _safe_edit(query, new_text, new_markup)

    _spawn_background(context, _refresh_and_rerender())


def _build_user_monitor_view(
    panel_statuses: list[dict[str, Any]] | None, loading: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    """Build the user-facing server status text and keyboard."""
    # Build simplified text for users
    text = "📊 <b>Статус серверов</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if not panel_statuses:
        text += "📭 Серверов не настроено" if not loading else "⏳ Загружаем данные..."
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

    if loading:
        text += "\n⏳ <i>Обновляем данные...</i>"
    text += f"\n🕐 <i>Обновлено: {datetime.now(timezone.utc).strftime('%H:%M:%S')}</i>"

    keyboard = [
        [btn("🔄 Обновить", "user_monitor_refresh")],
        [btn("🏠 Главное меню", "main_menu")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def handle_user_monitor_refresh(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Refresh monitoring data for user view."""
    query = update.callback_query
    await query.answer("🔄 Обновление...")

    # Force refresh (single-flight)
    panel_statuses = await refresh_panel_statuses_background()
    if panel_statuses is None:
        panel_statuses = _get_panel_statuses()

    text, markup = _build_user_monitor_view(panel_statuses, loading=False)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


def get_panel_alert_state() -> dict[str, datetime]:
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
    except (requests.RequestException, ValueError) as e:
        logger.error(f"Failed to get panels for monitoring: {e}")
        return

    for panel in panels:
        panel_id = panel.get("id")
        panel_name = panel.get("name", "Unknown")

        if panel_id is None:
            continue

        try:
            health = app_context.xcontroller.check_panel_health(panel_id)
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to check panel {panel_name} ({panel_id}): {e}")
            health = {"status": "error", "error": str(e)}

        status = health.get("status", PANEL_STATUS_UNKNOWN)

        # Validate status
        valid_statuses = {
            PANEL_STATUS_HEALTHY,
            PANEL_STATUS_DEGRADED,
            PANEL_STATUS_UNHEALTHY,
            PANEL_STATUS_ERROR,
            PANEL_STATUS_UNKNOWN,
        }
        if status not in valid_statuses:
            logger.warning(
                f"Invalid panel status '{status}' for panel {panel_name}, treating as unknown"
            )
            status = PANEL_STATUS_UNKNOWN

        # Check if we should alert
        if status in (PANEL_STATUS_UNHEALTHY, PANEL_STATUS_ERROR):
            # Check cooldown - use consistent time types
            last_alert = _panel_alert_state.get(panel_name)
            now = datetime.now(timezone.utc)

            if (
                last_alert is None
                or (now - last_alert).total_seconds()
                >= config.ALERT_COOLDOWN_MINUTES * 60
            ):
                # Send alert to admins
                alert_text = (
                    f"🚨 <b>АЛЕРТ: Панель недоступна</b>\n\n"
                    f"📋 <b>Панель:</b> {panel_name}\n"
                    f"📊 <b>Статус:</b> {status}\n"
                )

                if health.get("error"):
                    alert_text += (
                        f"❌ <b>Ошибка:</b> {health.get('error', 'Unknown error')}\n"
                    )

                alert_text += f"🕐 <b>Время:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}"

                # Validate admin IDs before sending alerts
                if not config.ADMIN_IDS:
                    logger.warning(
                        "No admin IDs configured, skipping alert for panel {panel_name}"
                    )
                else:
                    # Send to all admins
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id, text=alert_text, parse_mode="HTML"
                            )
                        except (RuntimeError, ValueError):
                            logger.exception(
                                f"Failed to send alert to admin {admin_id}"
                            )

                # Update alert state
                _panel_alert_state[panel_name] = now
                logger.warning(f"Alert sent for panel {panel_name}: {status}")

        elif status == PANEL_STATUS_DEGRADED and config.ALERT_ON_DEGRADED:
            # Check cooldown for degraded
            last_alert = _panel_alert_state.get(panel_name)
            now = datetime.now(timezone.utc)

            if (
                last_alert is None
                or (now - last_alert).total_seconds()
                >= config.ALERT_COOLDOWN_MINUTES * 60
            ):
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
                    logger.warning(
                        f"No admin IDs configured, skipping degraded alert for panel {panel_name}"
                    )
                else:
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id, text=alert_text, parse_mode="HTML"
                            )
                        except (RuntimeError, ValueError):
                            logger.exception(
                                f"Failed to send degraded alert to admin {admin_id}"
                            )

                _panel_alert_state[panel_name] = now
                logger.warning(f"Degraded alert sent for panel {panel_name}: {status}")

        elif status == "healthy":
            # Clear alert state when panel recovers
            if panel_name in _panel_alert_state:
                del _panel_alert_state[panel_name]
                logger.info(f"Panel {panel_name} recovered, alert state cleared")


def clear_panel_alert_state(panel_name: str | None = None):
    """Clear alert state for a panel or all panels."""
    global _panel_alert_state  # noqa: PLW0602
    if panel_name:
        _panel_alert_state.pop(panel_name, None)
    else:
        _panel_alert_state.clear()
