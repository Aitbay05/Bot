"""
SQLite арқылы:
1) заказ нөмірлерінің қайталанбауын тексеру,
2) 5 пакеттен аз тапсырыстарды диспетчер қабылдағанға дейін
   "күтуде" статусында сақтау,
3) диспетчер ретінде тіркелген чат id-лерін сақтау
үшін қолданылатын модуль.
"""
import logging
from typing import List, Optional

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_CREATE_ORDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    order_number TEXT PRIMARY KEY,
    employee_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_CREATE_PENDING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pending_orders (
    order_number TEXT PRIMARY KEY,
    employee_name TEXT NOT NULL,
    employee_chat_id INTEGER NOT NULL,
    package_count INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
"""

_CREATE_DISPATCHERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dispatchers (
    chat_id INTEGER PRIMARY KEY,
    added_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    """Дерекқорды және кестелерді (жоқ болса) жасайды. Бот іске қосылғанда бір рет шақырылады."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(_CREATE_ORDERS_TABLE_SQL)
        await db.execute(_CREATE_PENDING_TABLE_SQL)
        await db.execute(_CREATE_DISPATCHERS_TABLE_SQL)
        await db.commit()
    logger.info("SQLite дерекқоры дайын: %s", DATABASE_PATH)


# --- Тіркелген (қабылданған) заказдар ---

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


# --- Диспетчер қабылдауын күтетін (pending) заказдар ---

async def pending_order_exists(order_number: str) -> bool:
    """Заказ нөмірі "күтуде" статусында бұрын жіберілген бе, соны тексереді."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM pending_orders WHERE order_number = ? AND status = 'pending' LIMIT 1",
            (order_number,),
        )
        row = await cursor.fetchone()
        return row is not None


async def save_pending_order(
    order_number: str,
    employee_name: str,
    employee_chat_id: int,
    package_count: Optional[int],
    timestamp: str,
) -> None:
    """5 пакеттен аз тапсырысты "күтуде" статусымен сақтайды."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO pending_orders
                (order_number, employee_name, employee_chat_id, package_count, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (order_number, employee_name, employee_chat_id, package_count, timestamp),
        )
        await db.commit()
    logger.info(
        "Тапсырыс диспетчер қабылдауын күтуде: %s (%s, пакет саны: %s)",
        order_number, employee_name, package_count,
    )


async def get_pending_order(order_number: str) -> Optional[dict]:
    """Күтудегі заказ туралы деректерді қайтарады (табылмаса None)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM pending_orders WHERE order_number = ? LIMIT 1",
            (order_number,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_pending_orders() -> List[dict]:
    """Статусы 'pending' болатын барлық тапсырыстарды (ескіден жаңаға қарай) қайтарады.

    Диспетчер /admin арқылы кешірек тіркелсе де, бұрын келіп үлгерген
    тапсырыстарды /pending командасы арқылы көре алуы үшін қажет.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM pending_orders WHERE status = 'pending' ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_pending_order_status(order_number: str, status: str) -> None:
    """Күтудегі заказдың статусын өзгертеді ('accepted' немесе 'rejected')."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE pending_orders SET status = ? WHERE order_number = ?",
            (status, order_number),
        )
        await db.commit()
    logger.info("Тапсырыс статусы жаңартылды: %s -> %s", order_number, status)


# --- Диспетчерлер ---

async def add_dispatcher(chat_id: int, timestamp: str) -> None:
    """Чатты диспетчер ретінде тіркейді (бұрын тіркелген болса — қайта жазады)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO dispatchers (chat_id, added_at) VALUES (?, ?)",
            (chat_id, timestamp),
        )
        await db.commit()
    logger.info("Жаңа диспетчер чаты тіркелді: %s", chat_id)


async def get_dispatcher_chat_ids() -> List[int]:
    """Барлық тіркелген диспетчер чаттарының id тізімін қайтарады."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT chat_id FROM dispatchers")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def remove_dispatcher(chat_id: int) -> None:
    """Чатты диспетчерлер тізімінен шығарады."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM dispatchers WHERE chat_id = ?",
            (chat_id,),
        )
        await db.commit()

    logger.info("Диспетчер чаты тіркеуден шығарылды: %s", chat_id)
