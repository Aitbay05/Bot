"""
Обработчики Telegram-бота: команды /start, /help, /stats, /top5, /admin, /myid
и обработка сообщений, приходящих в виде скриншота + ФИО (в подписи).

Логика:
- Если на скриншоте указано количество пакетов:
    * если оно БОЛЬШЕ MIN_PACKAGES_FOR_AUTO_ACCEPT -> заказ принимается автоматически;
    * если оно РАВНО или МЕНЬШЕ этого числа -> заказ отправляется в чат
      диспетчера, и до тех пор, пока диспетчер не нажмёт кнопку "Принять" /
      "Вернуть", заказ остаётся в статусе "в ожидании".
    * если количество пакетов НЕ распознано (None) -> заказ ТАКЖЕ
      отправляется диспетчеру (безопасный дефолт), а не принимается
      автоматически "втихую". Раньше нераспознанный package_count
      приводил к автоматическому принятию без единого уведомления
      диспетчеру — это была логическая ошибка (см. AUDIT_REPORT.md,
      пункт Critical/1).
- Если chat_id пользователя есть в списке ADMIN_CHAT_IDS (.env), этот чат
  регистрируется как чат диспетчера через команду /admin (без пароля —
  chat_id нельзя подделать). Узнать свой chat_id можно командой /myid.
  Неограниченное количество попыток подряд запрещено простым
  in-memory ограничителем (см. _admin_attempts).
- Кнопки "Принять"/"Вернуть" обрабатываются только если чат, откуда
  пришёл callback, зарегистрирован как диспетчер — иначе запрос
  игнорируется (авторизация).
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden as TelegramForbidden
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database
import ocr
import google_sheet
import monitoring
from config import ADMIN_CHAT_IDS, BOT_TOKEN, MIN_PACKAGES_FOR_AUTO_ACCEPT
from database import DuplicateOrderError
from utils import clean_employee_name, format_timestamp

logger = logging.getLogger(__name__)

# --- Простая защита от спама /admin со стороны неавторизованных чатов ---
# Не персистентная (сбрасывается при рестарте бота), но останавливает
# автоматизированный перебор в рамках одной "жизни" процесса.
_ADMIN_MAX_ATTEMPTS = 5
_ADMIN_COOLDOWN_SECONDS = 15 * 60  # 15 минут
_admin_attempts: dict[int, list[float]] = defaultdict(list)


def _is_rate_limited(chat_id: int) -> bool:
    now = time.monotonic()
    attempts = _admin_attempts[chat_id]
    # Тек соңғы cooldown уақыты ішіндегі әрекеттерді сақтаймыз
    attempts[:] = [t for t in attempts if now - t < _ADMIN_COOLDOWN_SECONDS]
    return len(attempts) >= _ADMIN_MAX_ATTEMPTS


def _register_attempt(chat_id: int) -> None:
    _admin_attempts[chat_id].append(time.monotonic())


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
        f"Если количество пакетов меньше или равно {MIN_PACKAGES_FOR_AUTO_ACCEPT}, а также если "
        "количество пакетов не удалось распознать — заказ будет отправлен "
        "диспетчеру и будет ждать его подтверждения.\n\n"
        "📊 Команды:\n"
        "/stats — рейтинг всех сотрудников\n"
        "/top5 — топ-5 сотрудников\n"
        "/pending — (только для диспетчера) список заказов в ожидании\n"
        "/admin — зарегистрироваться как диспетчер\n"
        "/myid — узнать свой chat_id (для регистрации диспетчером)"
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


# --- /myid: пайдаланушыға өз chat_id-ін көрсету (диспетчер тіркеу үшін) ---

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    username_line = f"\n👤 Username: @{user.username}" if user and user.username else ""

    # Ескерту: бұрын мұнда parse_mode="Markdown" қолданылған еді, бірақ
    # мәтінде "chat_id", "ADMIN_CHAT_IDS" сияқты асты сызықтары (_) көп
    # сөздер бар — Telegram-ның ескі Markdown парсері оларды курсив
    # ашушы/жабушы белгі деп қате түсініп, "Can't parse entities" қатесін
    # берген (production логта расталды). Бұл жай ақпараттық хабарлама
    # болғандықтан, формат күрделі емес, сондықтан parse_mode мүлде
    # алынып тасталды — қарапайым мәтін ешқашан осы қатеге ұшырамайды.
    await update.message.reply_text(
        f"🆔 Сіздің chat_id: {chat_id}{username_line}\n\n"
        "Диспетчер болу үшін бұл нөмірді серверде .env файлындағы "
        "ADMIN_CHAT_IDS айнымалысына (үтірмен бөліп) қосу керек, "
        "содан кейін /admin командасын жіберіңіз."
    )


# --- /admin: диспетчер ретінде тіркелу (chat_id whitelist арқылы, парольсіз) ---
#
# Неге пароль емес, chat_id: Telegram chat_id-ды ешкім жалғандай ала
# алмайды — ол хабарламаны шын жіберген адамға Telegram сервері
# тарапынан белгіленеді. Сондықтан бұл әдіс парольге қарағанда
# қауіпсіз әрі brute-force/фишингке осал емес (жасырын құпия сөзді
# ешкім "болжап табуы" немесе ұрлауы мүмкін емес).

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    # Диспетчерді ТЕК жеке (private) чатта тіркейміз. Себебі: авторизация
    # chat_id бойынша тексеріледі (database.is_dispatcher(chat_id)), ал
    # топтық/канал чатында chat_id сол топтың бүкіл мүшелеріне ортақ —
    # яғни топта кез келген адам "Принять"/"Вернуть" батырмасын баса алар
    # еді, тіпті ол ADMIN_CHAT_IDS-те жоқ болса да. Жеке чатта chat_id
    # әрдайым сол нақты адамның Telegram ID-іне тең болғандықтан, бұл
    # шектеу осы тарапты толық жабады.
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "⛔ Диспетчер ретінде тек жеке чатта (боттың өзіне) тіркеле аласыз. "
            "Топтық чатта емес — ботқа жеке хабарласып, осы жерде /admin жіберіңіз."
        )
        return

    if not ADMIN_CHAT_IDS:
        await update.message.reply_text(
            "⚠️ На сервере не настроен ADMIN_CHAT_IDS. Обратитесь к администратору."
        )
        return

    if _is_rate_limited(chat_id):
        logger.warning("Слишком много попыток /admin из чата %s", chat_id)
        await update.message.reply_text(
            "⛔ Слишком много попыток. Попробуйте позже."
        )
        return

    if chat_id not in ADMIN_CHAT_IDS:
        _register_attempt(chat_id)
        logger.warning(
            "Неавторизованная попытка /admin из чата %s (не в ADMIN_CHAT_IDS)", chat_id
        )
        await update.message.reply_text(
            "⛔ У вас нет прав на регистрацию как диспетчер.\n\n"
            "Свой chat_id можно узнать командой /myid — передайте его "
            "администратору проекта, чтобы он добавил вас в ADMIN_CHAT_IDS."
        )
        return

    await database.add_dispatcher(chat_id, format_timestamp())
    await update.message.reply_text(
        "✅ Вы зарегистрированы как диспетчер.\n"
        f"Теперь заказы с количеством пакетов меньше/равным {MIN_PACKAGES_FOR_AUTO_ACCEPT} "
        "будут приходить в этот чат."
    )



# --- Обработка скриншота ---

async def _notify_dispatchers(
    context: ContextTypes.DEFAULT_TYPE,
    order_number: str,
    employee_name: str,
    package_count: int | None,
    order_number_confident: bool = True,
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

    package_text = package_count if package_count is not None else "не распознано"
    confidence_note = (
        "\n\n⚠️ Номер заказа распознан с низкой уверенностью (не найдено рядом "
        "со словом «заказ»/«№»/«#») — пожалуйста, сверьте номер со скриншотом вручную."
        if not order_number_confident
        else ""
    )
    text = (
        "🕐 Новый заказ ожидает подтверждения\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Количество пакетов: {package_text}"
        f"{confidence_note}"
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
        except TelegramForbidden:
            # Диспетчер ботты бұғаттаған немесе чатты өшірген — оны
            # диспетчерлер тізімінен автоматты алып тастаймыз, әйтпесе
            # әрбір жаңа заказда осы қате қайталана береді (толық
            # traceback логты былғайды, ал хабарлама іс жүзінде ешқашан
            # жетпейді). Ескерту деңгейінде қысқаша жазамыз.
            logger.warning(
                "Диспетчер (chat_id=%s) ботты бұғаттаған — тізімнен автоматты өшірілді",
                chat_id,
            )
            await database.remove_dispatcher(chat_id)
        except Exception:
            logger.exception("Ошибка при отправке сообщения диспетчеру (chat_id=%s)", chat_id)

    return sent_to_at_least_one


async def _notify_dispatchers_auto_warning(
    context: ContextTypes.DEFAULT_TYPE,
    order_number: str,
    employee_name: str,
    package_count: int | None,
) -> bool:
    """Отправляет уведомление диспетчеру о автоматически принятом большом заказе."""
    dispatcher_chat_ids = await database.get_dispatcher_chat_ids()

    if not dispatcher_chat_ids:
        logger.warning(
            "Чат диспетчера не зарегистрирован — уведомление "
            "об автоматически принятом заказе №%s не отправлено.",
            order_number,
        )
        return False

    text = (
        "🔔 БОЛЬШОЙ ЗАКАЗ — АВТОМАТИЧЕСКИ ПРИНЯТ\n\n"
        f"👤 Сотрудник: {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Количество пакетов: {package_count}\n\n"
        "✅ Заказ автоматически зарегистрирован в Google Таблице.\n"
        "ℹ️ Диспетчеру не нужно нажимать кнопки «Принять» / «Вернуть»."
    )

    sent_to_at_least_one = False
    for chat_id in dispatcher_chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            sent_to_at_least_one = True
        except TelegramForbidden:
            logger.warning(
                "Диспетчер (chat_id=%s) ботты бұғаттаған — тізімнен автоматты өшірілді",
                chat_id,
            )
            await database.remove_dispatcher(chat_id)
        except Exception:
            logger.exception(
                "Ошибка при отправке уведомления диспетчеру о автоматически принятом заказе (chat_id=%s)",
                chat_id,
            )

    return sent_to_at_least_one


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выполняет основную логику при получении скриншота:
    OCR → проверка дубликата → (в зависимости от количества пакетов)
    автоматическое принятие или отправка диспетчеру.
    """
    message = update.message
    if message is None:
        # Production логта расталған қате: Telegram edited_message/channel_post
        # сияқты update түрлерінде update.message = None болады, бірақ handler
        # осы функцияға сол update-ті де жіберуі мүмкін еді (filters.PHOTO
        # жаңа/өңделген хабарламаны ажыратпайды). Енді handler тіркеуінде
        # filters.UpdateType.MESSAGE қосылды (тек жаңа хабарлама), бірақ осы
        # жерде де қосымша сақтық ретінде тексереміз — бұл OCR қайта
        # іске қосылмауын, демек сол заказдың қайта өңделмеуін қамтамасыз етеді.
        return

    if not message.caption:
        await message.reply_text(
            "⚠️ Укажите в подписи к скриншоту ФИО сотрудника, который оказал помощь."
        )
        return

    employee_name = clean_employee_name(message.caption)
    if not employee_name:
        await message.reply_text("⚠️ ФИО указано неверно. Отправьте ещё раз.")
        return
    if len(employee_name) > 200:
        # Кездейсоқ немесе әдейі жіберілген өте ұзын caption-ды
        # деректер қорына жазбас бұрын кесіп тастаймыз.
        await message.reply_text("⚠️ ФИО слишком длинное. Проверьте подпись и отправьте ещё раз.")
        return

    photo = message.photo[-1]  # самый большой размер
    tg_file = await context.bot.get_file(photo.file_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = os.path.join(tmp_dir, "screenshot.jpg")
        await tg_file.download_to_drive(image_path)

        try:
            order_number, package_count, order_number_confident = (
                await ocr.recognize_order_and_packages(image_path)
            )
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

    # --- Решение принимается на основе количества пакетов И уверенности в номере заказа ---
    # ВАЖНО: если package_count не распознан (None), заказ ТОЖЕ уходит
    # диспетчеру, а не принимается автоматически. Раньше (баг) None
    # интерпретировался как "пакетов много", и заказ регистрировался
    # без единого уведомления — это позволяло случайно (или намеренно,
    # если сотрудник пришлёт скриншот без секции "Пакеты") обойти
    # проверку диспетчера.
    #
    # Также: если номер заказа найден только как "случайная последовательность
    # цифр" без явного слова-метки ("заказ"/"order"/"№"/"#"), это НИЗКАЯ
    # уверенность (order_number_confident=False) — OCR мог перепутать номер
    # заказа с каким-то другим числом на скриншоте (ценой, телефоном и т.п.).
    # Такой заказ тоже отправляется диспетчеру на ручную проверку, даже если
    # пакетов много.
    needs_dispatcher_approval = (
        package_count is None
        or package_count <= MIN_PACKAGES_FOR_AUTO_ACCEPT
        or not order_number_confident
    )

    if needs_dispatcher_approval:
        try:
            await database.save_pending_order(
                order_number, employee_name, message.chat_id, package_count, format_timestamp()
            )
        except DuplicateOrderError:
            await message.reply_text(
                "⏳ Этот заказ уже был отправлен на рассмотрение (возможно, в тот же момент). "
                "Повторно отправлять не нужно, подождите."
            )
            return
        except Exception:
            logger.exception("Ошибка при сохранении заказа в ожидании")
            await message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
            return

        package_display = package_count if package_count is not None else "не распознано"
        await message.reply_text(
            "⏳ Заказ отправлен диспетчеру, ожидается подтверждение.\n\n"
            f"📦 Заказ №{order_number}\n"
            f"📦 Количество пакетов: {package_display}"
        )
        sent = await _notify_dispatchers(
            context, order_number, employee_name, package_count, order_number_confident
        )
        if not sent:
            await message.reply_text(
                "⚠️ Внимание: сейчас нет зарегистрированного диспетчера, поэтому "
                "этот заказ никому не виден. После регистрации диспетчера через "
                "команду /admin, он сможет увидеть заказы в ожидании командой /pending."
            )
        return

    # --- Автоматическое принятие (package_count > MIN_PACKAGES_FOR_AUTO_ACCEPT) ---
    # ВАЖНО (порядок операций): сначала SQLite (database.save_order), и
    # только потом Google Sheets (google_sheet.add_help_record). Раньше
    # порядок был обратным — это создавало риск двойного учёта: если
    # запись в Sheets проходила успешно, а следующий за ней save_order
    # падал (например, из-за редкой гонки или временной ошибки БД), заказ
    # физически НЕ попадал в таблицу orders (order_exists() вернул бы
    # False), и при повторной отправке того же скриншота сотрудником бот
    # обработал бы его ЕЩЁ РАЗ как новый — с повторным увеличением счётчика
    # в Google Sheets. database.save_order имеет UNIQUE-ограничение на
    # order_number, поэтому если он выполнен первым, любой повтор для того
    # же заказа гарантированно отклоняется ДО того, как Sheets будет
    # тронута повторно.
    try:
        await database.save_order(order_number, employee_name, format_timestamp())
    except DuplicateOrderError:
        await message.reply_text("⚠️ Этот заказ уже был зарегистрирован (обработан параллельно).")
        return
    except Exception:
        logger.exception("Ошибка при обновлении базы данных")
        await message.reply_text("⚠️ Ошибка сервера. Попробуйте позже.")
        return

    try:
        total_count = await google_sheet.add_help_record(employee_name, order_number)
    except Exception:
        # БД уже подтвердила этот заказ как новый и уникальный (защита от
        # повторной обработки обеспечена), но запись в Google Таблицу не
        # удалась — сообщаем администраторам, чтобы это можно было
        # исправить вручную, вместо того чтобы молча потерять запись.
        logger.exception(
            "ВНИМАНИЕ: заказ №%s сохранён в БД, но НЕ записан в Google Sheets "
            "из-за ошибки. Требуется ручная проверка.",
            order_number,
        )
        try:
            await monitoring.notify_admins(
                context.bot,
                "🟠 Help Counter Bot — Google Sheets жазылмады\n\n"
                f"Қызметкер: {employee_name}\n"
                f"Заказ №{order_number}\n\n"
                "Дерекқорда сақталды, бірақ Google Таблицаға жазылмады. "
                "Қолмен тексеріп, керек болса қолмен қосыңыз.",
            )
        except Exception:
            logger.exception("Monitoring: Google Sheets қатесі туралы хабарлау сәтсіз аяқталды")
        await message.reply_text(
            "✅ Заказ учтён в системе, но не удалось обновить Google Таблицу. "
            "Администратор уведомлён и проверит вручную."
        )
        return

    # Заказы больше 5 пакетов автоматически принимаются,
    # но диспетчер получает уведомление для контроля.
    await _notify_dispatchers_auto_warning(context, order_number, employee_name, package_count)

    reply = (
        "✅ Помощь зарегистрирована\n\n"
        f"👤 {employee_name}\n"
        f"📦 Заказ №{order_number}\n"
        f"📦 Количество пакетов: {package_count}\n"
        f"📊 Общее количество оказанной помощи: {total_count}"
    )
    await message.reply_text(reply)


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выход из режима диспетчера."""
    chat_id = update.effective_chat.id

    if not await database.is_dispatcher(chat_id):
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

    if not await database.is_dispatcher(chat_id):
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
        package_text = order["package_count"] if order["package_count"] is not None else "не распознано"
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
    """Вызывается, когда диспетчер нажимает кнопку "Принять" или "Вернуть".

    АВТОРИЗАЦИЯ: раньше эта функция обрабатывала callback от ЛЮБОГО
    чата без проверки — то есть любой участник чата, куда бот отправил
    сообщение (например, участник группы, где один человек когда-то
    вводил /admin), мог нажать "Принять"/"Вернуть". Также, если
    диспетчер вышел через /logout, старые сообщения с кнопками
    оставались активными и callback всё ещё обрабатывался. Теперь чат
    проверяется через database.is_dispatcher() перед любым действием.
    """
    query = update.callback_query
    chat_id = update.effective_chat.id

    if not await database.is_dispatcher(chat_id):
        await query.answer(
            "⛔ У вас нет прав диспетчера для этого действия.", show_alert=True
        )
        logger.warning(
            "Попытка неавторизованного доступа к dispatcher callback из чата %s", chat_id
        )
        return

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
        # Алдымен статусты атомарлы түрде "pending" -> "accepted" етіп
        # ауыстырамыз. Егер басқа диспетчер бұл заказды бір мезгілде
        # өңдеп үлгерсе (updated=False), Google Sheets-ке қайта
        # жазбаймыз — осылайша double-write болдырмаймыз.
        updated = await database.update_pending_order_status(order_number, "accepted")
        if not updated:
            await query.edit_message_text("⚠️ Этот заказ уже обработан другим диспетчером.")
            return

        # ВАЖНО (порядок операций): database.save_order (SQLite, с UNIQUE
        # на order_number) вызывается ПЕРВЫМ, google_sheet.add_help_record —
        # ВТОРЫМ. Причина та же, что и в handle_screenshot: если Sheets
        # обновится первой, а последующая запись в БД упадёт, заказ не
        # будет считаться "существующим" при повторной обработке — и
        # счётчик в Sheets можно будет увеличить повторно.
        try:
            await database.save_order(order_number, employee_name, format_timestamp())
        except DuplicateOrderError:
            await query.edit_message_text("⚠️ Этот заказ уже был зарегистрирован ранее.")
            return
        except Exception:
            logger.exception("Ошибка при сохранении заказа в базу данных")
            await query.edit_message_text(
                "⚠️ Ошибка сервера при сохранении заказа. Попробуйте нажать «Принять» ещё раз."
            )
            return

        try:
            total_count = await google_sheet.add_help_record(employee_name, order_number)
        except Exception:
            # Статус "accepted" болып қалды, БД жағы толық сақталды, бірақ
            # Sheets-ке жазылмады — мұны логта анық көрсетеміз, өйткені
            # қолмен тексеру қажет.
            logger.exception(
                "ВНИМАНИЕ: заказ №%s сохранён в БД (accepted), но НЕ записан в Google Sheets "
                "из-за ошибки. Требуется ручная проверка.",
                order_number,
            )
            try:
                await monitoring.notify_admins(
                    context.bot,
                    "🟠 Help Counter Bot — Google Sheets жазылмады\n\n"
                    f"Қызметкер: {employee_name}\n"
                    f"Заказ №{order_number}\n\n"
                    "Диспетчер қабылдады, дерекқорда сақталды, бірақ Google Таблицаға "
                    "жазылмады. Қолмен тексеріп, керек болса қолмен қосыңыз.",
                )
            except Exception:
                logger.exception("Monitoring: Google Sheets қатесі туралы хабарлау сәтсіз аяқталды")
            await query.edit_message_text(
                "⚠️ Ошибка сервера при записи в таблицу. Обратитесь к администратору "
                f"и сообщите номер заказа №{order_number}."
            )
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
        updated = await database.update_pending_order_status(order_number, "rejected")
        if not updated:
            await query.edit_message_text("⚠️ Этот заказ уже обработан другим диспетчером.")
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
    if update.message is None:
        return
    await update.message.reply_text(
        "📸 Отправьте скриншот заказа вместе с ФИО в подписи."
    )


async def _post_init(application: Application) -> None:
    """Вызывается один раз при запуске Application (в собственном event loop PTB).

    Здесь готовим файл базы данных и все необходимые таблицы (orders,
    pending_orders, dispatchers). Поскольку используется
    CREATE TABLE IF NOT EXISTS, существующим данным (например, таблице
    orders) не наносится никакого вреда — добавляются только
    недостающие таблицы и индексы.

    Сондай-ақ монитoring startup-хабарламасы осы жерде жіберіледі —
    Application толық дайын болғаннан кейін (bot instance жарамды).
    """
    await database.init_db()
    await monitoring.send_startup_notification(application.bot)


def build_application() -> Application:
    """Создаёт объект Telegram Application и регистрирует все обработчики."""
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("top5", top5_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("logout", logout_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("admin", admin_start))

    application.add_handler(
        CallbackQueryHandler(dispatcher_decision_callback, pattern=r"^(approve|reject):")
    )

    # filters.UpdateType.MESSAGE — ТЕК жаңа хабарламалар (жаңа message
    # update), ескі (edited_message), channel_post сияқты update түрлерін
    # өткізбейді. Production логта расталған "AttributeError: 'NoneType'
    # object has no attribute 'caption'" қатесі дәл осы себептен болған:
    # бұрын PHOTO filter-і message/edited_message-ді ажыратпайтын, ал
    # update.edited_message бар, бірақ update.message=None болатын
    # жағдайда handler шақырылып, message.caption қатесі шыққан.
    application.add_handler(
        MessageHandler(filters.UpdateType.MESSAGE & filters.PHOTO, handle_screenshot)
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & ~filters.PHOTO & ~filters.COMMAND, handle_unsupported
        )
    )

    # Monitoring: python-telegram-bot ұстамаған (unhandled) кез келген
    # exception осы хендлерге келеді. monitoring.error_handler өзі
    # ешқашан жаңа exception лақтырмайды (толық try/except-пен
    # қоршалған), сондықтан негізгі бот жұмысына кедергі келтірмейді.
    application.add_error_handler(monitoring.error_handler)

    return application
