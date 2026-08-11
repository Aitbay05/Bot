"""
Telegram bot handlerлері: /start, /help, /stats, /top5, /admin командалары
және скриншот + аты-жөн (caption) арқылы келетін хабарламаны өңдеу.

Жаңа логика:
- Скриншотта пакет саны көрсетілген болса:
    * MIN_PACKAGES_FOR_AUTO_ACCEPT-тен КӨП болса -> автоматты қабылданады.
    * Сол санға ТЕҢ немесе одан АЗ болса -> диспетчер чатына жіберіледі,
      диспетчер "Қабылдау" / "Қайтару" батырмасын басқанша тапсырыс
      "күтуде" статусында тұрады.
- /admin командасы арқылы логин/пароль дұрыс енгізілсе, сол чат
  диспетчер чаты ретінде тіркеледі.
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

# /admin әңгіме (conversation) күйлері
ADMIN_LOGIN_STATE, ADMIN_PASSWORD_STATE = range(2)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Сәлем!\n\n"
        "Мен — қызметкерлердің бір-біріне көрсеткен көмегін автоматты түрде "
        "есептейтін бот.\n\n"
        "📸 Заказдың скриншотын жіберіп, астына (caption) көмек көрсеткен "
        "қызметкердің аты-жөнін жазыңыз.\n\n"
        "Қосымша ақпарат үшін /help командасын қолданыңыз."
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 Қолдану нұсқаулығы:\n\n"
        "1️⃣ Заказдың скриншотын түсіріңіз.\n"
        "2️⃣ Скриншотты ботқа жіберіңіз.\n"
        "3️⃣ Скриншоттың астына (caption) көмек көрсеткен қызметкердің "
        "аты-жөнін жазыңыз.\n\n"
        "Мысалы: Айтбай Рахымжан\n\n"
        f"📦 Егер скриншотта пакет саны {MIN_PACKAGES_FOR_AUTO_ACCEPT}-тен көп "
        "болса, бот автоматты қабылдайды. Аз болса, тапсырыс диспетчерге "
        "жіберіліп, қабылдауын күтеді.\n\n"
        "📊 Командалар:\n"
        "/stats — барлық қызметкерлердің рейтингі\n"
        "/top5 — үздік 5 қызметкер\n"
        "/pending — (тек диспетчерге) күтудегі тапсырыстар тізімі\n"
        "/admin — диспетчер ретінде тіркелу"
    )
    await update.message.reply_text(text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        employees = await google_sheet.get_all_employees()
    except Exception:
        logger.exception("Google Таблицадан деректерді алу кезінде қате")
        await update.message.reply_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
        return

    if not employees:
        await update.message.reply_text("Әзірге мәліметтер жоқ.")
        return

    employees.sort(key=lambda e: e["count"], reverse=True)
    lines = ["📊 Қызметкерлер рейтингі:\n"]
    for i, emp in enumerate(employees, start=1):
        lines.append(f"{i}. {emp['name']} — {emp['count']}")

    await update.message.reply_text("\n".join(lines))


async def top5_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        employees = await google_sheet.get_all_employees()
    except Exception:
        logger.exception("Google Таблицадан деректерді алу кезінде қате")
        await update.message.reply_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
        return

    employees.sort(key=lambda e: e["count"], reverse=True)
    top = employees[:5]

    if not top:
        await update.message.reply_text("Әзірге мәліметтер жоқ.")
        return

    lines = ["🏆 Үздік 5 қызметкер:\n"]
    for i, emp in enumerate(top, start=1):
        lines.append(f"{i}. {emp['name']} — {emp['count']}")

    await update.message.reply_text("\n".join(lines))


# --- /admin: диспетчер ретінде логин/пароль арқылы тіркелу ---

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not ADMIN_LOGIN or not ADMIN_PASSWORD:
        await update.message.reply_text(
            "⚠️ Сервер жағында ADMIN_LOGIN/ADMIN_PASSWORD орнатылмаған. "
            "Администраторға хабарласыңыз."
        )
        return ConversationHandler.END

    await update.message.reply_text("🔐 Логинді енгізіңіз:")
    return ADMIN_LOGIN_STATE


async def admin_receive_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_login_attempt"] = update.message.text.strip()
    await update.message.reply_text("🔑 Парольді енгізіңіз:")
    return ADMIN_PASSWORD_STATE


async def admin_receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    login_attempt = context.user_data.pop("admin_login_attempt", "")
    password_attempt = update.message.text.strip()

    if login_attempt == ADMIN_LOGIN and password_attempt == ADMIN_PASSWORD:
        await database.add_dispatcher(update.effective_chat.id, format_timestamp())
        await update.message.reply_text(
            "✅ Сіз диспетчер ретінде тіркелдіңіз.\n"
            f"Енді {MIN_PACKAGES_FOR_AUTO_ACCEPT}-тен аз/тең пакетті тапсырыстар "
            "осы чатқа келіп тұрады."
        )
    else:
        await update.message.reply_text("⛔ Логин немесе пароль қате.")

    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("admin_login_attempt", None)
    await update.message.reply_text("Бас тартылды.")
    return ConversationHandler.END


# --- Скриншот өңдеу ---

async def _notify_dispatchers(
    context: ContextTypes.DEFAULT_TYPE,
    order_number: str,
    employee_name: str,
    package_count: int | None,
) -> bool:
    """Барлық тіркелген диспетчер чаттарына тапсырысты Қабылдау/Қайтару батырмаларымен жібереді.

    Returns:
        Кем дегенде бір диспетчерге хабарлама сәтті жіберілсе True, әйтпесе False.
    """
    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if not dispatcher_chat_ids:
        logger.warning(
            "Диспетчер чаты тіркелмеген — тапсырыс №%s ешкімге жіберілмеді. "
            "/admin командасы арқылы тіркеу керек.",
            order_number,
        )
        return False

    package_text = package_count if package_count is not None else "белгісіз"
    text = (
        "🕐 Жаңа тапсырыс қабылдауды күтуде\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Пакет саны: {package_text}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Қабылдау", callback_data=f"approve:{order_number}"),
                InlineKeyboardButton("↩️ Қайтару", callback_data=f"reject:{order_number}"),
            ]
        ]
    )

    sent_to_at_least_one = False
    for chat_id in dispatcher_chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            sent_to_at_least_one = True
        except Exception:
            logger.exception("Диспетчерге хабарлама жіберу кезінде қате (chat_id=%s)", chat_id)

    return sent_to_at_least_one


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Скриншот келгенде негізгі логиканы орындайды:
    OCR → дубликат тексеру → (пакет санына қарай) автоматты қабылдау
    немесе диспетчерге жіберу.
    """
    message = update.message

    if not message.caption:
        await message.reply_text(
            "⚠️ Скриншоттың астына көмек көрсеткен қызметкердің аты-жөнін жазыңыз."
        )
        return

    employee_name = clean_employee_name(message.caption)
    if not employee_name:
        await message.reply_text("⚠️ Аты-жөн дұрыс жазылмады. Қайта жіберіңіз.")
        return

    photo = message.photo[-1]  # ең үлкен өлшемдісі
    tg_file = await context.bot.get_file(photo.file_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = os.path.join(tmp_dir, "screenshot.jpg")
        await tg_file.download_to_drive(image_path)

        try:
            order_number, package_count = await ocr.recognize_order_and_packages(image_path)
        except Exception:
            logger.exception("OCR кезінде қате шықты")
            await message.reply_text("⚠️ Заказ анықталмады.")
            return

    if not order_number:
        await message.reply_text("⚠️ Заказ нөмірі анықталмады. Қайта жіберіңіз.")
        return

    try:
        already_registered = await database.order_exists(order_number)
        already_pending = await database.pending_order_exists(order_number)
    except Exception:
        logger.exception("Дерекқорды тексеру кезінде қате")
        await message.reply_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
        return

    if already_registered:
        await message.reply_text("⚠️ Бұл заказ бұрын тіркелген (қабылданған).")
        return

    if already_pending:
        await message.reply_text(
            "⏳ Бұл тапсырыс әлі диспетчерде қаралу үстінде. "
            "Қайта жіберудің қажеті жоқ, күте тұрыңыз."
        )
        return

    # --- Пакет саны шешім қабылдайды ---
    needs_dispatcher_approval = (
        package_count is not None and package_count <= MIN_PACKAGES_FOR_AUTO_ACCEPT
    )

    if needs_dispatcher_approval:
        try:
            await database.save_pending_order(
                order_number, employee_name, message.chat_id, package_count, format_timestamp()
            )
        except Exception:
            logger.exception("Pending тапсырысты сақтау кезінде қате")
            await message.reply_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
            return

        await message.reply_text(
            "⏳ Тапсырыс диспетчерге жіберілді, қабылдау күтілуде.\n\n"
            f"📦 Заказ №{order_number}\n"
            f"📦 Пакет саны: {package_count}"
        )
        sent = await _notify_dispatchers(context, order_number, employee_name, package_count)
        if not sent:
            await message.reply_text(
                "⚠️ Ескерту: қазір тіркелген диспетчер жоқ, сондықтан бұл тапсырыс "
                "ешкімге көрінбей тұр. Диспетчер /admin командасы арқылы тіркелгеннен "
                "кейін /pending командасымен күтудегі тапсырыстарды көре алады."
            )
        return

    # --- Автоматты қабылдау (пакет саны жеткілікті немесе анықталмаған) ---
    try:
        total_count = await google_sheet.add_help_record(employee_name, order_number)
        await database.save_order(order_number, employee_name, format_timestamp())
    except Exception:
        logger.exception("Дерекқор/Google Таблица жаңарту кезінде қате")
        await message.reply_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
        return

    reply = (
        "✅ Көмек тіркелді\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📊 Жалпы көмек саны: {total_count}"
    )
    await message.reply_text(reply)

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Диспетчер режимінен шығу."""
    chat_id = update.effective_chat.id

    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if chat_id not in dispatcher_chat_ids:
        await update.message.reply_text(
            "ℹ️ Сіз қазір диспетчер ретінде тіркелмегенсіз."
        )
        return

    await database.remove_dispatcher(chat_id)

    await update.message.reply_text(
        "🚪 Диспетчер режимінен шықтыңыз.\n\n"
        "Қайта кіру үшін /admin командасын пайдаланыңыз."
    )

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Диспетчерге күтудегі барлық тапсырыстарды Қабылдау/Қайтару батырмаларымен көрсетеді.

    Бұл команда тек тіркелген диспетчер чаттарында ғана жұмыс істейді —
    /admin арқылы алдымен тіркелу керек.
    """
    chat_id = update.effective_chat.id
    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if chat_id not in dispatcher_chat_ids:
        await update.message.reply_text(
            "⛔ Бұл команда тек тіркелген диспетчерлерге қолжетімді.\n"
            "Алдымен /admin командасы арқылы тіркеліңіз."
        )
        return

    pending_orders = await database.get_all_pending_orders()

    if not pending_orders:
        await update.message.reply_text("✅ Қазір күтудегі тапсырыс жоқ.")
        return

    await update.message.reply_text(f"🕐 Күтудегі тапсырыстар: {len(pending_orders)}")

    for order in pending_orders:
        package_text = order["package_count"] if order["package_count"] is not None else "белгісіз"
        text = (
            "🕐 Тапсырыс қабылдауды күтуде\n\n"
            f"👤 {order['employee_name']}\n"
            f"📦 Заказ №{order['order_number']}\n"
            f"📦 Пакет саны: {package_text}\n"
            f"🕓 Жіберілген уақыты: {order['created_at']}"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Қабылдау", callback_data=f"approve:{order['order_number']}"
                    ),
                    InlineKeyboardButton(
                        "↩️ Қайтару", callback_data=f"reject:{order['order_number']}"
                    ),
                ]
            ]
        )
        await update.message.reply_text(text, reply_markup=keyboard)


