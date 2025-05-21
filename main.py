
from aiogram import Bot, Dispatcher

from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update
from typing import Callable, Awaitable, Dict, Any

from init import BOT_TOKEN, logging
from db.db_main import create_table, init_db_pool, close_db, get_pool

from users.user import get_or_create_user, user_router
from handlers.start import start_router
from handlers.stats import stats_router
from expense.expense_main import expense_router
from expense.expense_delete import expense_delete_router
from expense.expense_history import expense_history_router

# Инициализация бота
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

all_routers = [start_router, stats_router, expense_router, user_router, expense_delete_router, expense_history_router  ]

class UserActivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        logging.info("🛠 Middleware сработал. Проверяю пользователя...")

        user = getattr(event, "from_user", None)

        # Ищем пользователя в известных вложениях, если напрямую не найден
        if user is None:
            for attr in ["message", "callback_query", "chat_member", "my_chat_member"]:
                inner = getattr(event, attr, None)
                if inner and getattr(inner, "from_user", None):
                    user = inner.from_user
                    break

        if user is None:
            logging.warning("⚠️ Не удалось определить пользователя. Пропускаю событие.")
            return await handler(event, data)

        # Добавляем/обновляем пользователя в базе
        try:
            db_pool = get_pool()

            exists = await db_pool.fetchval(
                "SELECT 1 FROM users WHERE user_id = $1",
                user.id
            )

            if not exists:
                await db_pool.execute(
                    "INSERT INTO users (user_id, username, first_name, last_name) "
                    "VALUES ($1, $2, $3, $4)",
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name
                )
                logging.info(f"🆕 Пользователь {user.full_name} (ID: {user.id}) добавлен в базу.")

            await db_pool.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = $1",
                user.id
            )

        except Exception as e:
            logging.error(f"❌ Ошибка при обработке пользователя в middleware: {e}")

        return await handler(event, data)
# Добавляем в диспетчер
dp.update.middleware(UserActivityMiddleware())


async def main():
    """Основная функция запуска бота""" 
    logging.info("🔄 Запуск бота...")
    # Подключаем роутеры
    for router in all_routers:
        dp.include_router(router)
    try:
        await init_db_pool()
        await create_table()
        logging.info("✅ База данных подключена.")
    except Exception as e:
        logging.critical(f"❌ Ошибка подключения к БД: {e}", exc_info=True)
        return
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)  # Очищаем неотправленные сообщения
        logging.info("🚀 Бот начинает работу...")
        await dp.start_polling(bot)

    except asyncio.CancelledError:
        logging.warning("⏹️ Бот остановлен вручную (Ctrl+C)")

    except Exception as e:
        logging.exception("❌ Критическая ошибка в main():")

    finally:
        logging.info("🔻 Завершение работы бота...")
        try:
            await dp.shutdown()
        except Exception as e:
            logging.error(f"⚠️ Ошибка при завершении диспетчера: {e}")

        try:
            await close_db()
        except Exception as e:
            logging.error(f"⚠️ Ошибка при закрытии соединения с БД: {e}")

        logging.info("✅ Все ресурсы закрыты. Бот остановлен.")
    
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
#endregion