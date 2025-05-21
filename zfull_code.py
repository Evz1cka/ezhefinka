import os
from aiogram import Bot, Dispatcher, types, F
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
import asyncpg
from datetime import datetime, date, time, timedelta
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота
bot = Bot(
    token=os.getenv("BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Состояния для FSM
class ExpenseStates(StatesGroup):
    waiting_for_expense_input = State()  # Состояние для ввода расхода
    waiting_for_delete_id = State()  # Состоние для удаления записи
    waiting_for_history_count = State()  # Состояние для истории расходов
    waiting_for_delete_confirmation = State()
    waiting_for_amount = State() # Состояние для ввода суммы

class ReminderStates(StatesGroup):
    waiting_for_reminder_time = State()
    waiting_for_reminder_text = State()

class BudgetStates(StatesGroup):
    waiting_for_budget_category = State()
    waiting_for_budget_amount = State()

@dp.callback_query(F.data == "settings")
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

#region Тестовые функции
@dp.message(Command("debug"))
async def debug_cmd(message: types.Message):
    conn = await get_db_connection()
    try:
        data = await conn.fetch("SELECT * FROM expenses")
        await message.answer(f"Всего записей: {len(data)}\nПример: {dict(data[0])}")
    finally:
        await conn.close()

@dp.message(Command("testdate"))
async def test_date(message: types.Message):
    conn = await get_db_connection()
    try:
        current = await conn.fetchval("SELECT CURRENT_DATE")
        week_ago = current - timedelta(days=7)
        month_start = current.replace(day=1)
        await message.answer(
            f"Текущая дата в БД: {current}\n"
            f"Неделю назад: {week_ago}\n"
            f"Начало месяца: {month_start}"
        )
    finally:
        await conn.close()
#endregion
#region Работа с базой данных
async def get_db_connection():
    return await asyncpg.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        host=os.getenv("DB_HOST")
    )

async def create_table():   # Создание таблицы при запуске
    conn = await get_db_connection()
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                category VARCHAR(50) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'RUB',
                date DATE NOT NULL DEFAULT CURRENT_DATE,
                time TIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    finally:
        await conn.close()
#endregion
#region Основные команды
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()  # Очищаем состояние
    
    # Создаем inline-клавиатуру
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="➕ Добавить расход",
            callback_data="add_expense"
        ),
        types.InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="show_stats_menu"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🗑️ Удалить запись",
            callback_data="delete_expense"
        ),
        types.InlineKeyboardButton(
            text="📝 История расходов",
            callback_data="expenses_history"
        )
    )
    
    await message.answer(
        "👋 <b>Привет! Я бот Ежефинка 🍇</b>\n\n"
        "Я помогу вам вести учет расходов:\n"
        "• Добавлять траты в разных категориях\n"
        "• Смотреть статистику за период\n"
        "• Управлять историей ваших расходов\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await start(call.message, state)
    await call.answer()

@dp.message(lambda message: message.text == "Назад") # Обработка кнопки "Назад"
async def back_to_main(message: types.Message, state: FSMContext):
    # Полностью сбрасываем состояние
    await state.clear()
    
    # Возвращаем главное меню
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Добавить расход"))
    builder.add(types.KeyboardButton(text="Статистика"))
    builder.add(types.KeyboardButton(text="Удалить запись"))
    builder.add(types.KeyboardButton(text="История расходов"))
    
    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await start(message, state)
    await message.answer("Действие отменено")

# 6. Добавлена система помощи
@dp.callback_query(F.data == "show_help")
async def show_help(call: CallbackQuery):
    help_text = (
        "ℹ️ <b>Справка по использованию бота</b>\n\n"
        "<b>Добавление расходов:</b>\n"
        "Формат: <code>Категория Сумма [Дата] [Время]</code>\n"
        "Примеры:\n"
        "<code>Такси 350</code>\n"
        "<code>Еда 500 15.07</code>\n"
        "<code>Кино 800 15.07 20:30</code>\n\n"
        "<b>Статистика:</b>\n"
        "• Просмотр за разные периоды\n"
        "• Анализ по категориям\n"
        "• Графики расходов\n\n"
        "<b>История:</b>\n"
        "• Поиск по дате/категории\n"
        "• Редактирование записей\n"
        "• Экспорт данных\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="main_menu")
    
    await call.message.edit_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

#endregion
#region Добавление расходов
'''
@dp.callback_query(F.data == "add_expense") # Обработчики для inline-кнопок
async def add_expense_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await add_expense_start(call.message, state)
'''
@dp.callback_query(F.data == "add_expense")
async def add_expense_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    
    builder = InlineKeyboardBuilder()
    categories = ["Еда", "Транспорт", "Развлечения", "Жилье", "Другое"]
    for category in categories:
        builder.button(text=category, callback_data=f"quick_cat_{category}")
    builder.button(text="✏️ Ввести вручную", callback_data="manual_input")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(2, 2, 1)
    
    await call.message.edit_text(
        "Выберите категорию или введите вручную:",
        reply_markup=builder.as_markup()
    )

@dp.message(lambda message: message.text == "Добавить расход") # Обработка кнопки "Добавить расход"
async def add_expense_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите расход в формате:\n"
        "*категория* *сумма* [дата] [время]\n"
        "Пример:\n`Такси 300`\n`Еда 500 20.05`\n`Кино 800 20.05 19:30`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(ExpenseStates.waiting_for_expense_input)

@dp.message(lambda message: message.text == "Добавить ещё расход")
async def add_another_expense(message: types.Message, state: FSMContext):
    # Просто перенаправляем на обработчик добавления расхода с текущим state
    await add_expense_start(message, state)

@dp.message(ExpenseStates.waiting_for_expense_input) # Обработка ввода расхода
async def process_expense(message: types.Message, state: FSMContext):
    # Если это команда "Назад" - пропускаем обработку
    if message.text == "Назад":
        await back_to_main(message, state)
        return
        
    # Остальная логика обработки расхода...
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Ошибка: нужно указать категорию и сумму")
        return
    
    try:
        category = parts[0]
        amount = float(parts[1].replace(',', '.'))
        
        # По умолчанию используем текущую дату
        date_obj = datetime.utcnow().date()
        time_obj = None
        
        # Обработка даты (форматы: 18.05 или 18.05.2025)
        if len(parts) >= 3 and '.' in parts[2]:
            date_parts = parts[2].split('.')
            day = int(date_parts[0])
            month = int(date_parts[1])
            year = int(date_parts[2]) if len(date_parts) > 2 else datetime.now().year
            date_obj = datetime(year, month, day).date()
        
        # Обработка времени (формат: 8:52)
        if len(parts) >= 4 and ':' in parts[3]:
            time_obj = datetime.strptime(parts[3], '%H:%M').time()

        conn = await get_db_connection()
        try:
            # Если время не указано, передаем NULL
            if time_obj is None:
                await conn.execute(
                    "INSERT INTO expenses (user_id, category, amount, date) "
                    "VALUES ($1, $2, $3, $4)",
                    message.from_user.id,
                    category,
                    amount,
                    date_obj
                )
            else:
                await conn.execute(
                    "INSERT INTO expenses (user_id, category, amount, date, time) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    message.from_user.id,
                    category,
                    amount,
                    date_obj,
                    time_obj
                )
            
            await message.answer(f"✅ Добавлено: {category} - {amount:.2f} ₽")
            
            # После добавления расхода снова предлагаем добавить или вернуться
            builder = ReplyKeyboardBuilder()
            builder.add(types.KeyboardButton(text="Добавить ещё расход"))
            builder.add(types.KeyboardButton(text="Назад"))
            
            await message.answer(
                "Хотите добавить ещё один расход?",
                reply_markup=builder.as_markup(resize_keyboard=True)
            )
            
        except asyncpg.PostgresError as e:
            logger.error(f"Database error: {e}")
            await message.answer("❌ Ошибка при сохранении в базу данных")
        finally:
            await conn.close()
    except ValueError as e:
        await message.answer(f"❌ Ошибка в формате данных: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.answer("❌ Произошла непредвиденная ошибка")

    # Не очищаем состояние, чтобы можно было продолжать добавлять расходы
#endregion
#region Статистика расходов
'''
@dp.callback_query(F.data == "show_stats_menu")
async def show_stats_callback(call: CallbackQuery):
    await call.answer()
    await show_stats(call.message)
'''
@dp.callback_query(F.data == "show_stats_menu")
async def show_stats_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📅 За период", callback_data="stats_period"),
        types.InlineKeyboardButton(text="🏷 По категориям", callback_data="stats_categories")
    )
    builder.row(
        types.InlineKeyboardButton(text="📈 Графики", callback_data="stats_graphs"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )
    
    await call.message.edit_text(
        "📊 <b>Выберите тип статистики:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@dp.message(lambda message: message.text == "Статистика") # Обработка кнопки "Статистика"
async def show_stats(message: types.Message):
    # Создаем клавиатуру для выбора периода
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="За сегодня"))
    builder.add(types.KeyboardButton(text="За неделю"))
    builder.add(types.KeyboardButton(text="За месяц"))
    builder.add(types.KeyboardButton(text="Назад"))
    
    await message.answer(
        "Выберите период для статистики:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@dp.message(lambda message: message.text in ["За сегодня", "За неделю", "За месяц"]) # Обработка выбора периода статистики
async def handle_stats_period(message: types.Message):
    user_id = message.from_user.id
    period = message.text

    conn = None
    try:
        conn = await get_db_connection()
        
        # Получаем текущую дату из БД
        db_now = await conn.fetchval("SELECT NOW()")
        current_date = db_now.date()
        
        # Формируем условия и параметры
        if period == "За сегодня":
            date_condition = "date = $2::date"
            params = [user_id, current_date]
            title = "📊 Статистика за сегодня"
            period_info = f"{current_date.strftime('%d.%m.%Y')}"
        elif period == "За неделю":
            week_start = current_date - timedelta(days=6)
            date_condition = "date BETWEEN $2 AND $3"
            params = [user_id, week_start, current_date]
            title = "📊 Статистика за неделю"
            period_info = f"{week_start.strftime('%d.%m.%Y')} - {current_date.strftime('%d.%m.%Y')}"
        else:  # За месяц
            month_start = current_date.replace(day=1)
            date_condition = "date BETWEEN $2 AND $3"
            params = [user_id, month_start, current_date]
            title = "📊 Статистика за месяц"
            period_info = f"{month_start.strftime('%d.%m.%Y')} - {current_date.strftime('%d.%m.%Y')}"
        
        # Запрос данных
        total = await conn.fetchval(
            f"SELECT COALESCE(SUM(amount), 0) FROM expenses "
            f"WHERE user_id = $1 AND {date_condition}",
            *params
        )
        
        stats = await conn.fetch(
            f"SELECT category, COALESCE(SUM(amount), 0) as sum FROM expenses "
            f"WHERE user_id = $1 AND {date_condition} "
            f"GROUP BY category ORDER BY sum DESC",
            *params
        )
        
        # Формируем ответ
        response = (
            f"{title}\n"
            f"Период: {period_info}\n"
            f"Общие расходы: {float(total):.2f} ₽\n\n"
        )

        if stats:
            for i, row in enumerate(stats, 1):
                response += f"{i}. {row['category']}: {row['sum']:.2f} ₽\n"
        else:
            response += "Нет данных за выбранный период\n"
            
        await message.answer(response)
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}", exc_info=True)
        await message.answer("❌ Не удалось загрузить статистику")
    finally:
        if conn:
            await conn.close()
#endregion
#region Удаление записи расходов  
@dp.callback_query(F.data == "delete_expense") # Обработчики для inline-кнопок
async def delete_expense_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await delete_expense_start(call.message, state)

@dp.message(lambda message: message.text == "Удалить запись")
async def delete_expense_start(message: types.Message, state: FSMContext):
    conn = await get_db_connection()
    try:
        # Получаем последние 5 записей пользователя
        expenses = await conn.fetch(
            "SELECT id, category, amount, date FROM expenses "
            "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 5",
            message.from_user.id
        )
        
        if not expenses:
            await message.answer("Нет последних записей для удаления")
            return
            
        # Формируем список записей
        expenses_list = "\n".join(
            [f"{e['id']}: {e['category']} {e['amount']} ₽ ({e['date']})" 
             for e in expenses]
        )
        
        # Создаем клавиатуру с кнопкой отмены
        builder = ReplyKeyboardBuilder()
        builder.add(types.KeyboardButton(text="Отмена"))
        await message.answer(
            f"Последние записи (укажите ID для удаления):\n{expenses_list}\n\n"
            "Или нажмите 'Отмена' чтобы вернуться в меню",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )
        await state.set_state(ExpenseStates.waiting_for_delete_id)
        
    finally:
        await conn.close()
    
@dp.message(ExpenseStates.waiting_for_delete_id)
async def process_delete_expense(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await state.clear()
        await start(message, state)
        return
    
    try:
        expense_id = int(message.text)
        conn = await get_db_connection()
        try:
            # Получаем данные записи для подтверждения
            expense = await conn.fetchrow(
                "SELECT category, amount, date FROM expenses WHERE id = $1 AND user_id = $2",
                expense_id, message.from_user.id
            )
            
            if not expense:
                await message.answer("❌ Запись не найдена или не принадлежит вам")
                await state.clear()
                await start(message, state)
                return
                
            # Сохраняем ID в состоянии
            await state.update_data(expense_id=expense_id)
            
            # Запрашиваем подтверждение
            builder = ReplyKeyboardBuilder()
            builder.add(types.KeyboardButton(text="Да, удалить"))
            builder.add(types.KeyboardButton(text="Нет, отменить"))
            
            await message.answer(
                f"Вы уверены, что хотите удалить запись?\n"
                f"{expense['category']} {expense['amount']} ₽ ({expense['date']})",
                reply_markup=builder.as_markup(resize_keyboard=True)
            )
            await state.set_state(ExpenseStates.waiting_for_delete_confirmation)
            
        finally:
            await conn.close()
            
    except ValueError:
        await message.answer("❌ Введите корректный ID записи (число) или нажмите 'Отмена'")

@dp.message(ExpenseStates.waiting_for_delete_confirmation) # Обработчик подтверждения
async def confirm_delete_expense(message: types.Message, state: FSMContext):
    if message.text.lower() in ["нет", "отменить", "нет, отменить"]:
        await message.answer("Удаление отменено")
        await state.clear()
        await start(message, state)
        return
        
    if message.text.lower() in ["да", "удалить", "да, удалить"]:
        data = await state.get_data()
        expense_id = data.get('expense_id')
        
        if not expense_id:
            await message.answer("Ошибка: не найден ID записи")
            await state.clear()
            await start(message, state)
            return
            
        conn = await get_db_connection()
        try:
            deleted = await conn.execute(
                "DELETE FROM expenses WHERE id = $1 AND user_id = $2",
                expense_id, message.from_user.id
            )
            
            if deleted[-1] == '0':
                await message.answer("❌ Запись не найдена")
            else:
                await message.answer("✅ Запись успешно удалена")
                
        finally:
            await conn.close()
            
        await state.clear()
        await start(message, state)
    else:
        await message.answer("Пожалуйста, выберите 'Да, удалить' или 'Нет, отменить'")
#endregion
#region История расходов
EXPENSES_PER_PAGE = 5  # Количество расходов на одной странице
'''
@dp.callback_query(F.data == "expenses_history") # Обработчики для inline-кнопок
async def expenses_history_callback(call: CallbackQuery):
    await call.answer()
    await show_expenses_page(call.message, call.from_user.id, 1)
'''
@dp.callback_query(F.data == "expenses_history")
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

@dp.message(lambda message: message.text == "История расходов") # Обработчик кнопки "История расходов"
async def show_history_start(message: types.Message):
    # Показываем первую страницу
    await show_expenses_page(message, message.from_user.id, 1)

async def show_expenses_page(message: types.Message, user_id: int, page: int):
    conn = await get_db_connection()
    try:
        total_expenses = await conn.fetchval(
            "SELECT COUNT(*) FROM expenses WHERE user_id = $1",
            user_id
        ) or 0
        
        total_pages = max((total_expenses - 1) // EXPENSES_PER_PAGE + 1, 1)
        
        expenses = await conn.fetch(
            "SELECT id, category, amount, date, time FROM expenses "
            "WHERE user_id = $1 "
            "ORDER BY date DESC, time DESC NULLS LAST, created_at DESC "
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
        
        builder.button(text="🔙 В меню", callback_data="expenses_back")
        builder.adjust(2)
        
        if page == 1:
            await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
        else:
            await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
            
    except Exception as e:
        logger.error(f"Ошибка при получении истории расходов: {e}")
        await message.answer("❌ Не удалось загрузить историю расходов")
    finally:
        if conn:
            await conn.close()

@dp.callback_query(F.data.startswith("expenses_page_")) # Обработчик callback-запросов для пагинации
async def paginate_expenses(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    await show_expenses_page(call.message, call.from_user.id, page)
    await call.answer()

@dp.callback_query(F.data == "expenses_back") # Обработчик возврата в меню
async def back_to_menu(call: CallbackQuery):
    await call.message.delete()
    await start(call.message, call.bot)
    await call.answer()
#endregion
#region Бюджеты
@dp.callback_query(F.data == "budgets")
async def budgets_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="➕ Установить бюджет", callback_data="set_budget"),
        types.InlineKeyboardButton(text="📊 Текущие бюджеты", callback_data="view_budgets")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="settings")
    )
    
    await call.message.edit_text(
        "💰 <b>Управление бюджетами</b>\n"
        "Здесь вы можете установить лимиты расходов по категориям",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )
#endregion
# Обработчики для кнопок главного меню
@dp.callback_query(F.data == "add_expense")
async def handle_add_expense(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await add_expense_start(call.message, state)

@dp.callback_query(F.data == "show_stats_menu")
async def handle_show_stats(call: CallbackQuery):
    await call.answer()
    await show_stats_menu(call)

@dp.callback_query(F.data == "expenses_history")
async def handle_expenses_history(call: CallbackQuery):
    await call.answer()
    await expenses_history_menu(call)

@dp.callback_query(F.data == "settings")
async def handle_settings(call: CallbackQuery):
    await call.answer()
    await settings_menu(call)

# Обработчики для кнопок статистики
@dp.callback_query(F.data == "stats_period")
async def handle_stats_period(call: CallbackQuery):
    await call.answer("Показываем статистику по периодам")
    # Реализуйте логику показа статистики по периодам

@dp.callback_query(F.data == "stats_categories")
async def handle_stats_categories(call: CallbackQuery):
    await call.answer("Показываем статистику по категориям")
    # Реализуйте логику показа статистики по категориям

@dp.callback_query(F.data == "stats_graphs")
async def handle_stats_graphs(call: CallbackQuery):
    await call.answer("Показываем графики")
    # Реализуйте логику показа графиков

# Обработчики для кнопок истории
@dp.callback_query(F.data == "expenses_recent")
async def handle_expenses_recent(call: CallbackQuery):
    await call.answer()
    await show_expenses_page(call.message, call.from_user.id, 1)

@dp.callback_query(F.data == "expenses_search")
async def handle_expenses_search(call: CallbackQuery):
    await call.answer("Реализуйте поиск по истории")
    # Реализуйте логику поиска

@dp.callback_query(F.data == "expenses_by_category")
async def handle_expenses_by_category(call: CallbackQuery):
    await call.answer("Реализуйте фильтр по категориям")
    # Реализуйте логику фильтрации

# Обработчики для кнопок настроек
@dp.callback_query(F.data == "reminders")
async def handle_reminders(call: CallbackQuery):
    await call.answer("Реализуйте настройки напоминаний")
    # Реализуйте логику напоминаний

@dp.callback_query(F.data == "budgets")
async def handle_budgets(call: CallbackQuery):
    await call.answer()
    await budgets_menu(call)

@dp.callback_query(F.data == "categories")
async def handle_categories(call: CallbackQuery):
    await call.answer("Реализуйте управление категориями")
    # Реализуйте логику управления категориями

# Обработчики для кнопок бюджетов
@dp.callback_query(F.data == "set_budget")
async def handle_set_budget(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Введите категорию для установки бюджета:")
    await state.set_state(BudgetStates.waiting_for_category)

@dp.callback_query(F.data == "view_budgets")
async def handle_view_budgets(call: CallbackQuery):
    await call.answer("Показываем текущие бюджеты")
    # Реализуйте логику показа бюджетов
# Обработчики для быстрого выбора категорий
@dp.callback_query(F.data.startswith("quick_cat_"))
async def handle_quick_category(call: CallbackQuery, state: FSMContext):
    category = call.data.replace("quick_cat_", "")
    await state.update_data(category=category)
    await call.message.answer(f"Выбрана категория: {category}. Теперь введите сумму:")
    await state.set_state(ExpenseStates.waiting_for_amount)
    await call.answer()

@dp.callback_query(F.data == "manual_input")
async def handle_manual_input(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "Введите расход в формате: Категория Сумма [Дата] [Время]\n"
        "Пример: Такси 350 15.07 18:30",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(ExpenseStates.waiting_for_expense_input)
@dp.message(ExpenseStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        data = await state.get_data()
        category = data.get('category', 'Другое')
        
        conn = await get_db_connection()
        try:
            await conn.execute(
                "INSERT INTO expenses (user_id, category, amount) VALUES ($1, $2, $3)",
                message.from_user.id, category, amount
            )
            await message.answer(f"✅ Добавлено: {category} - {amount:.2f} ₽")
        finally:
            await conn.close()
            
        await state.clear()
        await start(message, state)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму")

@dp.callback_query(F.data == "settings_back")
async def handle_settings_back(call: CallbackQuery):
    await call.answer()
    await start(call.message, call.bot)

@dp.callback_query()
async def unknown_callback(call: CallbackQuery):
    await call.answer("⚠️ Неизвестная команда", show_alert=True)
    logger.warning(f"Unknown callback data: {call.data}")
#region Запуск бота
async def main():
    await create_table()
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
#endregion