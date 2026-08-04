"""
Telegram bot handlerлері: /start, /help, /stats, /top5 командалары
және скриншот + аты-жөн (caption) арқылы келетін хабарламаны өңдеу.
"""
from __future__ import annotations

import logging
import os
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database
import ocr
import google_sheet as excel_sheet  # Google Sheets модулі, интерфейсі бұрынғыдай
from config import BOT_TOKEN
from utils import clean_employee_name, format_timestamp

logger = logging.getLogger(__name__)


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
        "Бот автоматты түрде заказ нөмірін танып, Google Sheets-ке жазады.\n\n"
        "📊 Командалар:\n"
        "/stats — барлық қызметкерлердің рейтингі\n"
        "/top5 — үздік 5 қызметкер"
    )
    await update.message.reply_text(text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        employees = await excel_sheet.get_all_employees()
    except Exception:
        logger.exception("Google Sheets-тен деректерді алу кезінде қате")
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
        employees = await excel_sheet.get_all_employees()
    except Exception:
        logger.exception("Google Sheets-тен деректерді алу кезінде қате")
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


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Скриншот келгенде негізгі логиканы орындайды: OCR → дубликат тексеру → Google Sheets жазу."""
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
            order_number = await ocr.recognize_order_number(image_path)
        except Exception:
            logger.exception("OCR кезінде қате шықты")
            await message.reply_text("⚠️ Заказ анықталмады.")
            return

    if not order_number:
        await message.reply_text("⚠️ Заказ нөмірі анықталмады. Қайта жіберіңіз.")
        return

    try:
        if await database.order_exists(order_number):
            await message.reply_text("⚠️ Бұл заказ бұрын тіркелген.")
            return

        total_count = await excel_sheet.add_help_record(employee_name, order_number)
        await database.save_order(order_number, employee_name, format_timestamp())

    except Exception:
        logger.exception("Дерекқор/Google Sheets жаңарту кезінде қате")
        await message.reply_text("⚠️ Сервер қатесі. Кейінірек қайталап көріңіз.")
        return

    reply = (
        "✅ Көмек тіркелді\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📊 Жалпы көмек саны: {total_count}"
    )
    await message.reply_text(reply)


async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фото емес, басқа хабарлама түрлеріне жауап."""
    await update.message.reply_text(
        "📸 Заказдың скриншотын, астына аты-жөнмен бірге жіберіңіз."
    )


def build_application() -> Application:
    """Telegram Application объектісін жасап, барлық handlerлерді тіркейді."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("top5", top5_command))

    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(
        MessageHandler(~filters.PHOTO & ~filters.COMMAND, handle_unsupported)
    )

    return application
