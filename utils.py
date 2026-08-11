"""
Утилиталар: аты-жөнді тазарту, скриншот мәтінінен заказ нөмірін және
пакет санын regex арқылы табу, уақыт форматтау.
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

# Курьер қосымшасындағы скриншот форматы бойынша: "Пакеты (2)" —
# яғни бөлек жолдағы жақшаның ішіндегі сан. Сонымен қатар "Пакет саны: 3",
# "Пакеттер: 5" секілді нұсқалар да қамтылған.
#
# МАҢЫЗДЫ: осы жерде санды "пакет" сөзінен КЕЙІН, бір жолдың өзінде
# (\n арқылы басқа жолға өтпей) ғана іздейміз. Себебі скриншотта жоғарыда
# "Боксы (1)\n16" деген жол болуы мүмкін — егер \s* қолдансақ, ол келесі
# жолдағы "Пакеты" сөзімен қосылып, қате сан (16) алынып қалады.
PACKAGE_PATTERNS = [
    # "Пакеты (2)", "Пакеттер(3)", "Пакет : (4)"
    re.compile(r"пакет\w*[ \t]*[:\-]?[ \t]*\([ \t]*(\d{1,3})[ \t]*\)", re.IGNORECASE),
    # "Пакет саны: 3", "Пакеттер: 5", "Пакет-3"
    re.compile(r"пакет\w*[ \t]*(?:саны)?[ \t]*[:\-][ \t]*(\d{1,3})", re.IGNORECASE),
    # "3 пакет" — тек сол жолдың өзінде, жаңа жолдан өтпейді
    re.compile(r"(\d{1,3})[ \t]+пакет\w*", re.IGNORECASE),
    # Ағылшынша нұсқалар (қажет болса)
    re.compile(r"package\w*[ \t]*[:\-]?[ \t]*\([ \t]*(\d{1,3})[ \t]*\)", re.IGNORECASE),
    re.compile(r"package\w*[ \t]*(?:count)?[ \t]*[:\-][ \t]*(\d{1,3})", re.IGNORECASE),
]


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


def extract_package_count(text: str) -> Optional[int]:
    """OCR арқылы алынған мәтіннен пакет санын табады.

    Args:
        text: OCR нәтижесі (толық текст).

    Returns:
        Табылған пакет саны (int) немесе табылмаса None.
    """
    if not text:
        return None

    # Мұнда \n жолдарды бос орынға АЙНАЛДЫРМАЙМЫЗ — жоғарыдағы PACKAGE_PATTERNS
    # арнайы бір жолдың шеңберінде іздеуге негізделген (жоғарғы жолдағы санмен
    # (мысалы "Боксы (1)\n16") шатаспау үшін).
    for pattern in PACKAGE_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue

    return None


def clean_employee_name(text: str) -> str:
    """Caption ретінде келген аты-жөнді тазартады (артық бос орындарды алып тастайды)."""
    return " ".join(text.strip().split())


def format_timestamp() -> str:
    """Ағымдағы уақытты 'ДД.ММ.ГГГГ ЧЧ:ММ' форматында қайтарады."""
    return datetime.now().strftime("%d.%m.%Y %H:%M")
