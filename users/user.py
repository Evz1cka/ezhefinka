from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    CallbackQuery)

import asyncpg

from db.db_main import get_pool
from init import logging

user_router = Router()

async def get_or_create_user(user: types.User):
    db_pool = get_pool()
    if not db_pool:
        logging.error("❌ Ошибка: соединение с базой данных не установлено (pool is None)")
        return

    try:
        exists = await db_pool.fetchval(
            "SELECT 1 FROM users WHERE user_id = $1",
            user.id
        )
        
        if not exists:
            await db_pool.execute(
                "INSERT INTO users (user_id, username, first_name, last_name) "
                "VALUES ($1, $2, $3, $4)",
                user.id,
                user.username[:100] if user.username else None,
                user.first_name[:100] if user.first_name else None,
                user.last_name[:100] if user.last_name else None
            )
            logging.info(f"👤 Создан новый пользователь: {user.id}")
        
        await db_pool.execute(
            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = $1",
            user.id
        )
    except asyncpg.PostgresError as db_err:
        logging.error(f"❌ Ошибка базы данных при работе с пользователем {user.id}: {db_err}")
    except Exception as e:
        logging.exception(f"❌ Неизвестная ошибка при создании или обновлении пользователя {user.id}: {e}")

@user_router.callback_query(F.data == "profile")
async def show_profile_callback(call: CallbackQuery):
    await view_profile(call)
    await call.answer()

@user_router.message(Command("profile"))
async def show_profile_message(message: Message):
    await view_profile(message)


async def view_profile(event):
    db_pool = get_pool()
    try:
        user_id = event.from_user.id

        user_data = await db_pool.fetchrow(
            "SELECT username, first_name, last_name, join_date, last_active "
            "FROM users WHERE user_id = $1",
            user_id
        )
        if not user_data:
            await event.answer("❌ Профиль не найден")  # и message.answer, и call.answer есть
            return

        stats = await db_pool.fetchrow(
            "SELECT COUNT(*) as total_expenses, SUM(amount) as total_amount "
            "FROM expenses WHERE user_id = $1",
            user_id
        )
        first_name = user_data['first_name'] or ''
        last_name = user_data['last_name'] or ''
        username = f"@{user_data['username']}" if user_data['username'] else 'не указан'
        total_amount = stats['total_amount'] or 0

        text = (
            f"👤 <b>Ваш профиль</b>\n"
            f"├ Имя: {first_name} {last_name}\n"
            f"├ Юзернейм: {username}\n"
            f"├ Дата регистрации: {user_data['join_date'].strftime('%d.%m.%Y')}\n"
            f"├ Последняя активность: {user_data['last_active'].strftime('%d.%m.%Y %H:%M')}\n"
            f"╰ Статистика:\n"
            f"  └ Всего расходов: {stats['total_expenses']}\n"
            f"  └ Общая сумма: {total_amount:.2f} ₽"
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        )

        # у Message есть метод answer, у CallbackQuery тоже, но для call лучше использовать call.message.answer()
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
        else:
            await event.answer(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"❌ Ошибка при получении профиля: {e}")
        await event.answer("❌ Ошибка при получении профиля")