import asyncpg
from init import DB_URL, logging

pool = None

def get_pool():
    """Возвращает текущий пул соединений"""
    global pool
    return pool

async def init_db_pool():
    """Создает пул соединений"""
    global pool
    if not pool:
        pool = await asyncpg.create_pool(dsn=DB_URL)

async def close_db():
    """Закрывает пул соединений с базой данных"""
    global pool
    if pool:
        await pool.close()
        pool = None

async def create_table():
    """Создает таблицы, если их нет"""
    db_pool = get_pool()
    async with db_pool.acquire() as conn:
        # Таблица пользователей должна создаваться первой (на неё ссылается другая таблица)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(100),
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                category VARCHAR(50) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'RUB',
                date DATE NOT NULL DEFAULT CURRENT_DATE,
                time TIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')