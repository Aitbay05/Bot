"""
Monitoring / Error Alert модулі.

Мақсаты: ботта күтпеген (unhandled) exception немесе маңызды оқиға
(іске қосылу) болғанда, ADMIN_CHAT_IDS тізіміндегі администраторларға
Telegram арқылы автоматты хабарлама жіберу.

Дизайн принциптері:
1. Monitoring негізгі ботқа ТӘУЕЛДІ емес — оны шақыратын жер (bot.py-дегі
   error handler, main.py-дегі post_init) әрқашан try/except-пен
   қоршалған, сондықтан monitoring-тің өзінде қате шықса да (мыс.
   Telegram API уақытша қолжетімсіз болса), негізгі бот жұмысын
   жалғастыра береді — тек логқа жазылады.
2. Бірдей қате қайта-қайта (мыс. секунд сайын) қайталанса, әр
   рет Telegram-ға жібермей, cooldown (300 сек) қолданамыз — әйтпесе
   администратор жүздеген бірдей хабарламаға "бомбаланады".
3. Хабарламада ешқашан BOT_TOKEN, Google credentials немесе басқа
   құпия ақпарат болмауы керек — тек error type, error message және
   traceback-тің қысқа үзіндісі.
"""
from __future__ import annotations

import logging
import re
import time
import traceback
from typing import Optional

from telegram import Bot
from telegram.error import Conflict as TelegramConflict

from config import ADMIN_CHAT_IDS, BOT_TOKEN

logger = logging.getLogger(__name__)

# Telegram хабарлама лимиті — 4096 таңба. Форматтауға (тақырып, эмодзи
# және т.б.) орын қалдыру үшін одан аз шек қоямыз.
_MAX_MESSAGE_LENGTH = 3500

# Бірдей қате үшін қайта хабарлама жіберу арасындағы минималды уақыт (сек).
_ERROR_COOLDOWN_SECONDS = 300

# {error_key: соңғы жіберілген уақыт (time.monotonic())}
_last_error_sent_at: dict[str, float] = {}


def _error_key(error_type: str, message: str) -> str:
    """Қате түрі мен хабарламаның бірінші жолы бойынша қысқа кілт жасайды.

    Толық traceback-ті кілт ретінде қолданбаймыз — сол себепті бір
    орында (мыс. бір `except` блогында) қайта-қайта шығатын БІРДЕЙ
    қате дұрыс танылады, тіпті traceback-тегі жол нөмірлері сәл
    өзгеше көрінсе де.
    """
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    return f"{error_type}:{first_line}"


def _is_in_cooldown(key: str) -> bool:
    last_sent = _last_error_sent_at.get(key)
    if last_sent is None:
        return False
    return (time.monotonic() - last_sent) < _ERROR_COOLDOWN_SECONDS


def _mark_sent(key: str) -> None:
    _last_error_sent_at[key] = time.monotonic()


def reset_cooldowns() -> None:
    """Тек тестілеу үшін: cooldown жадын тазалайды."""
    _last_error_sent_at.clear()


