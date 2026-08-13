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
# OCR әртүрлі форматта тануы мүмкін, сондықтан бірнеше нұсқаны қолдаймыз:
# "Пакеты (6)", "Пакеттер: 6", "Пакетов 6", "Пакет саны 6",
# "6 пакет", "6 пакеттер", "packages: 6" және т.б.
PACKAGE_PATTERNS = [
    # "Пакеты (6)", "Пакеттер(3)", "Пакет : (4)"
    re.compile(r"пакет\w*[ \t]*[:\-]?[ \t]*\([ \t]*(\d{1,3})[ \t]*\)", re.IGNORECASE),

    # "Пакет саны: 6", "Пакеттер: 6", "Пакет-6"
    re.compile(
        r"пакет\w*[ \t]*(?:саны[ \t]*)?[:\-][ \t]*(\d{1,3})",
        re.IGNORECASE,
    ),

    # "Пакет саны 6", "Пакеттер 6", "Пакетов 6" — қос нүктесіз де
    re.compile(
        r"пакет\w*[ \t]+(?:саны[ \t]*)?(\d{1,3})",
        re.IGNORECASE,
    ),

    # "6 пакет", "6 пакеттер", "6 пакетов"
    re.compile(r"(\d{1,3})[ \t]+пакет\w*", re.IGNORECASE),

    # English: "packages (6)", "packages: 6", "packages 6"
    re.compile(
        r"package\w*[ \t]*[:\-]?[ \t]*\([ \t]*(\d{1,3})[ \t]*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"package\w*[ \t]*(?:count[ \t]*)?[:\-]?[ \t]*(\d{1,3})",
        re.IGNORECASE,
    ),
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

    # Алдымен бір жол ішіндегі барлық белгілі форматтарды тексереміз.
    # Бұл "Боксы (1)\n16" сияқты қате сәйкестіктерден қорғайды.
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        for pattern in PACKAGE_PATTERNS:
            match = pattern.search(line)
            if match:
                try:
                    count = int(match.group(1))
                    # Пакет саны әдетте 1..999 аралығында болады.
                    if 0 < count <= 999:
                        return count
                except (TypeError, ValueError):
                    continue

    # Кейбір OCR нәтижесінде "Пакеты" бір жолда, ал "6" келесі жолда
    # жеке тұруы мүмкін. Тек келесі жол ТЕК сан болған жағдайда ғана
    # қабылдаймыз — басқа сандарды қате пакет саны деп алмау үшін.
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines[:-1]):
        if not line or not re.search(r"пакет\w*|package\w*", line, re.IGNORECASE):
            continue

        next_line = lines[index + 1]
        match = re.fullmatch(r"(\d{1,3})", next_line)
        if match:
            count = int(match.group(1))
            if 0 < count <= 999:
                return count

    return None


def clean_employee_name(text: str) -> str:
    """Очищает ФИО, пришедшее в подписи (caption), убирая лишние пробелы."""
    return " ".join(text.strip().split())


def format_timestamp() -> str:
    """Возвращает текущее время в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'."""
    return datetime.now().strftime("%d.%m.%Y %H:%M")
