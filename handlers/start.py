
from aiogram import F, types, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    CallbackQuery,
    ReplyKeyboardRemove,

)
import asyncpg
from datetime import timedelta

from db.db_main import get_pool
start_router = Router()

@start_router.message(Command("testdate"))
async def test_date(message: types.Message):
    pool = get_pool()
    try:
        await message.answer("Переключаюсь на inline-кнопки", reply_markup=ReplyKeyboardRemove())
        current = await pool.fetchval("SELECT CURRENT_DATE")
        week_ago = current - timedelta(days=7)
        month_start = current.replace(day=1)
        await message.answer(
            f"Текущая дата в БД: {current}\n"
            f"Неделю назад: {week_ago}\n"
            f"Начало месяца: {month_start}"
        )
    except asyncpg.exceptions.UndefinedFunctionError as e:
        await message.answer(f"Ошибка: {e}")


@start_router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()  # Очищаем состояние
    
    #await get_or_create_user(message.from_user) # Регистрируем/обновляем пользователя
    # Создаем inline-клавиатуру
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="show_stats_menu"
        ),
        types.InlineKeyboardButton(
            text="📝 История расходов",
            callback_data="expenses_history"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="➕ Добавить расход",
            callback_data="add_expense"
            
        ),
        types.InlineKeyboardButton(
            text="🗑️ Удалить запись",
            callback_data="delete_expense"
        )
        )
    builder.row(
        types.InlineKeyboardButton(
            text="👤 Профиль",
            callback_data="profile"
            
        ),
        types.InlineKeyboardButton(
            text="⚙️ Настройки",
            callback_data="settings"
            
        )
        )
    builder.row(
        types.InlineKeyboardButton(
            text="ℹ️ Помощь",
            callback_data="show_help"
        )
        )
    text=(
        "👋 <b>Привет! Я бот Ежефинка 🍇</b>\n\n"
        "Я помогу вам вести учет расходов:\n"
        "• Добавлять траты в разных категориях\n"
        "• Смотреть статистику за период\n"
        "• Управлять историей ваших расходов\n\n"
        "Выберите действие:"
        )
    
    try:
        await message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=builder.as_markup()
        )
    

@start_router.callback_query(F.data == "show_help")
async def show_help(call: CallbackQuery):
    help_text = (
        "ℹ️ <b>Справка по использованию бота</b>\n\n"
        "<b>Добавление расходов:</b>\n"
        "Формат: <code>Категория Сумма Дата Время</code>\n"
        "Можно добавлять сразу несколько расходов, один расход на строку."
        "Пример:\n"
        "<code>Транспорт 100</code>\n"
        "<code>Продукты 200,20 15.07</code>\n"
        "<code>Кино 300.30 15.07.2025 20:30</code>\n\n"
        "<b>Статистика:</b>\n"
        "• Просмотр за разные периоды\n"
        "• Анализ по категориям\n"
        "• Графики расходов\n\n"
        "<b>История:</b>\n"
        "• Поиск по дате/категории/цене\n"
        "• Редактирование записей (пока не реализовано)\n"
        "• Экспорт данных (пока не реализовано)\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="main_menu")
    
    await call.message.edit_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@start_router.callback_query(F.data == "settings")
async def settings_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⏰ Напоминания", callback_data="reminders"),
        types.InlineKeyboardButton(text="💰 Бюджеты", callback_data="budgets")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 Категории", callback_data="categories"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )
    
    await call.message.edit_text(
        "⚙️ <b>Настройки бота</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@start_router.callback_query(F.data == "main_menu")
async def back_to_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text()
    except:
        pass
    await start(call.message, state)
    await call.answer()
    