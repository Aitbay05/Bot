"""
Модуль OCR: распознаёт текст со скриншота и выделяет из него номер заказа
и количество пакетов. Через config.OCR_ENGINE выбирается движок
"tesseract" или "easyocr".

Примечание: операция OCR является CPU-нагруженной (blocking), поэтому,
чтобы не блокировать event loop, все вызовы выполняются внутри
asyncio.to_thread.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from PIL import Image

from config import OCR_ENGINE, OCR_LANGUAGES, TESSERACT_CMD
from utils import extract_order_number, extract_package_count

logger = logging.getLogger(__name__)

# Модель EasyOCR загружаем только один раз, при необходимости (медленный процесс)
_easyocr_reader = None
_tesseract_configured = False


def _configure_tesseract() -> None:
    """Если на Windows tesseract.exe отсутствует в PATH, указывает точный путь через TESSERACT_CMD."""
    global _tesseract_configured
    if _tesseract_configured:
        return
    if TESSERACT_CMD:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        logger.info("Путь к Tesseract установлен: %s", TESSERACT_CMD)
    _tesseract_configured = True


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr

        # "ru" — кириллица, "en" — латинские буквы и цифры
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
    """Синхронно распознаёт текст с помощью выбранного OCR-движка."""
    try:
        if OCR_ENGINE.lower() == "easyocr":
            return _ocr_easyocr(image_path)
        return _ocr_tesseract(image_path)
    except Exception:
        logger.exception("Ошибка во время OCR")
        return ""


async def recognize_order_number(image_path: str) -> Optional[str]:
    """Распознаёт текст на изображении и возвращает номер заказа.

    Оставлена для совместимости со старым функционалом.
    """
    order_number, _ = await recognize_order_and_packages(image_path)
    return order_number


async def recognize_order_and_packages(image_path: str) -> Tuple[Optional[str], Optional[int]]:
    """Распознаёт текст на изображении, возвращает номер заказа и количество пакетов.

    Args:
        image_path: Путь к файлу скриншота на диске.

    Returns:
        (order_number, package_count) — оба значения могут быть None, если не найдены.
    """
    text = await asyncio.to_thread(_run_ocr_sync, image_path)
    order_number = extract_order_number(text)
    package_count = extract_package_count(text)

    if order_number:
        logger.info("Номер заказа найден: %s", order_number)
    else:
        # Записываем фрагмент распознанного текста, чтобы быстро понять причину.
        preview = (text or "").strip().replace("\n", " ")[:200]
        logger.warning(
            "Номер заказа не найден. Текст, распознанный OCR (первые 200 символов): %r",
            preview,
        )

    if package_count is not None:
        logger.info("Количество пакетов найдено: %s", package_count)
    else:
        logger.warning("Количество пакетов не найдено — заказ будет обработан в автоматическом режиме.")

    return order_number, package_count
