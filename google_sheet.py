"""
Google Sheets модулі: gspread арқылы Google Таблицаға оқу/жазу.
Бұрынғы excel_sheet.py-дың орнына қолданылады — интерфейсі бірдей
(add_help_record, get_all_employees), сондықтан bot.py-де тек импорт
жолын өзгерту жеткілікті.

Аутентификация үшін Google Service Account JSON кілт файлы қажет
(GOOGLE_CREDENTIALS_PATH) және сол service account-тың email-іне
таблицада "Редактор" рөлі берілген болу керек.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_CREDENTIALS_PATH, GOOGLE_SHEET_ID, GOOGLE_SHEET_NAME
from utils import format_timestamp

logger = logging.getLogger(__name__)

HEADERS = ["Аты-жөні", "Көмек саны", "Заказтар", "Соңғы заказ", "Соңғы жаңарту"]

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Бір мезгілде тек бір жазу операциясы жүруі үшін
_lock = asyncio.Lock()

# gspread клиенті мен worksheet-ті қайта-қайта ашпау үшін кэштейміз
_worksheet = None


def _get_worksheet():
    """Google Sheets worksheet объектісін қайтарады (бірінші шақыруда ашады)."""
    global _worksheet
    if _worksheet is not None:
        return _worksheet

    if not GOOGLE_SHEET_ID:
        raise RuntimeError(
            ".env файлында GOOGLE_SHEET_ID толтырылмаған. "
            "Таблица URL-індегі /d/<осы_жер>/edit бөлігін көшіріп қойыңыз."
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
        logger.info("Таблицаға тақырыптар (headers) жазылды")

    _worksheet = ws
    logger.info("Google Sheets дайын: sheet_id=%s, tab=%s", GOOGLE_SHEET_ID, GOOGLE_SHEET_NAME)
    return _worksheet


def _find_row_by_name_sync(ws, name: str) -> Optional[int]:
    """Аты-жөнді бос орындар мен әріп регистріне қарамай салыстырады."""
    target = name.strip().casefold()
    names = ws.col_values(1)  # 1-баған, барлық жолдар (тақырыппен қоса)
    for idx, cell_value in enumerate(names[1:], start=2):
        if cell_value and cell_value.strip().casefold() == target:
            return idx
    return None


def _add_help_record_sync(name: str, order_number: str) -> int:
    """Google Sheets-ті жаңартады, жаңа жалпы көмек санын қайтарады."""
    ws = _get_worksheet()
    row = _find_row_by_name_sync(ws, name)
    timestamp = format_timestamp()

    if row is None:
        ws.append_row([name, 1, order_number, order_number, timestamp])
        logger.info("Жаңа қызметкер қосылды: %s", name)
        return 1

    current_count = ws.cell(row, 2).value or 0
    current_orders = ws.cell(row, 3).value or ""

    try:
        new_count = int(current_count) + 1
    except (ValueError, TypeError):
        logger.warning(
            "Көмек саны бағанында сан емес мән табылды (жол %s), 1-ден бастаймыз", row
        )
        new_count = 1

    new_orders = f"{current_orders}, {order_number}" if current_orders else order_number

    # B,C,D,E бағандарын бір сұраныста жаңарту (API лимитін үнемдеу үшін)
    ws.update(f"B{row}:E{row}", [[new_count, new_orders, order_number, timestamp]])
    return new_count


def _get_all_employees_sync() -> List[dict]:
    ws = _get_worksheet()
    rows = ws.get_all_values()[1:]  # тақырыпты алып тастаймыз
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
    """Google Sheets-ке жаңа көмек жазбасын қосады, жалпы санды қайтарады.

    gspread синхронды кітапхана болғандықтан, шақыру asyncio.to_thread
    ішінде орындалады.
    """
    async with _lock:
        return await asyncio.to_thread(_add_help_record_sync, name, order_number)


async def get_all_employees() -> List[dict]:
    """Барлық қызметкерлердің тізімін [{'name': ..., 'count': ...}, ...] түрінде қайтарады."""
    async with _lock:
        return await asyncio.to_thread(_get_all_employees_sync)
