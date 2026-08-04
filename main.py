"""
Жобаның кіру нүктесі (entry point).

Іске қосу: python main.py
"""
import logging

from bot import build_application
from config import setup_logging, validate_config

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    validate_config()

    # database.init_db() енді bot.py ішіндегі post_init хугінде
    # (PTB-дің өз event loop-ында) шақырылады — main.py-де бөлек
    # event loop жасаудың қажеті жоқ.
    application = build_application()

    logger.info("Bot іске қосылды. Polling режимінде жұмыс істеп жатыр...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