async def dispatcher_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Диспетчер "Қабылдау" немесе "Қайтару" батырмасын басқанда шақырылады."""
    query = update.callback_query
    await query.answer()

    try:
        action, order_number = query.data.split(":", 1)
    except (ValueError, AttributeError):
        logger.warning("Дұрыс емес callback_data: %r", query.data)
        return

    pending = await database.get_pending_order(order_number)

    if not pending or pending["status"] != "pending":
        await query.edit_message_text("⚠️ Бұл тапсырыс бұрын өңделген немесе табылмады.")
        return

    employee_name = pending["employee_name"]
    employee_chat_id = pending["employee_chat_id"]

    if action == "approve":
        try:
            total_count = await google_sheet.add_help_record(employee_name, order_number)
            await database.save_order(order_number, employee_name, format_timestamp())
            await database.update_pending_order_status(order_number, "accepted")
        except Exception:
            logger.exception("Тапсырысты қабылдау кезінде қате")
            await query.edit_message_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
            return

        await query.edit_message_text(
            "✅ Тапсырыс қабылданды\n\n"
            f"👤 {employee_name}\n"
            f"📦 Заказ №{order_number}"
        )
        try:
            await context.bot.send_message(
                chat_id=employee_chat_id,
                text=(
                    f"✅ Сіздің №{order_number} тапсырысыңыз диспетчер тарапынан "
                    "қабылданды!\n"
                    f"📊 Жалпы көмек саны: {total_count}"
                ),
            )
        except Exception:
            logger.exception("Қызметкерге хабарлама жіберу кезінде қате")

    elif action == "reject":
        try:
            await database.update_pending_order_status(order_number, "rejected")
        except Exception:
            logger.exception("Тапсырысты қайтару кезінде қате")
            await query.edit_message_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
            return

        await query.edit_message_text(
            "↩️ Тапсырыс қайтарылды\n\n"
            f"👤 {employee_name}\n"
            f"📦 Заказ №{order_number}"
        )
        try:
            await context.bot.send_message(
                chat_id=employee_chat_id,
                text=(
                    f"↩️ Сіздің №{order_number} тапсырысыңыз диспетчер тарапынан "
                    "қайтарылды. Қайта тексеріп, қажет болса қайта жіберіңіз."
                ),
            )
        except Exception:
            logger.exception("Қызметкерге хабарлама жіберу кезінде қате")

    else:
        logger.warning("Белгісіз әрекет callback_data ішінде: %r", action)


async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фото емес, басқа хабарлама түрлеріне жауап."""
    await update.message.reply_text(
        "📸 Заказдың скриншотын, астына аты-жөнмен бірге жіберіңіз."
    )


async def _post_init(application: Application) -> None:
    """Application іске қосылғанда (PTB-дің өз event loop-ында) бір рет шақырылады.

    Дерекқор файлы мен барлық керек кестелерді (orders, pending_orders,
    dispatchers) осы жерде дайындаймыз. CREATE TABLE IF NOT EXISTS
    қолданылатындықтан, бар деректерге (мысалы, orders кестесіне) ешқандай
    зиян келмейді — тек жетіспейтін кестелер қосылады.
    """
    await database.init_db()


def build_application() -> Application:
    """Telegram Application объектісін жасап, барлық handlerлерді тіркейді."""
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
    # Admin conversation-ды каталогтың басында тіркеу маңызды —
    # солай логин/пароль хабарламалары "unsupported" handler-іне
    # түсіп қалмайды.
    application.add_handler(admin_conv_handler)

    application.add_handler(
        CallbackQueryHandler(dispatcher_decision_callback, pattern=r"^(approve|reject):")
    )

    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(
        MessageHandler(~filters.PHOTO & ~filters.COMMAND, handle_unsupported)
    )

    return application
