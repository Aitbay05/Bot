"""
Точка входа в проект (entry point).

Запуск: python main.py
"""
import logging

from telegram import Update

from bot import build_application
from config import setup_logging, validate_config

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
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
