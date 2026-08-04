"""
Утилиталар: аты-жөнді тазарту, скриншот мәтінінен заказ нөмірін
regex арқылы табу, уақыт форматтау.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# "Заказ №254891", "Заказ #254891", "Заказ: 254891", "№254891" секілді
# нұсқалардың барлығын қамтитын үлгілер (ретімен тексеріледі).
ORDER_PATTERNS = [
    re.compile(r"заказ\s*[№#:]*\s*(\d{4,})", re.IGNORECASE),
    re.compile(r"order\s*[№#:]*\s*(\d{4,})", re.IGNORECASE),
    re.compile(r"№\s*(\d{4,})"),
    re.compile(r"#\s*(\d{4,})"),
]

# Соңғы амал ретінде: мәтіндегі кез келген 5+ саннан тұратын тізбек
FALLBACK_PATTERN = re.compile(r"\b(\d{5,})\b")


def extract_order_number(text: str) -> Optional[str]:
    """OCR арқылы алынған мәтіннен заказ нөмірін табады.

    Args:
        text: OCR нәтижесі (толық текст).

    Returns:
        Табылған заказ нөмірі (str) немесе табылмаса None.
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


def clean_employee_name(text: str) -> str:
    """Caption ретінде келген аты-жөнді тазартады (артық бос орындарды алып тастайды)."""
    return " ".join(text.strip().split())


def format_timestamp() -> str:
    """Ағымдағы уақытты 'ДД.ММ.ГГГГ ЧЧ:ММ' форматында қайтарады."""
    return datetime.now().strftime("%d.%m.%Y %H:%M")
