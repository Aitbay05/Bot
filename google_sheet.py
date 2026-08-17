"""
Модуль Google Sheets: чтение/запись в Google Таблицу через gspread.
Используется вместо прежнего excel_sheet.py — интерфейс тот же
(add_help_record, get_all_employees), поэтому в bot.py достаточно
изменить только строку импорта.

Для аутентификации требуется JSON-файл ключа Google Service Account
(GOOGLE_CREDENTIALS_PATH), и email этого service account должен иметь
роль "Редактор" в самой таблице.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError

from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_SHEET_ID, GOOGLE_SHEET_NAME
from utils import format_timestamp

logger = logging.getLogger(__name__)

HEADERS = ["ФИО", "Количество помощи", "Заказы", "Последний заказ", "Последнее обновление"]

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Чтобы в один момент времени выполнялась только одна операция записи
_lock = asyncio.Lock()

# Кэшируем клиент gspread и worksheet, чтобы не открывать их заново каждый раз
_worksheet = None

# --- Retry-настройки для временных сбоев Google API (429/5xx/сетевые ошибки) ---
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE_SECONDS = 1.5


def _get_worksheet():
    """Возвращает объект worksheet Google Sheets (открывает при первом вызове)."""
    global _worksheet
    if _worksheet is not None:
        return _worksheet

    if not GOOGLE_SHEET_ID:
        raise RuntimeError(
            "В файле .env не заполнен GOOGLE_SHEET_ID. "
            "Скопируйте часть /d/<это_поле>/edit из URL таблицы."
        )

    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=_SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    existing_titles = [ws.title for ws in spreadsheet.worksheets()]
    if GOOGLE_SHEET_NAME in existing_titles:
        ws = spreadsheet.worksheet(GOOGLE_SHEET_NAME)
    else:
        ws = spreadsheet.add_worksheet(
            title=GOOGLE_SHEET_NAME, rows=1000, cols=len(HEADERS)
        )

    first_row = ws.row_values(1)
    if first_row[: len(HEADERS)] != HEADERS:
        ws.update("A1", [HEADERS])
        logger.info("В таблицу записаны заголовки (headers)")

    _worksheet = ws
    logger.info("Google Sheets готов: sheet_id=%s, tab=%s", GOOGLE_SHEET_ID, GOOGLE_SHEET_NAME)
    return _worksheet


def _is_retryable_api_error(exc: Exception) -> bool:
    """429 (rate limit) және 5xx (уақытша сервер қатесі) қайталауға жарамды деп есептейміз."""
    if not isinstance(exc, APIError):
        return False
    try:
        status = exc.response.status_code
    except Exception:
        return False
    return status == 429 or 500 <= status < 600


def _with_retry(func, *args, **kwargs):
    """Google Sheets API-ды уақытша (429/5xx) қателерде exponential backoff-пен қайта шақырады.

    Бұрын кез келген желілік ақау немесе rate-limit бірден exception
    ретінде bot.py-ге дейін көтеріліп, пайдаланушыға "сервер қатесі"
    ретінде көрінетін. Енді уақытша қателер бірнеше рет қайталанып
    көрінеді, тек содан кейін ғана қате көтеріледі.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except APIError as exc:
            last_exc = exc
            if not _is_retryable_api_error(exc) or attempt == _MAX_RETRIES:
                raise
            delay = _RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Google Sheets API уақытша қате қайтарды (талпыныс %s/%s), %.1f секундтан кейін қайталаймыз: %s",
                attempt, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
    if last_exc:
        raise last_exc


def _find_row_by_name_sync(ws, name: str) -> Optional[int]:
    """Сравнивает ФИО без учёта лишних пробелов и регистра букв."""
    target = name.strip().casefold()
    names = ws.col_values(1)  # 1-я колонка, все строки (включая заголовок)
    for idx, cell_value in enumerate(names[1:], start=2):
        if cell_value and cell_value.strip().casefold() == target:
            return idx
    return None


def _add_help_record_sync(name: str, order_number: str) -> int:
    """Обновляет Google Sheets, возвращает новое общее количество помощи."""
    ws = _get_worksheet()
    row = _with_retry(_find_row_by_name_sync, ws, name)
    timestamp = format_timestamp()

    if row is None:
        _with_retry(ws.append_row, [name, 1, order_number, order_number, timestamp])
        logger.info("Добавлен новый сотрудник: %s", name)
        return 1

    current_count = _with_retry(ws.cell, row, 2).value or 0
    current_orders = _with_retry(ws.cell, row, 3).value or ""

    try:
        new_count = int(current_count) + 1
    except (ValueError, TypeError):
        logger.warning(
            "В колонке количества помощи найдено нечисловое значение (строка %s), начинаем с 1", row
        )
        new_count = 1

    new_orders = f"{current_orders}, {order_number}" if current_orders else order_number

    # Обновляем колонки B,C,D,E одним запросом (чтобы сэкономить лимит API)
    _with_retry(ws.update, f"B{row}:E{row}", [[new_count, new_orders, order_number, timestamp]])
    return new_count


def _get_all_employees_sync() -> List[dict]:
    ws = _get_worksheet()
    rows = _with_retry(ws.get_all_values)[1:]  # убираем заголовок
    employees = []
    for row in rows:
        if not row or not row[0]:
            continue
        name = row[0]
        count_raw = row[1] if len(row) > 1 else "0"
        try:
            count = int(count_raw)
        except (ValueError, TypeError):
            count = 0
        employees.append({"name": name, "count": count})
    return employees


async def add_help_record(name: str, order_number: str) -> int:
    """Добавляет новую запись о помощи в Google Sheets, возвращает общее количество.

    Поскольку gspread — синхронная библиотека, вызов выполняется внутри
    asyncio.to_thread. _lock гарантирует, что внутри ЭТОГО процесса
    операции записи не пересекаются (защита от lost update при двух
    почти одновременных заказах). Если бот когда-нибудь будет запущен
    в нескольких процессах одновременно — этой блокировки уже
    недостаточно, потребуется внешняя блокировка (например, через БД).
    """
    async with _lock:
        return await asyncio.to_thread(_add_help_record_sync, name, order_number)


async def get_all_employees() -> List[dict]:
    """Возвращает список всех сотрудников в виде [{'name': ..., 'count': ...}, ...]."""
    async with _lock:
        return await asyncio.to_thread(_get_all_employees_sync)
