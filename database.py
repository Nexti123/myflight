import aiosqlite

DB_NAME = "flight_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_number TEXT,
                subscriber_telegram_id INTEGER,
                owner_telegram_id INTEGER
            )
        """)
        await db.commit()

async def add_subscription(flight_number: str, subscriber_id: int, owner_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions (flight_number, subscriber_telegram_id, owner_telegram_id) VALUES (?, ?, ?)",
            (flight_number.upper(), subscriber_id, owner_id)
        )
        await db.commit()

async def remove_subscription(flight_number: str, subscriber_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "DELETE FROM subscriptions WHERE flight_number = ? AND subscriber_telegram_id = ?",
            (flight_number.upper(), subscriber_id)
        )
        await db.commit()

async def check_subscription(flight_number: str, subscriber_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id FROM subscriptions WHERE flight_number = ? AND subscriber_telegram_id = ?",
            (flight_number.upper(), subscriber_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None
