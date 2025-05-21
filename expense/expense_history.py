import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,

)

import asyncpg  # для работы с базой данных 
from init import logging  # твой модуль для логов
from db.db_main import get_pool  # функция для получения пула подключения к базе

# Создаем роутер для обработки удаления расходов
expense_history_router = Router()

EXPENSES_PER_PAGE = 5  # Количество расходов на одной странице


@expense_history_router.callback_query(F.data == "expenses_history")
async def expenses_history_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📅 Последние", callback_data="expenses_recent"),
        types.InlineKeyboardButton(text="🔍 Поиск", callback_data="expenses_search")
    )
    builder.row(
        types.InlineKeyboardButton(text="🗂 По категориям", callback_data="expenses_by_category"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )
    
    await call.message.edit_text(
        "📝 <b>История расходов</b>\nВыберите способ просмотра:",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@expense_history_router.callback_query(F.data == "expenses_search") # Обработка кнопки "Статистика"
async def search_expenses(callback: CallbackQuery):
    await callback.answer("🚧 Эта функция пока в разработке.", show_alert=True)

@expense_history_router.callback_query(F.data == "expenses_by_category") # Обработка кнопки "Статистика"
async def expenses_hystory_categories(callback: CallbackQuery):
    await callback.answer("🚧 Эта функция пока в разработке.", show_alert=True)

@expense_history_router.callback_query(F.data == "expenses_recent")
async def show_history_start(call: CallbackQuery):
    # Показываем первую страницу
    await show_expenses_page(call.message, call.from_user.id, 1)
    await call.answer()  # добавим call.answer() чтобы убрать "часики"


async def show_expenses_page(message: types.Message, user_id: int, page: int):
    pool = get_pool()
    try:
        total_expenses = await pool.fetchval(
            "SELECT COUNT(*) FROM expenses WHERE user_id = $1",
            user_id
        ) or 0
        
        total_pages = max((total_expenses - 1) // EXPENSES_PER_PAGE + 1, 1)
        
        expenses = await pool.fetch(
            "SELECT id, category, amount, date, time FROM expenses "
            "WHERE user_id = $1 "
            "ORDER BY date DESC, (time IS NULL), time DESC, created_at DESC "
            "LIMIT $2 OFFSET $3",
            user_id,
            EXPENSES_PER_PAGE,
            (page - 1) * EXPENSES_PER_PAGE
        )

        
        if not expenses:
            await message.answer("📭 У вас пока нет записей о расходах")
            return
            
        text = (
            f"📝 <b>История расходов</b> (страница {page}/{total_pages})\n"
            f"📊 Всего записей: <b>{total_expenses}</b>\n\n"
        )
        
        for i, expense in enumerate(expenses, 1):
            date_str = expense['date'].strftime('%d.%m.%Y')
            time_str = f" {expense['time'].strftime('%H:%M')}" if expense['time'] else ""
            text += (
                f"<b>#{i + (page-1)*EXPENSES_PER_PAGE}</b> | 🆔 <code>{expense['id']}</code>\n"
                f"📅 <b>{date_str}{time_str}</b>\n"
                f"🏷 {expense['category']}: <b>{expense['amount']:.2f} ₽</b>\n\n"
            )
        
        builder = InlineKeyboardBuilder()
        
        if page > 1:
            builder.button(text="⬅️ Назад", callback_data=f"expenses_page_{page-1}")
        if page < total_pages:
            builder.button(text="Вперед ➡️", callback_data=f"expenses_page_{page+1}")
        
        builder.button(text="🔙 В меню", callback_data="main_menu")
        builder.adjust(2)
        
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"Ошибка при получении истории расходов: {e}")
        await message.answer("❌ Не удалось загрузить историю расходов")
    

@expense_history_router.callback_query(F.data.startswith("expenses_page_")) # Обработчик callback-запросов для пагинации
async def paginate_expenses(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    await show_expenses_page(call.message, call.from_user.id, page)
    await call.answer()