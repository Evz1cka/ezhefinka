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
from datetime import timedelta, date, datetime
import asyncpg  # для работы с базой данных 
from init import logging  # твой модуль для логов
from db.db_main import get_pool  # функция для получения пула подключения к базе

# Создаем роутер для обработки удаления расходов
expense_history_router = Router()

EXPENSES_PER_PAGE = 5  # Количество расходов на одной странице

class SearchExpenses(StatesGroup):
    waiting_for_query = State()
class PeriodHistory(StatesGroup):
    waiting_for_custom_period = State()

@expense_history_router.callback_query(F.data == "expenses_by_period")
async def expenses_by_period_menu(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📅 За сегодня", callback_data="history_period_today"),
        types.InlineKeyboardButton(text="🗓 За неделю", callback_data="history_period_week")
    )
    builder.row(
        types.InlineKeyboardButton(text="📆 За месяц", callback_data="history_period_month"),
        types.InlineKeyboardButton(text="✏️ Выбрать свой", callback_data="history_period_custom")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="expenses_history"))
    
    await callback.message.edit_text(
        "📅 <b>Выберите период</b> для просмотра расходов:",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@expense_history_router.callback_query(F.data.startswith("history_period_"))
async def show_period_expenses(callback: CallbackQuery):
    user_id = callback.from_user.id
    today = date.today()
    
    if callback.data == "history_period_today":
        start_date = end_date = today
    elif callback.data == "history_period_week":
        start_date = today - timedelta(days=7)
        end_date = today
    elif callback.data == "history_period_month":
        start_date = today.replace(day=1)
        end_date = today
    elif callback.data == "history_period_custom":
        await callback.message.edit_text(
            "✏️ Введите диапазон в формате:\n<code>ДД.ММ.ГГГГ - ДД.ММ</code>\n\n"
            "Пример: <code>13.11.2024 - 22.05</code>",
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return await callback.bot.fsm.set_state(callback.from_user.id, PeriodHistory.waiting_for_custom_period)

    await show_expenses_in_period(callback.message, user_id, start_date, end_date)
    await callback.answer()

@expense_history_router.message(PeriodHistory.waiting_for_custom_period)
async def handle_custom_period(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        parts = message.text.strip().split("-")
        start_str = parts[0].strip()
        end_str = parts[1].strip()

        start_date = datetime.strptime(start_str, "%d.%m.%Y").date()
        end_date = datetime.strptime(end_str + f".{start_date.year}", "%d.%m.%Y").date()

        if end_date < start_date:
            raise ValueError("Конечная дата раньше начальной.")

        await show_expenses_in_period(message, user_id, start_date, end_date)
        await state.clear()

    except Exception as e:
        logging.warning(f"Ошибка при парсинге периода: {e}")
        await message.answer("❌ Неверный формат. Введите, например:\n<code>13.11.2024 - 22.05</code>",
                             parse_mode=ParseMode.HTML)


async def show_expenses_in_period(message: types.Message, user_id: int, start_date: date, end_date: date):
    pool = get_pool()
    try:
        expenses = await pool.fetch(
            "SELECT id, category, amount, date, time FROM expenses "
            "WHERE user_id = $1 AND date BETWEEN $2 AND $3 "
            "ORDER BY date DESC, (time IS NULL), time DESC, created_at DESC",
            user_id, start_date, end_date
        )

        if not expenses:
            await message.answer("📭 За этот период нет записей о расходах.")
            return

        text = (
            f"📅 <b>Расходы с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}</b>\n"
            f"📊 Всего: <b>{len(expenses)}</b>\n\n"
        )

        for i, expense in enumerate(expenses, 1):
            date_str = expense['date'].strftime('%d.%m.%Y')
            time_str = f" {expense['time'].strftime('%H:%M')}" if expense['time'] else ""
            text += (
                f"<b>#{i}</b> | 🆔 <code>{expense['id']}</code>\n"
                f"📅 <b>{date_str}{time_str}</b>\n"
                f"🏷 {expense['category']}: <b>{expense['amount']:.2f} ₽</b>\n\n"
            )

        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data="expenses_by_period")
        builder.button(text="🏠 В меню", callback_data="main_menu")
        builder.adjust(2)

        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
    
    except Exception as e:
        logging.error(f"Ошибка показа расходов за период: {e}")
        await message.answer("❌ Не удалось загрузить данные.")


@expense_history_router.callback_query(F.data == "expenses_history")
async def expenses_history_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📅 Последние", callback_data="expenses_recent"),
        types.InlineKeyboardButton(text="🔍 Поиск", callback_data="expenses_search")
    ) 

    builder.row(
        types.InlineKeyboardButton(text="🗂 По категориям", callback_data="expenses_by_category"),
        types.InlineKeyboardButton(text="📆 По периоду", callback_data="expenses_by_period"),
    )
    
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu") 
    )
    await call.message.edit_text(
        "📝 <b>История расходов</b>\nВыберите способ просмотра:",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@expense_history_router.callback_query(F.data == "expenses_search")
async def start_search_expenses(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔍 Введите поисковый запрос.\n"
        "Можно искать по категории или дате (в формате ДД.ММ.ГГГГ) или по сумме."
    )
    await state.set_state(SearchExpenses.waiting_for_query)
    await callback.answer()

@expense_history_router.message(SearchExpenses.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    query = message.text.strip()
    user_id = message.from_user.id

    # Сохраним запрос и сбросим страницу на 1
    await state.update_data(search_query=query, page=1)

    await show_search_results(message, user_id, query, 1)

    await state.clear()  # если не нужна пагинация по страницам, иначе не очищать

async def show_search_results(message: Message, user_id: int, query: str, page: int):
    pool = get_pool()

    try:

        params = [user_id]
        conditions = ["user_id = $1"]
        idx = 2

        # Попытка распарсить дату
        date_filter = None
        try:
            date_filter = datetime.strptime(query, "%d.%m.%Y").date()
        except:
            pass

        # Попытка распарсить сумму
        amount_filter = None
        try:
            amount_filter = float(query.replace(",", "."))
        except:
            pass

        or_conditions = []
        if date_filter:
            or_conditions.append(f"date = ${idx}")
            params.append(date_filter)
            idx += 1

        if amount_filter is not None:
            or_conditions.append(f"(amount >= ${idx} AND amount < ${idx + 1})")
            params.append(amount_filter)
            params.append(amount_filter + 1)
            idx += 2

        or_conditions.append(f"category ILIKE ${idx}")
        params.append(f"%{query}%")
        idx += 1

        # Формируем часть с OR
        or_sql = " OR ".join(or_conditions)

        # Собираем полный WHERE
        where_sql = " AND ".join(conditions + [f"({or_sql})"])

        # Подсчёт общего количества записей
        count_sql = f"SELECT COUNT(*) FROM expenses WHERE {where_sql}"
        total_expenses = await pool.fetchval(count_sql, *params)

        if total_expenses == 0:
            await message.answer("❌ По вашему запросу ничего не найдено.")
            return

        total_pages = max((total_expenses - 1) // EXPENSES_PER_PAGE + 1, 1)
        offset = (page - 1) * EXPENSES_PER_PAGE

        query_sql = (
            f"SELECT id, category, amount, date, time FROM expenses "
            f"WHERE {where_sql} "
            f"ORDER BY date DESC, (time IS NULL), time DESC, created_at DESC "
            f"LIMIT {EXPENSES_PER_PAGE} OFFSET {offset}"
        )

        expenses = await pool.fetch(query_sql, *params)

        text = (
            f"🔍 <b>Результаты поиска</b> (страница {page}/{total_pages})\n"
            f"📊 Всего найдено: <b>{total_expenses}</b>\n\n"
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
            builder.button(text="⬅️ Назад", callback_data=f"search_expenses_page_{page-1}_{query}")
        if page < total_pages:
            builder.button(text="Вперед ➡️", callback_data=f"search_expenses_page_{page+1}_{query}")
        builder.button(text="🔙 В меню", callback_data="main_menu")
        builder.adjust(2)

        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"Ошибка поиска расходов: {e}")
        await message.answer("❌ Произошла ошибка при поиске расходов.")


@expense_history_router.callback_query(F.data.startswith("search_expenses_page_"))
async def paginate_search_expenses(call: CallbackQuery):
    # Данные формата: search_expenses_page_{page}_{query}
    try:
        _, _, page_str, *query_parts = call.data.split("_")
        page = int(page_str)
        query = "_".join(query_parts)  # т.к. query может содержать _
        user_id = call.from_user.id

        # Показываем результаты на нужной странице
        await show_search_results(call.message, user_id, query, page)
        await call.answer()
    except Exception as e:
        logging.error(f"Ошибка пагинации поиска: {e}")
        await call.answer("❌ Ошибка при пагинации поиска.")

@expense_history_router.callback_query(F.data == "expenses_by_category")
async def expenses_history_categories(callback: CallbackQuery):
    user_id = callback.from_user.id
    pool = get_pool()
    
    try:
        categories = await pool.fetch(
            "SELECT DISTINCT category FROM expenses WHERE user_id = $1 ORDER BY category",
            user_id
        )
        
        if not categories:
            await callback.message.edit_text("❌ У вас ещё нет добавленных категорий.")
            return

        builder = InlineKeyboardBuilder()
        for cat in categories:
            builder.button(
                text=cat['category'],
                callback_data=f"category_page_{cat['category']}_1"
            )
        builder.button(text="🔙 Назад", callback_data="expenses_history")
        builder.adjust(2,1)

        await callback.message.edit_text(
            "📂 <b>Выберите категорию</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logging.error(f"Ошибка при получении категорий: {e}")
        await callback.message.answer("❌ Не удалось загрузить категории.")

async def show_category_expenses_page(message: types.Message, user_id: int, category: str, page: int):
    pool = get_pool()
    
    try:
        total_expenses = await pool.fetchval(
            "SELECT COUNT(*) FROM expenses WHERE user_id = $1 AND category = $2",
            user_id, category
        ) or 0

        if total_expenses == 0:
            await message.edit_text(f"📭 В категории <b>{category}</b> пока нет расходов.", parse_mode=ParseMode.HTML)
            return

        total_pages = max((total_expenses - 1) // EXPENSES_PER_PAGE + 1, 1)
        offset = (page - 1) * EXPENSES_PER_PAGE

        expenses = await pool.fetch(
            "SELECT id, amount, date, time FROM expenses "
            "WHERE user_id = $1 AND category = $2 "
            "ORDER BY date DESC, (time IS NULL), time DESC, created_at DESC "
            "LIMIT $3 OFFSET $4",
            user_id, category, EXPENSES_PER_PAGE, offset
        )

        text = (
            f"📂 <b>Категория:</b> <i>{category}</i>\n"
            f"📝 Страница {page}/{total_pages}\n"
            f"📊 Всего записей: <b>{total_expenses}</b>\n\n"
        )

        for i, expense in enumerate(expenses, 1):
            date_str = expense['date'].strftime('%d.%m.%Y')
            time_str = f" {expense['time'].strftime('%H:%M')}" if expense['time'] else ""
            text += (
                f"<b>#{i + (page-1)*EXPENSES_PER_PAGE}</b> | 🆔 <code>{expense['id']}</code>\n"
                f"📅 <b>{date_str}{time_str}</b>\n"
                f"💰 <b>{expense['amount']:.2f} ₽</b>\n\n"
            )

        builder = InlineKeyboardBuilder()
        if page > 1:
            builder.button(
                text="⬅️ Назад",
                callback_data=f"category_page_{category}_{page - 1}"
            )
        if page < total_pages:
            builder.button(
                text="Вперед ➡️",
                callback_data=f"category_page_{category}_{page + 1}"
            )
        builder.button(text="📂 Все категории", callback_data="expenses_by_category")
        builder.button(text="🏠 В меню", callback_data="main_menu")
        builder.adjust(2)

        await message.edit_text(
            text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup()
        )

    except Exception as e:
        logging.error(f"Ошибка при выводе расходов по категории: {e}")
        await message.answer("❌ Не удалось получить данные по категории.")

@expense_history_router.callback_query(F.data.startswith("category_page_"))
async def paginate_category_expenses(callback: CallbackQuery):
    try:
        # category_page_{category}_{page}
        parts = callback.data.split("_")
        category = "_".join(parts[2:-1])  # Чтобы учесть _ в названии категории
        page = int(parts[-1])
        user_id = callback.from_user.id

        await show_category_expenses_page(callback.message, user_id, category, page)
        await callback.answer()

    except Exception as e:
        logging.error(f"Ошибка при пагинации расходов по категории: {e}")
        await callback.answer("❌ Ошибка при загрузке страницы.")

@expense_history_router.callback_query(F.data.startswith("category_history_"))
async def show_expenses_by_category(callback: CallbackQuery):
    data_parts = callback.data.split("category_history_")
    if len(data_parts) < 2:
        await callback.answer("Некорректная категория.", show_alert=True)
        return

    category = data_parts[1]
    user_id = callback.from_user.id
    pool = get_pool()

    try:
        expenses = await pool.fetch(
            "SELECT id, amount, date, time FROM expenses "
            "WHERE user_id = $1 AND category = $2 "
            "ORDER BY date DESC, (time IS NULL), time DESC, created_at DESC",
            user_id,
            category
        )

        if not expenses:
            await callback.message.edit_text(f"📭 Нет расходов в категории <b>{category}</b>.", parse_mode=ParseMode.HTML)
            return

        text = f"📂 <b>Расходы по категории</b> <i>{category}</i>:\n\n"

        for i, expense in enumerate(expenses, 1):
            date_str = expense['date'].strftime('%d.%m.%Y')
            time_str = f" {expense['time'].strftime('%H:%M')}" if expense['time'] else ""
            text += (
                f"<b>#{i}</b> | 🆔 <code>{expense['id']}</code>\n"
                f"📅 <b>{date_str}{time_str}</b>\n"
                f"💰 <b>{expense['amount']:.2f} ₽</b>\n\n"
            )

        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад", callback_data="expenses_by_category")
        builder.button(text="🏠 В меню", callback_data="main_menu")
        builder.adjust(1)

        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

    except Exception as e:
        logging.error(f"Ошибка при выводе расходов по категории: {e}")
        await callback.message.answer("❌ Не удалось получить данные по категории.")


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