import re  # для экранирования символов Markdown
from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import asyncpg  # для работы с базой данных
from init import logging  # твой модуль для логов
from db.db_main import get_pool  # функция для получения пула подключения к базе

# Создаем роутер для обработки удаления расходов
expense_delete_router = Router()

# Определяем состояния для FSM (машины состояний)
class DeleteExpenseStates(StatesGroup):
    waiting_for_delete_id = State()  # Ждем ID записи для удаления
    waiting_for_delete_confirmation = State()  # Ждем подтверждения удаления

def escape_markdown(text: str) -> str:
    # Экранируем символы, которые могут нарушить Markdown в Telegram
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

@expense_delete_router.callback_query(lambda c: c.data == "delete_expense")
async def delete_expense_callback(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await delete_expense_start(call.from_user.id, call.message, state)

async def delete_expense_start(user_id: int, message: types.Message, state: FSMContext):
    pool = get_pool()

    try:
        expenses = await pool.fetch(
            "SELECT id, category, amount, date FROM expenses "
            "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 5",
            user_id
        )

        if not expenses:
            await message.answer("Нет последних записей для удаления.")
            return

        # Формируем текст с расходами, экранируем спецсимволы
        expenses_list = "\n".join(
            [f"{e['id']}: {escape_markdown(e['category'])} {e['amount']} ₽ ({e['date']})"
             for e in expenses]
        )

        # Инлайн-кнопка отмены
        cancel_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])

        await message.edit_text(
            f"Последние записи (укажите ID для удаления, если хотите удалить несколько, укажите все ID через пробел):\n{expenses_list}\n\n"
            "Нажмите кнопку ниже, чтобы отменить.",
            reply_markup=cancel_inline_kb
        )

        await state.set_state(DeleteExpenseStates.waiting_for_delete_id)

    except asyncpg.PostgresError as e:
        logging.error(f"Database error: {e}")
        await message.answer("❌ Ошибка при получении данных из базы данных.")

@expense_delete_router.message(DeleteExpenseStates.waiting_for_delete_id)
async def process_delete_expense(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Удаление отменено")
        await state.clear()
        return

    # Разбираем строку на ID, ожидаем числа через пробел
    id_strings = message.text.strip().split()
    try:
        expense_ids = list(set(int(x) for x in id_strings))  # Уникальные числа
    except ValueError:
        await message.answer("❌ Введите корректные ID записей через пробел (например: 29 28 27) или нажмите 'Отмена'")
        return

    if not expense_ids:
        await message.answer("❌ Список ID пуст. Введите хотя бы один ID или нажмите 'Отмена'.")
        return

    db_pool = get_pool()

    # Проверяем, что все записи существуют и принадлежат пользователю
    rows = await db_pool.fetch(
        "SELECT id, category, amount, date FROM expenses WHERE id = ANY($1) AND user_id = $2",
        expense_ids,
        message.from_user.id
    )

    if not rows or len(rows) != len(expense_ids):
        await message.answer("❌ Некоторые записи не найдены или не принадлежат вам. Проверьте список ID.")
        return

    # Сохраняем ID и детали для подтверждения
    await state.update_data(expense_ids=expense_ids, expense_rows=rows)

    # Формируем список для подтверждения
    expenses_list = "\n".join(
    [f"{e['id']}: {escape_markdown(e['category'])} {e['amount']} ₽ ({e['date']})" for e in rows]
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete_yes"),
        InlineKeyboardButton(text="❌ Нет, отменить", callback_data="confirm_delete_no")
    )
    keyboard = builder.as_markup()

    await message.answer(
        f"Вы уверены, что хотите удалить следующие записи?\n\n{expenses_list}",
        reply_markup=keyboard
    )

    await state.set_state(DeleteExpenseStates.waiting_for_delete_confirmation)

@expense_delete_router.callback_query(DeleteExpenseStates.waiting_for_delete_confirmation)
async def confirm_delete_callback(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if call.data == "confirm_delete_yes":
        expense_ids = data.get('expense_ids')
        if not expense_ids:
            await call.message.answer("Ошибка: не найдены ID записей")
            await state.clear()
            await call.answer()
            return

        db_pool = get_pool()
        try:
            result = await db_pool.execute(
                "DELETE FROM expenses WHERE id = ANY($1) AND user_id = $2",
                expense_ids,
                call.from_user.id
            )
            # result возвращает строку вида "DELETE X"
            count_deleted = int(result.split()[1])
            if count_deleted == 0:
                await call.message.answer("❌ Записи не найдены или уже удалены")
            else:
                await call.message.edit_text(f"✅ Успешно удалено {count_deleted} записей")
        except asyncpg.PostgresError as e:
            logging.error(f"Database error: {e}")
            await call.message.answer("❌ Ошибка при удалении записей из базы данных")

        await state.clear()
        await call.answer()

    elif call.data == "confirm_delete_no":
        await call.message.answer("Удаление отменено")
        await state.clear()
        await call.answer()
