# Avava VPN Bot - Redesigned UI (Single Message Interface)
import logging
import uuid

from telegram import (
    Update,
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
from yookassa import YooKassaAPI, PaymentStorage
from xcontroller_client import XControllerClient, SubscriptionManager
import app_context
from utils import (
    STATE_IDLE, STATE_FIND_USER, STATE_BAN_REASON,
    STATE_SIMULATE_REFERRAL_USERID, STATE_ADMIN_GIVE_USER_ID, STATE_ADMIN_GIVE_DAYS,
    is_admin, btn, back_btn,
    check_channel_subscription, build_subscription_prompt,
)
from keyboards import (
    build_main_menu, build_user_detail,
)
from handlers.navigation import (
    handle_main_menu, handle_menu_tariffs, handle_menu_subscription,
    handle_menu_support, handle_menu_referral, handle_use_days_menu,
    handle_tariff, handle_get_link, handle_confirm_cancel,
    handle_cancel, handle_use_days_apply,
)
from handlers.payments import (
    handle_subscribe, handle_check_payment,
    handle_change_tariff, handle_confirm_change,
    handle_pay_change, handle_check_change_payment,
    handle_extend,
)
from handlers.admin import (
    handle_admin_panel, handle_admin_stats, handle_admin_users,
    handle_admin_subscriptions, handle_admin_logs,
    handle_admin_give_subscription, handle_admin_give_tariff,
    handle_admin_simulate_referral, handle_admin_find,
    handle_ban, handle_unban, handle_makeadmin, handle_removeadmin,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ===== INITIALIZE CLIENTS =====
# YooKassa payment client
app_context.yookassa = None
if config.YOOKASSA_SHOP_ID and config.YOOKASSA_API_KEY:
    try:
        app_context.yookassa = YooKassaAPI(
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
app_context.payment_storage = PaymentStorage(db.conn)

# X-Controller client
app_context.xcontroller = None
if config.XCONTROLLER_URL and config.XCONTROLLER_PASSWORD:
    try:
        app_context.xcontroller = XControllerClient()
        logger.info("X-Controller client initialized: %s", config.XCONTROLLER_URL)
    except Exception as e:
        logger.error("Failed to initialize X-Controller: %s", e)
else:
    logger.warning("X-Controller not configured - subscription creation will be disabled")

# Subscription manager
app_context.subscription_manager = None
if app_context.xcontroller:
    app_context.subscription_manager = SubscriptionManager(db, app_context.xcontroller)

# UI builders are now in keyboards.py

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
    
    # Channel subscription softlock
    if config.REQUIRED_CHANNEL_USERNAME and not is_admin(user.id):
        if not await check_channel_subscription(user.id, context):
            text, markup = build_subscription_prompt()
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
            return
    
    text, reply_markup = build_main_menu(user.id)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified handler for text messages based on state."""
    state = context.user_data.get("state", STATE_IDLE)
    text = update.message.text.strip()
    
    # Channel subscription softlock (skip for admins)
    if config.REQUIRED_CHANNEL_USERNAME and not is_admin(update.effective_user.id):
        if not await check_channel_subscription(update.effective_user.id, context):
            prompt_text, markup = build_subscription_prompt()
            await update.message.reply_text(prompt_text, parse_mode="HTML", reply_markup=markup)
            return
    
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
    
    elif state == STATE_ADMIN_GIVE_USER_ID:
        # Получаем ID пользователя для выдачи подписки
        try:
            target_user_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID пользователя")
            return
        
        context.user_data["state"] = STATE_IDLE
        
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Нет доступа")
            return
        
        # Проверяем, существует ли пользователь в БД
        target_user = db.get_user_by_id(target_user_id)
        if not target_user:
            await update.message.reply_text(
                f"❌ Пользователь <code>{target_user_id}</code> не найден в БД.\n"
                "Сначала он должен запустить бота (/start).",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем target_user_id, показываем выбор тарифа
        context.user_data["admin_give_target"] = target_user_id
        text = "🎁 <b>Выберите тариф для выдачи:</b>\n\n"
        keyboard = []
        for tid, tariff in TARIFFS.items():
            price = "Бесплатно" if tariff["price"] == 0 else f"{tariff['price']}₽"
            keyboard.append([btn(f"{tariff['name']} — {price}", f"admin_give_tariff_{tid}")])
        keyboard.append([back_btn("admin_panel")])
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif state == STATE_ADMIN_GIVE_DAYS:
        # Получаем количество дней
        try:
            days = int(text)
        except ValueError:
            await update.message.reply_text("❌ Введите целое число дней")
            return
        
        if days <= 0:
            await update.message.reply_text("❌ Количество дней должно быть больше 0")
            return
        
        context.user_data["state"] = STATE_IDLE
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Нет доступа")
            return
        
        target_user_id = context.user_data.get("admin_give_target")
        tariff_id = context.user_data.get("admin_give_tariff")
        
        if not target_user_id or not tariff_id:
            await update.message.reply_text("❌ Ошибка: данные не найдены. Начните заново.")
            return
        
        tariff = TARIFFS.get(tariff_id)
        if not tariff:
            await update.message.reply_text("❌ Тариф не найден")
            return
        
        # Проверяем, есть ли уже активная подписка
        active_sub = db.get_active_subscription(target_user_id)
        
        try:
            if active_sub:
                # Меняем существующую подписку
                sub_id = active_sub["id"]
                result = app_context.subscription_manager.change_subscription(
                    subscription_id=sub_id,
                    new_tariff_id=tariff_id,
                    expiry_days=days,
                )
                action_text = "изменена"
            else:
                # Создаём новую подписку
                result = app_context.subscription_manager.create_subscription(
                    user_id=target_user_id,
                    tariff_id=tariff_id,
                    preset_id=tariff.get("preset_id"),
                    expiry_days=days,
                )
                action_text = "создана"
            
            if not result.get("success"):
                error = result.get("error", "Неизвестная ошибка")
                await update.message.reply_text(
                    f"❌ <b>Ошибка выдачи подписки</b>\n\n{error}",
                    parse_mode="HTML"
                )
                return
            
            sub_link = result.get("sub_link", "N/A")
            db.log_admin_action(admin_id, f"give_subscription_{action_text}", target_user_id, f"tariff={tariff_id}, days={days}")
            
            await update.message.reply_text(
                f"✅ <b>Подписка {action_text}!</b>\n\n"
                f"👤 Пользователь: <code>{target_user_id}</code>\n"
                f"📌 Тариф: {tariff['name']}\n"
                f"⏱ Дней: {days}\n"
                f"🔗 Ссылка: <code>{sub_link}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[back_btn("admin_panel")]])
            )
        except Exception as e:
            logger.exception(f"Error giving subscription: {e}")
            await update.message.reply_text(
                f"❌ <b>Ошибка:</b> {str(e)}",
                parse_mode="HTML"
            )
    
    elif state == STATE_SIMULATE_REFERRAL_USERID:
        try:
            test_user_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID пользователя")
            return

        context.user_data["state"] = STATE_IDLE
        admin_id = update.effective_user.id

        if not is_admin(admin_id):
            await update.message.reply_text("❌ Нет доступа")
            return

        # 1. Получаем или создаём тестового пользователя
        test_user = db.get_or_create_user({"user_id": test_user_id, "first_name": "TestUser", "username": ""})
        # Принудительно устанавливаем referred_by (если ещё не заполнен)
        if not test_user.get("referred_by") or test_user["referred_by"] != admin_id:
            cursor = db.conn.cursor()
            cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (admin_id, test_user_id))
            # Сбрасываем флаги для чистоты эксперимента
            cursor.execute("UPDATE users SET has_rewarded_referrer = 0, has_used_discount = 0 WHERE user_id = ?", (test_user_id,))
            db.conn.commit()
            # Обновляем данные в переменной
            test_user = db.get_user_by_id(test_user_id)

        # 2. Проверяем, есть ли у админа реферальный код, и если нет — генерируем
        admin_user = db.get_user_by_id(admin_id)
        if not admin_user.get("referral_code"):
            referral_code = f"REF_{admin_id}_{uuid.uuid4().hex[:6]}"
            cursor = db.conn.cursor()
            cursor.execute("UPDATE users SET referral_code = ? WHERE user_id = ?", (referral_code, admin_id))
            db.conn.commit()

        # 3. Проверяем, не использовал ли тестовый пользователь пробный период
        if db.has_user_ever_had_tariff(test_user_id, "trial"):
            # Отменяем старый trial только для этого пользователя
            db.cancel_subscription_by_tariff("trial", user_id=test_user_id)
            logger.info(f"Old trial cancelled for user {test_user_id} to allow simulation")

        # 4. Берём тариф trial
        tariff = TARIFFS.get("trial")
        if not tariff or not app_context.subscription_manager:
            await update.message.reply_text("❌ Нет тарифа trial или не настроен X-Controller")
            return

        # 5. Создаём подписку trial через менеджер
        result = app_context.subscription_manager.create_subscription(
            user_id=test_user_id,
            tariff_id="trial",
            preset_id=tariff.get("preset_id"),
        )

        if not result.get("success"):
            error = result.get("error", "Неизвестная ошибка")
            await update.message.reply_text(f"❌ Ошибка создания подписки: {error}")
            return

        sub_link = result.get("sub_link", "N/A")

        # 6. Начисляем бонус рефереру (единый метод)
        db.reward_referrer(test_user_id, "trial")

        # 7. Ответ админу
        await update.message.reply_text(
            f"✅ <b>Симуляция успешна!</b>\n\n"
            f"Пользователь <code>{test_user_id}</code> активировал пробный период.\n"
            f"Подписка создана, ссылка: <code>{sub_link}</code>\n\n"
            f"Реферер (вы) получили <b>7 реферальных дней</b>.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[btn("👑 Админ-панель", "admin_panel")]])
        )
    
    else:
        # Default - show menu
        text, reply_markup = build_main_menu(update.effective_user.id)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query router — dispatches to domain handlers."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # Shared pre-checks (ban + channel subscription) are done inside each handler
    # ===== NAVIGATION =====
    if data == "main_menu":
        await handle_main_menu(update, context, user_id)
    elif data == "menu_tariffs":
        await handle_menu_tariffs(update, context, user_id)
    elif data == "menu_subscription":
        await handle_menu_subscription(update, context, user_id)
    elif data == "menu_support":
        await handle_menu_support(update, context, user_id)
    elif data == "menu_referral":
        await handle_menu_referral(update, context, user_id)
    elif data == "use_days_menu":
        await handle_use_days_menu(update, context, user_id)
    elif data.startswith("tariff_"):
        await handle_tariff(update, context, user_id, data[7:])
    elif data.startswith("get_link_"):
        await handle_get_link(update, context, user_id, data[9:])
    elif data.startswith("confirm_cancel_"):
        await handle_confirm_cancel(update, context, user_id, data[15:])
    elif data.startswith("use_days_apply_"):
        await handle_use_days_apply(update, context, user_id, data[15:])
    elif data.startswith("cancel_"):
        await handle_cancel(update, context, user_id, data[7:])

    # ===== PAYMENTS =====
    elif data.startswith("subscribe_"):
        await handle_subscribe(update, context, user_id, data[10:])
    elif data.startswith("check_payment_"):
        await handle_check_payment(update, context, user_id, data[14:])
    elif data.startswith("change_tariff_"):
        await handle_change_tariff(update, context, user_id, data[14:])
    elif data.startswith("confirm_change_"):
        await handle_confirm_change(update, context, user_id, data[15:])
    elif data.startswith("pay_change_"):
        await handle_pay_change(update, context, user_id, data[11:])
    elif data.startswith("check_change_payment_"):
        await handle_check_change_payment(update, context, user_id, data[20:])
    elif data.startswith("extend_"):
        await handle_extend(update, context, user_id, data[7:])

    # ===== ADMIN =====
    elif data == "admin_panel":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_panel(update, context, user_id)
    elif data == "admin_stats":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_stats(update, context, user_id)
    elif data == "admin_users":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_users(update, context, user_id)
    elif data == "admin_subscriptions":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_subscriptions(update, context, user_id)
    elif data == "admin_logs":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_logs(update, context, user_id)
    elif data == "admin_give_subscription":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_give_subscription(update, context, user_id)
    elif data.startswith("admin_give_tariff_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_give_tariff(update, context, user_id, data[18:])
    elif data == "admin_simulate_referral":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_simulate_referral(update, context, user_id)
    elif data == "admin_find":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_admin_find(update, context, user_id)
    elif data.startswith("ban_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_ban(update, context, user_id, data[4:])
    elif data.startswith("unban_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_unban(update, context, user_id, data[6:])
    elif data.startswith("makeadmin_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_makeadmin(update, context, user_id, data[10:])
    elif data.startswith("removeadmin_"):
        if not is_admin(user_id):
            await query.edit_message_text("❌ Нет доступа")
            return
        await handle_removeadmin(update, context, user_id, data[12:])

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
