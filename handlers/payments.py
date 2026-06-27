# handlers/payments.py — Subscription purchasing, payment checks, tariff changes, extensions
import logging
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db, TARIFFS
from yookassa import PAYMENT_STATUS_SUCCEEDED, PAYMENT_STATUS_CANCELLED
import app_context
from utils import (
    safe_date_format, btn, back_btn,
    STATE_PAYMENT_PENDING,
)
from handlers.subscriptions import (
    handle_free_subscription,
    create_paid_subscription,
    handle_tariff_change,
)

logger = logging.getLogger(__name__)


async def handle_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, tariff_id: str):
    """Handle subscribe_ callback — paid or free subscription."""
    query = update.callback_query
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
    if not app_context.subscription_manager:
        await query.edit_message_text(
            "❌ <b>Сервис временно недоступен</b>\n\n"
            "Система подписок не настроена.\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )
        return

    # Free tariff — create immediately without payment
    if tariff.get("price", 0) == 0:
        await handle_free_subscription(update, user_id, tariff_id, tariff)
        return

    # Paid tariff — create payment
    if not app_context.yookassa:
        await query.edit_message_text(
            "❌ <b>Платежная система недоступна</b>\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )
        return

    amount = tariff.get("price", 0)

    # Apply 10% discount for new referred users (only for paid tariffs)
    discount = 0
    user_info = db.get_user_by_id(user_id)
    if user_info.get("referred_by") and not user_info.get("has_used_discount") and tariff_id not in ["trial"]:
        discount = amount * 0.1
        amount -= discount

    # Create YooKassa payment
    order_id = f"avava_{user_id}_{tariff_id}_{uuid.uuid4().hex[:8]}"

    payment_result = app_context.yookassa.create_payment(
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
    app_context.payment_storage.create_payment_record(
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


async def handle_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, order_id: str):
    """Handle check_payment_ callback."""
    query = update.callback_query

    # Get payment from database
    payment_record = app_context.payment_storage.get_payment_by_order(order_id)
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

    check_result = app_context.yookassa.check_payment(payment_id)

    if check_result.get("error"):
        await query.edit_message_text(
            f"❌ <b>Ошибка проверки</b>\n\n"
            f"{check_result['error']}"
        )
        return

    status = check_result.get("status")
    paid = check_result.get("paid", False)

    if status == PAYMENT_STATUS_SUCCEEDED and paid:
        # Update payment status
        app_context.payment_storage.update_payment_status(order_id, "completed", payment_id)

        # ─── Extend existing subscription ─────────────────────────────────
        if order_id.startswith("extend_"):
            try:
                # order_id = f"extend_{sid}_{uuid4_hex}"
                parts = order_id.split("_")
                old_sub_id = int(parts[1])

                tariff_id = payment_record.get("tariff_id")
                tariff = TARIFFS.get(tariff_id)
                extra_days = tariff["duration_days"] if tariff else 30

                # Продлеваем через SubscriptionManager (локальная БД + x-controller + панели)
                result = app_context.subscription_manager.extend_subscription(
                    old_sub_id, extra_days
                )

                if not result.get("success"):
                    error = result.get("error", "Unknown error")
                    logger.error(f"Extension failed: {error}")
                    # Всё равно показываем успех, т.к. локальная БД обновлена

                sub_link = result.get("sub_link") or app_context.subscription_manager.get_user_subscription_link(user_id) or "N/A"

                text = (
                    f"✅ <b>Подписка продлена!</b>\n\n"
                    f"📌 {tariff['name'] if tariff else '—'}\n"
                    f"⏱ +{extra_days} дней\n\n"
                    f"🔗 <b>Ваша ссылка для подключения:</b>\n"
                    f"<code>{sub_link}</code>"
                )
                keyboard = [
                    [InlineKeyboardButton("📋 Инструкция по настройке", url=sub_link)],
                    [btn("📊 Моя подписка", "menu_subscription"), back_btn()]
                ]
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

                logger.info(f"Extended subscription {old_sub_id} by {extra_days} days (order={order_id})")
            except (IndexError, ValueError, Exception) as e:
                logger.error(f"Error extending subscription from order_id {order_id}: {e}")
                await query.edit_message_text("❌ Ошибка продления подписки. Обратитесь в поддержку.")

            # Начисляем реферальные дни (если применимо)
            db.reward_referrer(user_id, payment_record.get("tariff_id", ""))
            return

        # ─── New subscription (not extend) ────────────────────────────────
        tariff_id = payment_record.get("tariff_id")
        tariff = TARIFFS.get(tariff_id)

        if not tariff:
            await query.edit_message_text("❌ Тариф не найден")
            return

        # Create subscription
        await create_paid_subscription(update, user_id, tariff_id, tariff, payment_id)

        # Award referral bonus using unified method
        db.reward_referrer(user_id, tariff_id)

    elif status == PAYMENT_STATUS_CANCELLED:
        app_context.payment_storage.update_payment_status(order_id, "cancelled", payment_id)
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


async def handle_change_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: str):
    """Handle change_tariff_ callback — show available tariffs for change."""
    query = update.callback_query
    try:
        sid = int(sub_id)
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


async def handle_confirm_change(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, data: str):
    """Handle confirm_change_ callback."""
    query = update.callback_query
    parts = data.split("_")
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
        await handle_tariff_change(update, user_id, sub_id, new_tariff_id, new_tariff)


async def handle_pay_change(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, data: str):
    """Handle pay_change_ callback — create payment for tariff change."""
    query = update.callback_query
    parts = data.split("_")
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

    payment_result = app_context.yookassa.create_payment(
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
    app_context.payment_storage.create_payment_record(
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


async def handle_check_change_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, order_id: str):
    """Handle check_change_payment_ callback."""
    query = update.callback_query

    payment_record = app_context.payment_storage.get_payment_by_order(order_id)
    if not payment_record:
        await query.edit_message_text("❌ Платеж не найден")
        return

    if payment_record.get("status") == "completed":
        await query.edit_message_text(
            "✅ <b>Платеж уже обработан</b>\n\n"
            "Тариф изменен."
        )
        return

    payment_id = payment_record.get("payment_id")
    if not payment_id:
        await query.edit_message_text("❌ Ошибка: ID платежа не найден")
        return

    check_result = app_context.yookassa.check_payment(payment_id)

    if check_result.get("error"):
        await query.edit_message_text(
            f"❌ <b>Ошибка проверки</b>\n\n{check_result['error']}"
        )
        return

    status = check_result.get("status")
    paid = check_result.get("paid", False)

    if status == PAYMENT_STATUS_SUCCEEDED and paid:
        parts = order_id.split("_")
        if len(parts) >= 4:
            sub_id = int(parts[2])
            new_tariff_id = parts[3]
            new_tariff = TARIFFS.get(new_tariff_id)

            if new_tariff:
                app_context.payment_storage.update_payment_status(order_id, "completed", payment_id)
                await handle_tariff_change(update, user_id, sub_id, new_tariff_id, new_tariff)
            else:
                await query.edit_message_text("❌ Тариф не найден")
        else:
            await query.edit_message_text("❌ Ошибка данных заказа")
    elif status == PAYMENT_STATUS_CANCELLED:
        app_context.payment_storage.update_payment_status(order_id, "cancelled", payment_id)
        await query.edit_message_text(
            "❌ <b>Платеж отменен</b>\n\n"
            "Вы можете попробовать снова."
        )
    else:
        await query.answer("⏳ Платеж в обработке...")


async def handle_extend(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, sub_id: str):
    """Handle extend_ callback — create payment for subscription extension."""
    query = update.callback_query
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
        if not app_context.subscription_manager:
            await query.edit_message_text("❌ Сервис подписок недоступен")
            return

        # Check if YooKassa is available
        if not app_context.yookassa:
            await query.edit_message_text("❌ Платежная система недоступна")
            return

        # Create order_id with prefix "extend_"
        order_id = f"extend_{sid}_{uuid.uuid4().hex[:8]}"
        amount = tariff.get("price", 0)

        # Create payment
        payment_result = app_context.yookassa.create_payment(
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
        app_context.payment_storage.create_payment_record(
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