"""
Модуль конфигурации: загружает все переменные окружения (environment variables)
и настраивает логирование.
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Telegram ---
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# --- Google Sheets (данные хранятся здесь) ---
# Путь к JSON-файлу ключа Service Account (получается в Google Cloud Console).
GOOGLE_CREDENTIALS_PATH: str = os.getenv(
    "GOOGLE_CREDENTIALS_PATH", str(BASE_DIR / "credentials.json")
)
# URL таблицы: https://docs.google.com/spreadsheets/d/<ЭТА_ЧАСТЬ>/edit
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
# Название листа внутри таблицы
GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Sheet1")

# --- OCR ---
# "tesseract" или "easyocr"
OCR_ENGINE: str = os.getenv("OCR_ENGINE", "tesseract")
OCR_LANGUAGES: str = os.getenv("OCR_LANGUAGES", "rus+eng")
# На Windows tesseract.exe может отсутствовать в PATH — в этом случае
# укажите здесь полный путь к нему, например:
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "")

# --- База данных ---
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "orders.db"))

# --- Диспетчер / администратор ---
# Диспетчер болуға рұқсат етілген Telegram chat_id тізімі (үтірмен
# бөлінген). Chat_id-ды білу үшін бот-та /myid командасын қолданыңыз.
# Пароль қолданбаймыз — chat_id-ды жалғандай ешкім ала алмайды
# (Telegram оны сол хабарламаны шын жіберген адамға сәйкес белгілейді),
# сондықтан бұл логин/парольге қарағанда қауіпсіз әрі brute-force-қа
# осал емес.
_raw_admin_chat_ids = os.getenv("ADMIN_CHAT_IDS", "")
ADMIN_CHAT_IDS: list[int] = [
    int(cid.strip()) for cid in _raw_admin_chat_ids.split(",") if cid.strip().lstrip("-").isdigit()
]

# Если пакетов БОЛЬШЕ этого числа — заказ принимается автоматически.
# Если РАВНО или МЕНЬШЕ этого числа — заказ отправляется диспетчеру.
MIN_PACKAGES_FOR_AUTO_ACCEPT: int = int(os.getenv("MIN_PACKAGES_FOR_AUTO_ACCEPT", "5"))

# --- Логирование ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"


def setup_logging() -> None:
    """Настраивает логирование одновременно в консоль и в файл."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
    # Чтобы сторонние библиотеки не выдавали слишком много информации
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def validate_config() -> None:
    """Проверяет наличие обязательных переменных, при отсутствии — останавливается с ошибкой."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if missing:
        raise RuntimeError(
            f"В файле .env не заполнены следующие переменные: {', '.join(missing)}"
        )

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise RuntimeError(
            f"Файл ключа Google Service Account не найден: {GOOGLE_CREDENTIALS_PATH}\n"
            "Проверьте, что GOOGLE_CREDENTIALS_PATH указывает на правильный путь."
        )

    # ADMIN_CHAT_IDS міндетті емес, бірақ ол болмаса /admin командасы
    # ешкімді диспетчер ретінде тіркей алмайды — сондықтан тек ескерту.
    logger = logging.getLogger(__name__)
    if not ADMIN_CHAT_IDS:
        logger.warning(
            "ADMIN_CHAT_IDS орнатылмаған — /admin командасы арқылы диспетчер "
            "тіркеу мүмкін болмайды. /myid арқылы chat_id алып, .env-ге қосыңыз."
        )
