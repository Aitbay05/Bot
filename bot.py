"""
Обработчики Telegram-бота: команды /start, /help, /stats, /top5, /admin
и обработка сообщений, приходящих в виде скриншота + ФИО (в подписи).

Новая логика:
- Если на скриншоте указано количество пакетов:
    * если оно БОЛЬШЕ MIN_PACKAGES_FOR_AUTO_ACCEPT -> заказ принимается автоматически;
    * если оно РАВНО или МЕНЬШЕ этого числа -> заказ отправляется в чат
      диспетчера, и до тех пор, пока диспетчер не нажмёт кнопку "Принять" /
      "Вернуть", заказ остаётся в статусе "в ожидании".
- Если через команду /admin введены верные логин/пароль, этот чат
  регистрируется как чат диспетчера.
"""
from __future__ import annotations

import logging
import os
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database
import ocr
import google_sheet
from config import ADMIN_LOGIN, ADMIN_PASSWORD, BOT_TOKEN, MIN_PACKAGES_FOR_AUTO_ACCEPT
from utils import clean_employee_name, format_timestamp

logger = logging.getLogger(__name__)

# Состояния диалога (conversation) для /admin
ADMIN_LOGIN_STATE, ADMIN_PASSWORD_STATE = range(2)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Привет!\n\n"
        "Я — бот, который автоматически учитывает помощь, оказанную "
        "сотрудниками друг другу.\n\n"
        "📸 Отправьте скриншот заказа, а в подписи (caption) укажите "
        "ФИО сотрудника, который оказал помощь.\n\n"
        "Для получения дополнительной информации используйте команду /help."
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 Инструкция по использованию:\n\n"
        "1️⃣ Сделайте скриншот заказа.\n"
        "2️⃣ Отправьте скриншот боту.\n"
        "3️⃣ В подписи (caption) к скриншоту укажите ФИО сотрудника, "
        "который оказал помощь.\n\n"
        "Пример: Айтбай Рахымжан\n\n"
        f"📦 Если на скриншоте количество пакетов больше {MIN_PACKAGES_FOR_AUTO_ACCEPT}, "
        "бот автоматически зарегистрирует заказ в таблице и отправит диспетчеру уведомление. "
        f"Если количество пакетов меньше или равно {MIN_PACKAGES_FOR_AUTO_ACCEPT} — заказ будет отправлен "
        "диспетчеру и будет ждать его подтверждения.\n\n"
        "📊 Команды:\n"
        "/stats — рейтинг всех сотрудников\n"
        "/top5 — топ-5 сотрудников\n"
        "/pending — (только для диспетчера) список заказов в ожидании\n"
        "/admin — зарегистрироваться как диспетчер"
    )
    await update.message.reply_text(text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        employees = await google_sheet.get_all_employees()
    except Exception:
        logger.exception("Ошибка при получении данных из Google Таблицы")
        await update.message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
        return

    if not employees:
        await update.message.reply_text("Пока нет данных.")
        return

    employees.sort(key=lambda e: e["count"], reverse=True)
    lines = ["📊 Рейтинг сотрудников:\n"]
    for i, emp in enumerate(employees, start=1):
        lines.append(f"{i}. {emp['name']} — {emp['count']}")

    await update.message.reply_text("\n".join(lines))


async def top5_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        employees = await google_sheet.get_all_employees()
    except Exception:
        logger.exception("Ошибка при получении данных из Google Таблицы")
        await update.message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
        return

    employees.sort(key=lambda e: e["count"], reverse=True)
    top = employees[:5]

    if not top:
        await update.message.reply_text("Пока нет данных.")
        return

    lines = ["🏆 Топ-5 сотрудников:\n"]
    for i, emp in enumerate(top, start=1):
        lines.append(f"{i}. {emp['name']} — {emp['count']}")

    await update.message.reply_text("\n".join(lines))


# --- /admin: регистрация как диспетчер через логин/пароль ---

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not ADMIN_LOGIN or not ADMIN_PASSWORD:
        await update.message.reply_text(
            "⚠️ На сервере не установлены ADMIN_LOGIN/ADMIN_PASSWORD. "
            "Обратитесь к администратору."
        )
        return ConversationHandler.END

    await update.message.reply_text("🔐 Введите логин:")
    return ADMIN_LOGIN_STATE


async def admin_receive_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_login_attempt"] = update.message.text.strip()
    await update.message.reply_text("🔑 Введите пароль:")
    return ADMIN_PASSWORD_STATE


async def admin_receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    login_attempt = context.user_data.pop("admin_login_attempt", "")
    password_attempt = update.message.text.strip()

    if login_attempt == ADMIN_LOGIN and password_attempt == ADMIN_PASSWORD:
        await database.add_dispatcher(update.effective_chat.id, format_timestamp())
        await update.message.reply_text(
            "✅ Вы зарегистрированы как диспетчер.\n"
            f"Теперь заказы с количеством пакетов меньше/равным {MIN_PACKAGES_FOR_AUTO_ACCEPT} "
            "будут приходить в этот чат."
        )
    else:
        await update.message.reply_text("⛔ Неверный логин или пароль.")

    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("admin_login_attempt", None)
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


# --- Обработка скриншота ---

async def _notify_dispatchers(
    context: ContextTypes.DEFAULT_TYPE,
    order_number: str,
    employee_name: str,
    package_count: int | None,
) -> bool:
    """Отправляет заказ во все зарегистрированные чаты диспетчеров с кнопками Принять/Вернуть.

    Returns:
        True, если сообщение успешно отправлено хотя бы одному диспетчеру, иначе False.
    """
    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if not dispatcher_chat_ids:
        logger.warning(
            "Чат диспетчера не зарегистрирован — заказ №%s никому не отправлен. "
            "Нужно зарегистрироваться через команду /admin.",
            order_number,
        )
        return False

    package_text = package_count if package_count is not None else "неизвестно"
    text = (
        "🕐 Новый заказ ожидает подтверждения\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Количество пакетов: {package_text}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"approve:{order_number}"),
                InlineKeyboardButton("↩️ Вернуть", callback_data=f"reject:{order_number}"),
            ]
        ]
    )

    sent_to_at_least_one = False
    for chat_id in dispatcher_chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            sent_to_at_least_one = True
        except Exception:
            logger.exception("Ошибка при отправке сообщения диспетчеру (chat_id=%s)", chat_id)

    return sent_to_at_least_one


