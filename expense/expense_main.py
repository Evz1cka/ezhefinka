import re

from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery
from datetime import datetime, date, time
from expense.category import get_available_categories, PREDEFINED_CATEGORIES
from init import logging, ADMIN_ID
from db.db_main import get_pool

expense_router = Router()

# Предустановленные категории (доступны всем)

def escape_markdown(text: str) -> str:
    return re.sub(r'([_\*\[\]()~`>#+=\-|{}.!\\])', r'\\\1', text)

class ExpenseStates(StatesGroup):
    waiting_for_expense_input = State()  # Состояние для ввода расхода
    waiting_for_history_count = State()  # Состояние для истории расходов
    waiting_for_amount = State() # Состояние для ввода суммы

#endregion
#region Добавление расходов
@expense_router.callback_query(F.data == "add_expense")
async def add_expense_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await send_expense_input_prompt(call.from_user.id, call.message.edit_text, state)

async def send_expense_input_prompt(user_id: int, send_func, state: FSMContext):
    all_categories = await get_available_categories(user_id)
    custom_categories = [cat for cat in all_categories if cat not in PREDEFINED_CATEGORIES]

    # Основной текст с правильным экранированием
    text = (
        "Введите расход в формате:\n"
        "`категория сумма дата время`\n"
        "Можно добавлять сразу несколько расходов, один расход на строку\\.\n"
        "Пример:\n"
        "`Транспорт 100`\n"
        "`Продукты 200\\,20 15\\.07`\n"
        "`Кино 300\\.30 15\\.07\\.2025 20:30`\n\n"
        "*Доступные категории:*"
    )

    # Формируем список категорий с правильным экранированием
    lines = []
    for cat in PREDEFINED_CATEGORIES:
        lines.append(f"• {escape_markdown(cat)}")

    if custom_categories:
        lines.append("\n*Ваши категории:*")
        for cat in custom_categories:
            lines.append(f"• {escape_markdown(cat)}")

    category_block = "\n".join(lines)
    
    # Комбинируем текст и категории
    full_text = f"{text}\n{category_block}"

    builder = InlineKeyboardBuilder()
    builder.row_width = 1
    builder.button(text="⬅️ Вернуться в меню", callback_data="main_menu")
    keyboard = builder.as_markup()

    await send_func(
        full_text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

    await state.set_state(ExpenseStates.waiting_for_expense_input)
#endregion

#region Обработка ввода расходов
@expense_router.message(ExpenseStates.waiting_for_expense_input)
async def process_expense(message: types.Message, state: FSMContext):
    pool = get_pool()
    if not pool:
        await message.answer("❌ Внутренняя ошибка, попробуйте позже.")
        return

    lines = message.text.strip().split('\n')
    success_count = 0
    failed_entries = []

    available_categories = await get_available_categories(message.from_user.id)

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 2:
            failed_entries.append((line, "Недостаточно данных"))
            continue

        category_input = parts[0].strip()
        amount_str = parts[1].replace(',', '.')

        normalized_input = category_input.lower()
        matched_category = next((cat for cat in available_categories if cat.lower() == normalized_input), None)

        if not matched_category:
            failed_entries.append((line, "Категория не найдена"))
            continue

        try:
            amount = float(amount_str)
        except ValueError:
            failed_entries.append((line, "Неверный формат суммы"))
            continue

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
                    raise ValueError()
                date_obj = datetime(year, month, day).date()

            if len(parts) >= 4 and ':' in parts[3]:
                time_obj = datetime.strptime(parts[3], '%H:%M').time()
        except Exception:
            failed_entries.append((line, "Неверный формат даты или времени"))
            continue

        try:
            if time_obj:
                await pool.execute(
                    "INSERT INTO expenses (user_id, category, amount, date, time) VALUES ($1, $2, $3, $4, $5)",
                    message.from_user.id, matched_category, amount, date_obj, time_obj
                )
            else:
                await pool.execute(
                    "INSERT INTO expenses (user_id, category, amount, date) VALUES ($1, $2, $3, $4)",
                    message.from_user.id, matched_category, amount, date_obj
                )
            success_count += 1
        except Exception:
            failed_entries.append((line, "Ошибка при сохранении"))

    # Ответ пользователю
    response = f"✅ Добавлено расходов: {success_count}\n"
    if failed_entries:
        response += "\n❌ Ошибки:\n"
        for entry, reason in failed_entries:
            # Экранируем каждый элемент отдельно
            escaped_entry = escape_markdown(entry)
            escaped_reason = escape_markdown(reason)
            response += f"\\- `{escaped_entry}` \\- {escaped_reason}\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="main_menu")]]
    )

    await message.answer(response, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
#endregion
#region Проверка на дубликаты
async def is_duplicate_expense(
    user_id: int,
    category: str,
    amount: float,
    date_obj: date,
    time_obj: time | None = None
) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        if time_obj:
            result = await conn.fetchval(
                """
                SELECT 1 FROM expenses
                WHERE user_id = $1 AND category = $2 AND amount = $3 AND date = $4 AND time = $5
                LIMIT 1
                """,
                user_id, category, amount, date_obj, time_obj
            )
        else:
            result = await conn.fetchval(
                """
                SELECT 1 FROM expenses
                WHERE user_id = $1 AND category = $2 AND amount = $3 AND date = $4 AND time IS NULL
                LIMIT 1
                """,
                user_id, category, amount, date_obj
            )

        return result is not None
#endregion

