import os
import re

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,

)
import asyncpg
from datetime import datetime, date, time, timedelta

from init import logging, ADMIN_ID
from db.db_main import get_pool

expense_router = Router()

# Предустановленные категории (доступны всем)
PREDEFINED_CATEGORIES = [
    "Продукты", "Жильё", "Связь и интернет", "Транспорт", "Здоровье",
    "Одежда и обувь", "Красота и уход", "Развлечения", "Образование",
    "Дом/ремонт", "Путешествия", "Подарки и праздники", "Неожиданные траты"
]

MAX_CUSTOM_CATEGORIES = 5  # лимит пользовательских категорий

def escape_markdown(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

class ExpenseStates(StatesGroup):
    waiting_for_expense_input = State()  # Состояние для ввода расхода
    waiting_for_history_count = State()  # Состояние для истории расходов
    waiting_for_amount = State() # Состояние для ввода суммы
    waiting_for_new_category = State()  # ← новое состояние
    
async def get_available_categories(user_id: int) -> list[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        # Получаем пользовательские категории из user_categories
        user_custom = await conn.fetch(
            "SELECT category FROM user_categories WHERE user_id = $1",
            user_id
        )
        custom = [r['category'] for r in user_custom]

        if user_id == ADMIN_ID:
            # У администратора сначала кастомные, потом предустановленные
            return custom + PREDEFINED_CATEGORIES
        else:
            # У обычных — сначала предустановленные, потом кастомные
            return PREDEFINED_CATEGORIES + custom

async def get_user_categories(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT category FROM expenses WHERE user_id = $1",
            user_id
        )
        return [row["category"] for row in rows]

@expense_router.callback_query(F.data == "add_category")
async def prompt_new_category(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Введите название новой категории:")
    await state.set_state(ExpenseStates.waiting_for_new_category)

@expense_router.message(ExpenseStates.waiting_for_new_category)
async def save_new_category(message: types.Message, state: FSMContext):
    new_cat = message.text.strip().title()
    user_id = message.from_user.id

    if new_cat in PREDEFINED_CATEGORIES:
        await message.answer("❌ Эта категория уже есть в стандартном списке.")
        await state.clear()
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        # Проверяем, сколько у пользователя кастомных категорий
        count_custom = await conn.fetchval(
            "SELECT COUNT(*) FROM user_categories WHERE user_id = $1",
            user_id
        )

        if user_id != ADMIN_ID and count_custom >= MAX_CUSTOM_CATEGORIES:
            await message.answer("❌ Вы достигли лимита из 5 пользовательских категорий.")
            await state.clear()
            return

        # Проверяем, есть ли такая категория уже у пользователя
        exists = await conn.fetchval(
            "SELECT 1 FROM user_categories WHERE user_id = $1 AND LOWER(category) = LOWER($2)",
            user_id, new_cat
        )
        if exists:
            await message.answer("❌ Такая категория уже существует.")
            await state.clear()
            return

        # Добавляем новую категорию в user_categories
        await conn.execute(
            "INSERT INTO user_categories (user_id, category) VALUES ($1, $2)",
            user_id, new_cat
        )
    # Клавиатура с кнопкой "Добавить расходы"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Добавить расходы", callback_data="add_expense")
            ]
        ]
    )
    await message.answer(f"✅ Категория «{new_cat}» добавлена! Теперь вы можете использовать её.", reply_markup=keyboard)
    await state.clear()

@expense_router.callback_query(F.data == "add_expense")
async def add_expense_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await send_expense_input_prompt(call.from_user.id, call.message.edit_text, state)


