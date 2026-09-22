# handlers/trial_nudge.py — Periodic follow-up for users with expired trials
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import db
from keyboards import build_main_menu

logger = logging.getLogger(__name__)

# Moscow time (UTC+3, no DST)
MOSCOW_TZ_OFFSET_HOURS = 3

NUDGE_TEXT = (
    "👋 Привет! Мы заметили, что вы попробовали наш продукт, "
    "но так и не перешли на платный план.\n\n"
    "Ваш пробный период закончился, но это легко исправить — "
    "выберите тариф в главном меню, и VPN снова заработает.\n\n"
    "💡 Если возникли вопросы или проблемы — напишите в поддержку, "
    "мы поможем разобраться с любым вопросом!"
)


def _moscow_now(context: ContextTypes.DEFAULT_TYPE):
    """Current time in Moscow timezone (fixed UTC+3)."""
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(hours=MOSCOW_TZ_OFFSET_HOURS)


def build_trial_nudge_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⏭ Пропустить", callback_data="trial_nudge_skip"),
            InlineKeyboardButton(
                "🔕 Не напоминать больше", callback_data="trial_nudge_mute"
            ),
        ],
        [InlineKeyboardButton("📨 Написать в поддержку", callback_data="trial_nudge_support")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_trial_nudges(context: ContextTypes.DEFAULT_TYPE):
    """Job callback: notify users with an expired, never-upgraded trial."""
    try:
        stale_users = db.get_stale_trial_users()
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to fetch stale trial users: %s", e)
        return

    if not stale_users:
        logger.info("Trial nudge job: no stale trial users found")
        return

    sent, failed = 0, 0
    for row in stale_users:
        user_id = row["user_id"]
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=NUDGE_TEXT,
                parse_mode="HTML",
                reply_markup=build_trial_nudge_keyboard(),
            )
            sent += 1
        except Exception as e:  # noqa: BLE001
            # User may have blocked the bot — log and continue
            failed += 1
            logger.warning("Trial nudge: failed to message user %s: %s", user_id, e)

    logger.info(
        "Trial nudge job done: sent=%d, failed=%d, total=%d",
        sent,
        failed,
        len(stale_users),
    )


def schedule_trial_nudge_job(app):
    """Schedule the trial follow-up job at 09:00 and 20:00 Moscow time."""
    if not app.job_queue:
        logger.warning("JobQueue unavailable — trial nudge job not scheduled")
        return

    from datetime import datetime, time, timedelta, timezone

    moscow_tz = timezone(timedelta(hours=MOSCOW_TZ_OFFSET_HOURS))

    for run_time in (time(9, 0), time(20, 0)):
        app.job_queue.run_daily(
            send_trial_nudges,
            time=run_time.replace(tzinfo=moscow_tz),
            name=f"trial_nudge_{run_time.hour:02d}",
        )
    logger.info("🔔 Trial nudge job scheduled at 09:00 and 20:00 Moscow time")


async def handle_trial_nudge_skip(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """'Пропустить' — just go to the main menu, keep nudges enabled."""
    query = update.callback_query
    text, markup = build_main_menu(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_trial_nudge_mute(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """'Не напоминать больше' — mute future nudges and go to the main menu."""
    query = update.callback_query
    db.set_trial_nudge_muted(user_id, True)
    text, markup = build_main_menu(user_id)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_trial_nudge_support(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """'Написать в поддержку' — open the support chat."""
    query = update.callback_query
    text = (
        "🛠 <b>Поддержка Avava VPN</b>\n\n"
        "Если у вас возникли вопросы или проблемы, "
        "перейдите в наш чат поддержки — там вам помогут!\n\n"
        "👇 Нажмите кнопку ниже, чтобы открыть чат."
    )
    keyboard = [
        [
            InlineKeyboardButton(
                "📨 Открыть чат поддержки", url="https://t.me/+2I6sevlNpo5mMjcy"
            )
        ],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )