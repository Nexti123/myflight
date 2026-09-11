import aiosqlite

DB_NAME = "flight_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица подписок (для шэринга родителям)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_number TEXT,
                subscriber_telegram_id INTEGER,
                owner_telegram_id INTEGER
            )
        """)
        
        # Таблица кэша API (чтобы не тратить лимиты)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS flight_cache (
                flight_number TEXT PRIMARY KEY,
                data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица истории полетов пользователя
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_flights (
                user_id INTEGER,
                flight_number TEXT,
                PRIMARY KEY (user_id, flight_number)
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

async def get_subscribers(flight_number: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT subscriber_telegram_id FROM subscriptions WHERE flight_number = ?", (flight_number.upper(),)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
