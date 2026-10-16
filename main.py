"""
Точка входа в проект (entry point).

Запуск: python main.py
"""
import fcntl
import logging
import os
import sys

from telegram import Update

from bot import build_application
from config import BASE_DIR, setup_logging, validate_config

logger = logging.getLogger(__name__)

# Production-та бұрын "Conflict: terminated by other getUpdates request"
# қатесі кездескен — бұл EКІ Telegram-бот процесі (мыс. systemd автоматты
# қайта іске қосу кезінде ескі процесс әлі толық тоқтамай, жаңасы іске
# қосылып кетсе, немесе әзірлеуші қолмен "python main.py" қосып жіберсе)
# БІРДЕЙ bot token-мен бір мезгілде getUpdates (polling) шақырғанда пайда
# болады — Telegram бір токенге тек бір polling сессиясына рұқсат етеді.
# Файл-құлып (file lock) арқылы: екінші процесс бірден, анық хабарламамен
# тоқтайды — Telegram API-мен "жарысуға" (race) түспей, өзінің polling-ін
# мүлде бастамайды.
_LOCK_FILE_PATH = BASE_DIR / "helpbot.lock"
_lock_file_handle = None  # garbage collector жауып кетпеуі үшін модуль деңгейінде сақтаймыз


def _acquire_single_instance_lock() -> None:
    global _lock_file_handle
    _lock_file_handle = open(_LOCK_FILE_PATH, "w")
    try:
        fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.critical(
            "Бот-тың басқа процесі ЕНДІ ҚАЗІР жұмыс істеп тұр (lock-файл: %s бос емес). "
            "Екі процесс бірдей BOT_TOKEN-мен Telegram-ға polling жасаса, "
            "'Conflict: terminated by other getUpdates request' қатесі шығады. "
            "Бұл процесс іске қосылмай тоқтатылады.",
            _LOCK_FILE_PATH,
        )
        sys.exit(1)
    _lock_file_handle.write(str(os.getpid()))
    _lock_file_handle.flush()


def main() -> None:
    setup_logging()
    _acquire_single_instance_lock()
    validate_config()

    # database.init_db() вызывается в хуке post_init внутри bot.py
    # (в собственном event loop PTB).
    application = build_application()

    logger.info("Бот запущен. Работает в режиме polling...")
    # ВАЖНО: allowed_updates=["message"] принимает только текстовые/фото
    # сообщения, а нажатие inline-кнопок (callback_query) сюда НЕ входит —
    # поэтому кнопки "Принять"/"Вернуть" вообще не работали бы и
    # оставались в бесконечном состоянии "загрузка". Через Update.ALL_TYPES
    # принимаем ВСЕ типы обновлений (включая callback_query).
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
