"""
Утилиты: очистка ФИО, поиск номера заказа и количества пакетов в тексте
скриншота с помощью regex, форматирование времени.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# Шаблоны, охватывающие варианты "Заказ №254891", "Заказ #254891",
# "Заказ: 254891", "№254891" и т.п. (проверяются по порядку).
ORDER_PATTERNS = [
    re.compile(r"заказ\s*[№#:]*\s*(\d{4,})", re.IGNORECASE),
    re.compile(r"order\s*[№#:]*\s*(\d{4,})", re.IGNORECASE),
    re.compile(r"№\s*(\d{4,})"),
    re.compile(r"#\s*(\d{4,})"),
]

# В качестве последней попытки: любая последовательность из 5+ цифр в тексте
FALLBACK_PATTERN = re.compile(r"\b(\d{5,})\b")

# По формату скриншотов из приложения курьера: "Пакеты (2)" —
# то есть число в скобках на отдельной строке. Также учтены варианты
# "Пакет саны: 3" (кол-во пакетов), "Пакеттер: 5" и т.п.
#
# ВАЖНО: здесь мы ищем число ПОСЛЕ слова "пакет" только в пределах ОДНОЙ
# строки (не переходя на другую строку через \n). Дело в том, что выше
# на скриншоте может быть строка вида "Боксы (1)\n16" — если использовать
# \s*, то это число объединится со словом "Пакеты" на следующей строке,
# и будет получено неверное число (16).
PACKAGE_PATTERNS = [
    # "Пакеты (2)", "Пакеттер(3)", "Пакет : (4)"
    re.compile(r"пакет\w*[ \t]*[:\-]?[ \t]*\([ \t]*(\d{1,3})[ \t]*\)", re.IGNORECASE),
    # "Пакет саны: 3", "Пакеттер: 5", "Пакет-3"
    re.compile(r"пакет\w*[ \t]*(?:саны)?[ \t]*[:\-][ \t]*(\d{1,3})", re.IGNORECASE),
    # "3 пакет" — только в пределах той же строки, не переходя на новую
    re.compile(r"(\d{1,3})[ \t]+пакет\w*", re.IGNORECASE),
    # Варианты на английском (на всякий случай)
    re.compile(r"package\w*[ \t]*[:\-]?[ \t]*\([ \t]*(\d{1,3})[ \t]*\)", re.IGNORECASE),
    re.compile(r"package\w*[ \t]*(?:count)?[ \t]*[:\-][ \t]*(\d{1,3})", re.IGNORECASE),
]


def extract_order_number(text: str) -> Optional[str]:
    """Находит номер заказа в тексте, полученном через OCR.

    Args:
        text: Результат OCR (полный текст).

    Returns:
        Найденный номер заказа (str) или None, если не найден.
    """
    if not text:
        return None

    normalized = text.replace("\n", " ")

    for pattern in ORDER_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return match.group(1)

    fallback = FALLBACK_PATTERN.search(normalized)
    if fallback:
        return fallback.group(1)

    return None


def extract_package_count(text: str) -> Optional[int]:
    """Находит количество пакетов в тексте, полученном через OCR.

    Args:
        text: Результат OCR (полный текст).

    Returns:
        Найденное количество пакетов (int) или None, если не найдено.
    """
    if not text:
        return None

    # Здесь мы НЕ заменяем \n на пробел — шаблоны PACKAGE_PATTERNS выше
    # специально построены на поиске в пределах одной строки (чтобы не
    # перепутать с числом из строки выше, например "Боксы (1)\n16").
    for pattern in PACKAGE_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue

    return None


def clean_employee_name(text: str) -> str:
    """Очищает ФИО, пришедшее в подписи (caption), убирая лишние пробелы."""
    return " ".join(text.strip().split())


def format_timestamp() -> str:
    """Возвращает текущее время в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'."""
    return datetime.now().strftime("%d.%m.%Y %H:%M")
