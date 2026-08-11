"""
OCR модулі: скриншоттан мәтінді танып, заказ нөмірі мен пакет санын
бөліп алады. config.OCR_ENGINE арқылы "tesseract" немесе "easyocr"
қозғалтқышы таңдалады.

Ескерту: OCR операциясы CPU-мен байланысты (blocking) болғандықтан,
event loop бұғатталмас үшін барлық шақырулар asyncio.to_thread ішінде
орындалады.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from PIL import Image

from config import OCR_ENGINE, OCR_LANGUAGES, TESSERACT_CMD
from utils import extract_order_number, extract_package_count

logger = logging.getLogger(__name__)

# EasyOCR моделін тек бір рет, қажет болғанда ғана жүктейміз (баяу процесс)
_easyocr_reader = None
_tesseract_configured = False


def _configure_tesseract() -> None:
    """Windows-та tesseract.exe PATH-та болмаса, TESSERACT_CMD арқылы нақты жолды көрсетеді."""
    global _tesseract_configured
    if _tesseract_configured:
        return
    if TESSERACT_CMD:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        logger.info("Tesseract жолы орнатылды: %s", TESSERACT_CMD)
    _tesseract_configured = True


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr

        # "ru" — кирилица, "en" — латын әріптер мен сандар үшін
        _easyocr_reader = easyocr.Reader(["ru", "en"], gpu=False)
    return _easyocr_reader


def _ocr_tesseract(image_path: str) -> str:
    import pytesseract

    _configure_tesseract()
    image = Image.open(image_path)
    return pytesseract.image_to_string(image, lang=OCR_LANGUAGES)


def _ocr_easyocr(image_path: str) -> str:
    reader = _get_easyocr_reader()
    results = reader.readtext(image_path, detail=0)
    return "\n".join(results)


def _run_ocr_sync(image_path: str) -> str:
    """Таңдалған OCR қозғалтқышы арқылы синхронды түрде мәтін таниды."""
    try:
        if OCR_ENGINE.lower() == "easyocr":
            return _ocr_easyocr(image_path)
        return _ocr_tesseract(image_path)
    except Exception:
        logger.exception("OCR кезінде қате шықты")
        return ""


async def recognize_order_number(image_path: str) -> Optional[str]:
    """Суреттегі мәтінді таниды және заказ нөмірін қайтарады.

    Ескі функционалдылықпен үйлесімділік үшін қалдырылды.
    """
    order_number, _ = await recognize_order_and_packages(image_path)
    return order_number


async def recognize_order_and_packages(image_path: str) -> Tuple[Optional[str], Optional[int]]:
    """Суреттегі мәтінді таниды, заказ нөмірі мен пакет санын қайтарады.

    Args:
        image_path: Дискідегі скриншот суретінің жолы.

    Returns:
        (order_number, package_count) — екеуі де табылмаса None болуы мүмкін.
    """
    text = await asyncio.to_thread(_run_ocr_sync, image_path)
    order_number = extract_order_number(text)
    package_count = extract_package_count(text)

    if order_number:
        logger.info("Заказ нөмірі табылды: %s", order_number)
    else:
        # Себебін тез анықтау үшін танылған мәтіннің үзіндісін жазамыз.
        preview = (text or "").strip().replace("\n", " ")[:200]
        logger.warning(
            "Заказ нөмірі табылмады. OCR таныған мәтін (алғашқы 200 таңба): %r",
            preview,
        )

    if package_count is not None:
        logger.info("Пакет саны табылды: %s", package_count)
    else:
        logger.warning("Пакет саны табылмады — тапсырыс автоматты режимде өңделеді.")

    return order_number, package_count