async def send_expense_input_prompt(user_id: int, send_func, state: FSMContext):
    all_categories = await get_available_categories(user_id)
    custom_categories = [cat for cat in all_categories if cat not in PREDEFINED_CATEGORIES]

    text = (
        "Введите расход в формате:\n"
        "*категория* *сумма* [дата] [время]\n"
        "Пример:\n"
        "`Такси 300`\n"
        "`Еда 500 20.05`\n"
        "`Кино 800 20.05 19:30`\n\n"
        "*Доступные категории:*"
    )

    lines = []
    for cat in PREDEFINED_CATEGORIES:
        lines.append(f"• {escape_markdown(cat)}")  # без version=2

    if custom_categories:
        lines.append("\n*Ваши категории:*")
        for cat in custom_categories:
            lines.append(f"• {escape_markdown(cat)}")

    category_block = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    builder.row_width = 1
    builder.button(text="⬅️ Вернуться в меню", callback_data="main_menu")
    keyboard = builder.as_markup()

    await send_func(
        f"{text}\n{category_block}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

    await state.set_state(ExpenseStates.waiting_for_expense_input)

@expense_router.message(ExpenseStates.waiting_for_expense_input)
async def process_expense(message: types.Message, state: FSMContext):
    pool = get_pool()
    if not pool:
        await message.answer("❌ Внутренняя ошибка, попробуйте позже.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Укажите категорию и сумму.")
        return

    category_input = parts[0].strip()
    amount_str = parts[1].replace(',', '.')

    # Получаем все доступные категории
    available = await get_available_categories(message.from_user.id)

    # Ищем соответствие по нижнему регистру, но сохраняем оригинальную запись
    normalized_input = category_input.lower()
    matched_category = None
    for cat in available:
        if cat.lower() == normalized_input:
            matched_category = cat  # Сохраняем правильное написание
            break

    if matched_category is None:
        add_category_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Добавить новую категорию", callback_data="add_category")
        ]])
        await message.answer(
            f"❌ Категория *{escape_markdown(category_input)}* не найдена среди доступных\.\n"
            f"Пожалуйста, выберите из списка или добавьте новую\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=add_category_kb
        )
        return

    category = matched_category  # теперь это правильный вариант категории


    try:
        amount = float(amount_str)
    except ValueError:
        await message.answer("❌ Неверный формат суммы. Введите число, например: 300 или 300.50")
        return

    # Дата и время по умолчанию
    date_obj = datetime.utcnow().date()
    time_obj = None

    try:
        if len(parts) >= 3 and '.' in parts[2]:
            date_parts = parts[2].split('.')
            if len(date_parts) == 2:
                day, month = map(int, date_parts)
                year = datetime.now().year
            elif len(date_parts) == 3:
                day, month, year = map(int, date_parts)
            else:
                raise ValueError("Неверный формат даты")

            date_obj = datetime(year, month, day).date()

        if len(parts) >= 4 and ':' in parts[3]:
            time_obj = datetime.strptime(parts[3], '%H:%M').time()

    except Exception:
        await message.answer("❌ Неверный формат даты или времени.\n"
                             "Дата должна быть в формате ДД.ММ или ДД.ММ.ГГГГ.\n"
                             "Время — в формате ЧЧ:ММ.")
        return

    # Вставка в базу
    try:
        # Вставка в базу
        if time_obj is None:
            await pool.execute(
                "INSERT INTO expenses (user_id, category, amount, date) VALUES ($1, $2, $3, $4)",
                message.from_user.id, category, amount, date_obj
            )
        else:
            await pool.execute(
                "INSERT INTO expenses (user_id, category, amount, date, time) VALUES ($1, $2, $3, $4, $5)",
                message.from_user.id, category, amount, date_obj, time_obj
            )
    except Exception as e:
        await message.answer("❌ Ошибка при сохранении в базу. Попробуйте позже.")
        return

    await message.answer(f"✅ Добавлено: {category} - {amount:.2f} ₽")

    # Удаляем предыдущее сообщение с подсказкой, если есть
    data = await state.get_data()
    last_msg_id = data.get("last_hint_message_id")
    if last_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_msg_id)
        except Exception:
            pass  # Если не удалось удалить — просто игнорируем

    # Клавиатура для следующего действия
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Готово", callback_data="main_menu"),
        ]]
    )

    sent_msg = await message.answer(
        "Добавьте ещё расходы или нажмите кнопку 'Готово'",
        reply_markup=keyboard
    )

    # Сохраняем ID этого сообщения в FSM для будущего удаления
    await state.update_data(last_hint_message_id=sent_msg.message_id)

#endregion
