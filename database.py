"""
SQLite арқылы заказ нөмірлерінің қайталанбауын (дубликат болмауын)
тексеретін модуль. Excel файлын әр жолы толық оқымай-ақ жылдам тексеру
үшін локальді дерекқор ретінде қолданылады.
"""
import logging

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    order_number TEXT PRIMARY KEY,
    employee_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    """Дерекқорды және кестені (жоқ болса) жасайды. Бот іске қосылғанда бір рет шақырылады."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.commit()
    logger.info("SQLite дерекқоры дайын: %s", DATABASE_PATH)


async def order_exists(order_number: str) -> bool:
    """Заказ нөмірі бұрын тіркелген бе, соны тексереді."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM orders WHERE order_number = ? LIMIT 1", (order_number,)
        )
        row = await cursor.fetchone()
        return row is not None


async def save_order(order_number: str, employee_name: str, timestamp: str) -> None:
    """Жаңа заказды дерекқорға сақтайды (дубликатты болдырмау үшін)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO orders (order_number, employee_name, created_at) VALUES (?, ?, ?)",
            (order_number, employee_name, timestamp),
        )
        await db.commit()
    logger.info("Заказ сақталды: %s (%s)", order_number, employee_name)