async def _notify_dispatchers_auto_warning(
    context: ContextTypes.DEFAULT_TYPE,
    order_number: str,
    employee_name: str,
    package_count: int | None,
) -> bool:
    """Үлкен заказ автоматты қабылданғаны туралы диспетчерге ескерту жібереді."""
    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if not dispatcher_chat_ids:
        logger.warning(
            "Диспетчер чаты тіркелмеген — автоматты қабылданған "
            "заказ №%s туралы ескерту жіберілмеді.",
            order_number,
        )
        return False

    text = (
        "🔔 ҮЛКЕН ЗАКАЗ — АВТОМАТТЫ ҚАБЫЛДАНДЫ\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Количество пакетов: {package_count}\n\n"
        "✅ Заказ автоматты түрде Google Таблицаға тіркелді.\n"
        "ℹ️ Диспетчердің қабылдау/қайтару батырмасын басуы қажет емес."
    )

    sent_to_at_least_one = False
    for chat_id in dispatcher_chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            sent_to_at_least_one = True
        except Exception:
            logger.exception(
                "Автоматты заказ туралы диспетчерге ескерту жіберу қатесі (chat_id=%s)",
                chat_id,
            )

    return sent_to_at_least_one


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выполняет основную логику при получении скриншота:
    OCR → проверка дубликата → (в зависимости от количества пакетов)
    автоматическое принятие или отправка диспетчеру.
    """
    message = update.message

    if not message.caption:
        await message.reply_text(
            "⚠️ Укажите в подписи к скриншоту ФИО сотрудника, который оказал помощь."
        )
        return

    employee_name = clean_employee_name(message.caption)
    if not employee_name:
        await message.reply_text("⚠️ ФИО указано неверно. Отправьте ещё раз.")
        return

    photo = message.photo[-1]  # самый большой размер
    tg_file = await context.bot.get_file(photo.file_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = os.path.join(tmp_dir, "screenshot.jpg")
        await tg_file.download_to_drive(image_path)

        try:
            order_number, package_count = await ocr.recognize_order_and_packages(image_path)
        except Exception:
            logger.exception("Ошибка во время OCR")
            await message.reply_text("⚠️ Заказ не распознан.")
            return

    if not order_number:
        await message.reply_text("⚠️ Номер заказа не распознан. Отправьте ещё раз.")
        return

    try:
        already_registered = await database.order_exists(order_number)
        already_pending = await database.pending_order_exists(order_number)
    except Exception:
        logger.exception("Ошибка при проверке базы данных")
        await message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
        return

    if already_registered:
        await message.reply_text("⚠️ Этот заказ уже был зарегистрирован (принят) ранее.")
        return

    if already_pending:
        await message.reply_text(
            "⏳ Этот заказ ещё рассматривается диспетчером. "
            "Повторно отправлять не нужно, подождите."
        )
        return

    # --- Решение принимается на основе количества пакетов ---
    needs_dispatcher_approval = (
        package_count is not None and package_count <= MIN_PACKAGES_FOR_AUTO_ACCEPT
    )

    if needs_dispatcher_approval:
        try:
            await database.save_pending_order(
                order_number, employee_name, message.chat_id, package_count, format_timestamp()
            )
        except Exception:
            logger.exception("Ошибка при сохранении заказа в ожидании")
            await message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
            return

        await message.reply_text(
            "⏳ Заказ отправлен диспетчеру, ожидается подтверждение.\n\n"
            f"📦 Заказ №{order_number}\n"
            f"📦 Количество пакетов: {package_count}"
        )
        sent = await _notify_dispatchers(context, order_number, employee_name, package_count)
        if not sent:
            await message.reply_text(
                "⚠️ Внимание: сейчас нет зарегистрированного диспетчера, поэтому "
                "этот заказ никому не виден. После регистрации диспетчера через "
                "команду /admin, он сможет увидеть заказы в ожидании командой /pending."
            )
        return

    # --- Автоматическое принятие ---
    try:
        total_count = await google_sheet.add_help_record(employee_name, order_number)
        await database.save_order(order_number, employee_name, format_timestamp())
    except Exception:
        logger.exception("Ошибка при обновлении базы данных/Google Таблицы")
        await message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
        return

    # Заказы больше 5 пакетов автоматически принимаются,
    # но диспетчер получает уведомление для контроля.
    if package_count is not None and package_count > MIN_PACKAGES_FOR_AUTO_ACCEPT:
        await _notify_dispatchers_auto_warning(
            context,
            order_number,
            employee_name,
            package_count,
        )

    reply = (
        "✅ Помощь зарегистрирована\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Количество пакетов: {package_count if package_count is not None else 'неизвестно'}\n"
        f"📊 Общее количество оказанной помощи: {total_count}"
    )
    await message.reply_text(reply)

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выход из режима диспетчера."""
    chat_id = update.effective_chat.id

    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if chat_id not in dispatcher_chat_ids:
        await update.message.reply_text(
            "ℹ️ Сейчас вы не зарегистрированы как диспетчер."
        )
        return

    await database.remove_dispatcher(chat_id)

    await update.message.reply_text(
        "🚪 Вы вышли из режима диспетчера.\n\n"
        "Чтобы войти снова, используйте команду /admin."
    )

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает диспетчеру все заказы в ожидании с кнопками Принять/Вернуть.

    Эта команда работает только в зарегистрированных чатах диспетчеров —
    сначала нужно зарегистрироваться через /admin.
    """
    chat_id = update.effective_chat.id
    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if chat_id not in dispatcher_chat_ids:
        await update.message.reply_text(
            "⛔ Эта команда доступна только зарегистрированным диспетчерам.\n"
            "Сначала зарегистрируйтесь через команду /admin."
        )
        return

    pending_orders = await database.get_all_pending_orders()

    if not pending_orders:
        await update.message.reply_text("✅ Сейчас нет заказов в ожидании.")
        return

    await update.message.reply_text(f"🕐 Заказов в ожидании: {len(pending_orders)}")

    for order in pending_orders:
        package_text = order["package_count"] if order["package_count"] is not None else "неизвестно"
        text = (
            "🕐 Заказ ожидает подтверждения\n\n"
            f"👤 {order['employee_name']}\n"
            f"📦 Заказ №{order['order_number']}\n"
            f"📦 Количество пакетов: {package_text}\n"
            f"🕓 Время отправки: {order['created_at']}"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Принять", callback_data=f"approve:{order['order_number']}"
                    ),
                    InlineKeyboardButton(
                        "↩️ Вернуть", callback_data=f"reject:{order['order_number']}"
                    ),
                ]
            ]
        )
        await update.message.reply_text(text, reply_markup=keyboard)


async def dispatcher_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вызывается, когда диспетчер нажимает кнопку "Принять" или "Вернуть"."""
    query = update.callback_query
    await query.answer()

    try:
        action, order_number = query.data.split(":", 1)
    except (ValueError, AttributeError):
        logger.warning("Некорректный callback_data: %r", query.data)
        return

    pending = await database.get_pending_order(order_number)

    if not pending or pending["status"] != "pending":
        await query.edit_message_text("⚠️ Этот заказ уже обработан ранее или не найден.")
        return

    employee_name = pending["employee_name"]
    employee_chat_id = pending["employee_chat_id"]

    if action == "approve":
        try:
            total_count = await google_sheet.add_help_record(employee_name, order_number)
            await database.save_order(order_number, employee_name, format_timestamp())
            await database.update_pending_order_status(order_number, "accepted")
        except Exception:
            logger.exception("Ошибка при принятии заказа")
            await query.edit_message_text("⚠️ Ошибка сервера. Попробуйте позже.")
            return

        await query.edit_message_text(
            "✅ Заказ принят\n\n"
            f"👤 {employee_name}\n"
            f"📦 Заказ №{order_number}"
        )
        try:
            await context.bot.send_message(
                chat_id=employee_chat_id,
                text=(
                    f"✅ Ваш заказ №{order_number} принят диспетчером!\n"
                    f"📊 Общее количество оказанной помощи: {total_count}"
                ),
            )
        except Exception:
            logger.exception("Ошибка при отправке сообщения сотруднику")

    elif action == "reject":
        try:
            await database.update_pending_order_status(order_number, "rejected")
        except Exception:
            logger.exception("Ошибка при возврате заказа")
            await query.edit_message_text("⚠️ Ошибка сервера. Попробуйте позже.")
            return

        await query.edit_message_text(
            "↩️ Заказ возвращён\n\n"
            f"👤 {employee_name}\n"
            f"📦 Заказ №{order_number}"
        )
        try:
            await context.bot.send_message(
                chat_id=employee_chat_id,
                text=(
                    f"↩️ Ваш заказ №{order_number} возвращён диспетчером. "
                    "Проверьте ещё раз и при необходимости отправьте заново."
                ),
            )
        except Exception:
            logger.exception("Ошибка при отправке сообщения сотруднику")

    else:
        logger.warning("Неизвестное действие в callback_data: %r", action)


async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ответ на сообщения, отличные от фото."""
    await update.message.reply_text(
        "📸 Отправьте скриншот заказа вместе с ФИО в подписи."
    )


async def _post_init(application: Application) -> None:
    """Вызывается один раз при запуске Application (в собственном event loop PTB).

    Здесь готовим файл базы данных и все необходимые таблицы (orders,
    pending_orders, dispatchers). Поскольку используется
    CREATE TABLE IF NOT EXISTS, существующим данным (например, таблице
    orders) не наносится никакого вреда — добавляются только
    недостающие таблицы.
    """
    await database.init_db()


def build_application() -> Application:
    """Создаёт объект Telegram Application и регистрирует все обработчики."""
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("top5", top5_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("logout", logout_command))

    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_LOGIN_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_login)
            ],
            ADMIN_PASSWORD_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
    )
    # Важно зарегистрировать admin conversation в начале списка —
    # иначе сообщения с логином/паролем попадут в обработчик "unsupported".
    application.add_handler(admin_conv_handler)

    application.add_handler(
        CallbackQueryHandler(dispatcher_decision_callback, pattern=r"^(approve|reject):")
    )

    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(
        MessageHandler(~filters.PHOTO & ~filters.COMMAND, handle_unsupported)
    )

    return application