def _truncate(text: str, limit: int = _MAX_MESSAGE_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n… (қысқартылды)"


def _format_traceback_excerpt(tb_text: str, max_lines: int = 15) -> str:
    """Traceback-тің ЕҢ ПАЙДАЛЫ бөлігін алады — соңғы жолдар (нақты
    exception шыққан жер мен error message онда болады), басы емес."""
    lines = [line for line in tb_text.strip().splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "…\n" + "\n".join(lines[-max_lines:])


async def notify_admins(bot: Bot, text: str) -> None:
    """ADMIN_CHAT_IDS тізіміндегі барлық админге хабарлама жібереді.

    Бір админ ботты бұғаттаған/қолжетімсіз болса, қалғандарына
    жіберу тоқтамайды — әрқайсысы жеке try/except-пен қоршалған.
    """
    if not ADMIN_CHAT_IDS:
        logger.warning(
            "Monitoring: ADMIN_CHAT_IDS бос — хабарлама ешкімге жіберілмейді "
            "(тек логталады): %s",
            text[:200].replace("\n", " "),
        )
        return

    for chat_id in ADMIN_CHAT_IDS:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            # Monitoring-тің өз қатесі негізгі ботты еш уақытта тоқтатпауы
            # керек — сондықтан кез келген exception осында ұсталады.
            logger.exception(
                "Monitoring: администраторға (chat_id=%s) хабарлама жіберу сәтсіз аяқталды",
                chat_id,
            )


async def send_startup_notification(bot: Bot) -> None:
    """Бот сәтті іске қосылғанда бір рет шақырылады (main.py/bot.py post_init)."""
    try:
        await notify_admins(
            bot,
            "🟢 Help Counter Bot\n\nБот успешно запущен и готов принимать заказы.",
        )
    except Exception:
        # Осы жерде де сақтық: startup notification сәтсіз болса да,
        # бот өз жұмысын бастауы керек.
        logger.exception("Monitoring: startup notification жіберу кезінде күтпеген қате")


# Telegram bot-токенінің пішіні: "123456789:AA...35 таңба". Кейбір
# telegram-ext қателерінің мәтінінде (мыс. желі/URL қатесі) осындай
# жол кездейсоқ болуы мүмкін — мониторинг хабарламасы Telegram-ға
# кетпес бұрын оны міндетті түрде жасырамыз. Толық (жасырылмаған)
# traceback ӘРҚАШАН тек серверлік логта қалады, Telegram-ға ешқашан
# жіберілмейді.
_BOT_TOKEN_PATTERN = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,45}")


def _redact_secrets(text: str) -> str:
    if BOT_TOKEN:
        text = text.replace(BOT_TOKEN, "[BOT_TOKEN REDACTED]")
    text = _BOT_TOKEN_PATTERN.sub("[BOT_TOKEN REDACTED]", text)
    return text


def format_error_message(error_type: str, error_message: str, tb_text: str) -> str:
    excerpt = _format_traceback_excerpt(tb_text)
    text = (
        "🔴 Help Counter Bot — ERROR\n\n"
        f"Тип: {error_type}\n\n"
        f"Ошибка:\n{error_message or '(пусто)'}\n\n"
        f"Traceback:\n{excerpt}"
    )
    # Telegram-ға кетпес бұрын құпия ақпаратты (BOT_TOKEN және т.б.)
    # жасырамыз — тіпті error message/traceback ішінде кездейсоқ
    # кездессе де.
    text = _redact_secrets(text)
    return _truncate(text)


async def error_handler(update: object, context) -> None:
    """`Application.add_error_handler(error_handler)` арқылы тіркеледі.

    python-telegram-bot кез келген handler ішінде ұсталмаған exception
    шыққанда осы функцияны шақырады (`context.error` ішінде exception
    объектісі болады). Бұл функцияның өзі ешқашан жаңа exception
    лақтырмауы керек — әйтпесе PTB "error while handling an error"
    жағдайына түсіп, тек логтап қана қоймай, шексіз циклге ұрынуы мүмкін.
    """
    error = getattr(context, "error", None)
    error_type = type(error).__name__ if error is not None else "UnknownError"
    error_message = str(error) if error is not None else ""

    if error is not None:
        tb_text = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
    else:
        tb_text = ""

    # Толық traceback ӘРҚАШАН серверлік логта сақталады (қысқартылмайды) —
    # Telegram-ға тек қысқа үзінді кетеді.
    logger.error("Unhandled exception (update=%r):\n%s", update, tb_text or error_message)

    # "Conflict: terminated by other getUpdates request" production-та
    # бұрын кездескен нақты оқиға — екі бот процесі бір token-мен бір
    # мезгілде polling жасағанда шығады. main.py-дегі файл-құлып (single
    # instance lock) бұл жағдайды алдын алады, бірақ желі/деплой кезінде
    # сирек орын алуы мүмкін болғандықтан, мұны администраторға ӨЗГЕШЕ,
    # түсінікті хабарламамен бөлек белгілейміз (жай "unhandled exception"
    # емес — нақты не істеу керегін көрсетеміз).
    if isinstance(error, TelegramConflict):
        logger.critical(
            "Telegram polling conflict: екінші бот процесі іске қосылған болуы мүмкін. "
            "`ps aux | grep main.py` арқылы тексеріп, артық процесті тоқтатыңыз."
        )

    try:
        key = _error_key(error_type, error_message)
        if _is_in_cooldown(key):
            logger.info(
                "Monitoring: '%s' қатесі cooldown ішінде (%s сек) — Telegram-ға "
                "қайта жіберілмейді",
                error_type,
                _ERROR_COOLDOWN_SECONDS,
            )
            return
        _mark_sent(key)

        bot: Optional[Bot] = getattr(context, "bot", None)
        if bot is None:
            logger.warning("Monitoring: context.bot қолжетімсіз, хабарлама жіберілмеді")
            return

        text = format_error_message(error_type, error_message, tb_text)
        await notify_admins(bot, text)
    except Exception:
        # Monitoring-тің өз ішінде шыққан кез келген қате осы жерде
        # тоқтатылады — негізгі бот жұмысына КЕДЕРГІ КЕЛТІРМЕЙДІ.
        logger.exception("Monitoring: error_handler ішінде күтпеген қате")
