"""
Config modulі: барлық орта айнымалыларын (environment variables) жүктейді
және логтауды баптайды.
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Telegram ---
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# --- Google Sheets (мәліметтер осында сақталады) ---
# Service Account JSON кілт файлының жолы (Google Cloud Console-дан алынады).
GOOGLE_CREDENTIALS_PATH: str = os.getenv(
    "GOOGLE_CREDENTIALS_PATH", str(BASE_DIR / "credentials.json")
)
# Таблица URL-і: https://docs.google.com/spreadsheets/d/<ОСЫ_ЖЕР>/edit
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
# Таблицаның ішіндегі парақ (лист) атауы
GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "Sheet1")

# --- OCR ---
# "tesseract" немесе "easyocr"
OCR_ENGINE: str = os.getenv("OCR_ENGINE", "tesseract")
OCR_LANGUAGES: str = os.getenv("OCR_LANGUAGES", "rus+eng")
# Windows-та tesseract.exe PATH-та болмауы мүмкін — сол кезде оның толық
# жолын осында көрсетуге болады, мысалы:
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "")

# --- Database ---
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "orders.db"))

# --- Диспетчер / админ ---
# /admin командасы арқылы кіру үшін логин мен пароль.
ADMIN_LOGIN: str = os.getenv("ADMIN_LOGIN", "")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

# Осы саннан КОП пакет болса — автоматты қабылданады.
# Осы санға ТЕҢ немесе одан АЗ болса — диспетчерге жіберіледі.
MIN_PACKAGES_FOR_AUTO_ACCEPT: int = int(os.getenv("MIN_PACKAGES_FOR_AUTO_ACCEPT", "5"))

# --- Logging ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"


def setup_logging() -> None:
    """Логтауды консольге және файлға бір мезгілде жазатындай баптайды."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )
    # Сыртқы кітапханалардың тым көп ақпарат беруін болдырмау
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def validate_config() -> None:
    """Міндетті айнымалылар бар-жоғын тексереді, жоқ болса қатемен тоқтайды."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if missing:
        raise RuntimeError(
            f".env файлында келесі айнымалылар толтырылмаған: {', '.join(missing)}"
        )

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise RuntimeError(
            f"Google Service Account кілт файлы табылмады: {GOOGLE_CREDENTIALS_PATH}\n"
            "GOOGLE_CREDENTIALS_PATH дұрыс жолды көрсетіп тұрғанын тексеріңіз."
        )

    # ADMIN_LOGIN/ADMIN_PASSWORD міндетті емес, бірақ болмаса /admin
    # командасы ешқашан сәтті болмайды — сондықтан тек ескерту береміз.
    logger = logging.getLogger(__name__)
    if not ADMIN_LOGIN or not ADMIN_PASSWORD:
        logger.warning(
            "ADMIN_LOGIN немесе ADMIN_PASSWORD орнатылмаған — /admin командасы "
            "арқылы диспетчер тіркеу мүмкін болмайды."
        )
