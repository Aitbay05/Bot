"""
Жобаның кіру нүктесі (entry point).

Іске қосу: python main.py
"""
import logging

from telegram import Update

from bot import build_application
from config import setup_logging, validate_config

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    validate_config()

    # database.init_db() bot.py ішіндегі post_init хугінде
    # (PTB-дің өз event loop-ында) шақырылады.
    application = build_application()

    logger.info("Bot іске қосылды. Polling режимінде жұмыс істеп жатыр...")
    # МАҢЫЗДЫ: allowed_updates=["message"] тек мәтін/фото хабарламаларын
    # қабылдайды, ал inline батырма басу (callback_query) осында ЖОҚ
    # болғандықтан "Қабылдау"/"Қайтару" батырмалары мүлдем іске қосылмай,
    # шексіз "жүктелуде" күйінде қалып қоятын еді. Update.ALL_TYPES
    # арқылы barлық update түрлерін (соның ішінде callback_query) қабылдаймыз.
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
