
import matplotlib.pyplot as plt
from matplotlib import rcParams
import io
from aiogram.types import InputMediaPhoto, InputFile, CallbackQuery

from aiogram.exceptions import TelegramAPIError
from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from datetime import  date, timedelta, datetime

from init import logging, ADMIN_ID
from db.db_main import get_pool

stats_router = Router()

class StatsState(StatesGroup):
    choosing_period = State()
    choosing_type = State()
    custom_period_input = State()
    
def get_stat_type_keyboard():
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Обычная", callback_data="stat_type_regular"),
        InlineKeyboardButton(text="По категориям", callback_data="stat_type_categories")
    )
    kb.row(
        InlineKeyboardButton(text="График", callback_data="stat_type_graph"),
        InlineKeyboardButton(text="🏆 Топ", callback_data="stat_type_top")
    )
    kb.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="show_stats_menu")
    )
    return kb.as_markup()

@stats_router.callback_query(F.data == "period_custom")
async def ask_custom_period(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "📅 Введите период в формате:\n"
        "<code>дд.мм.гггг - дд.мм.гггг</code>\n"
        "например: 01.05.2025 - 22.05.2025",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("show_stats_menu").as_markup()
    )
    await state.set_state(StatsState.custom_period_input)
    await call.answer()

@stats_router.message(StatsState.custom_period_input)
async def process_custom_period(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        start_str, end_str = map(str.strip, text.split("-"))
        start_date = datetime.strptime(start_str, "%d.%m.%Y").date()
        end_date = datetime.strptime(end_str, "%d.%m.%Y").date()
        if start_date > end_date:
            raise ValueError("Начальная дата позже конечной.")
    except Exception:
        await message.answer(
            "❌ Неверный формат даты или даты указаны неправильно.\n"
            "Пожалуйста, введите период в формате:\n"
            "<code>дд.мм.гггг - дд.мм.гггг</code>\n"
            "Например: 01.05.2025 - 22.05.2025",
            parse_mode=ParseMode.HTML
        )
        return

    await state.update_data(custom_period=(start_date, end_date), period="period_custom")
    await state.set_state(StatsState.choosing_type)

    await message.answer(
        f"✅ Период установлен: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n"
        "📈 Выберите тип статистики:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_stat_type_keyboard()
    )



def get_period_filter(period_key: str, current_date: date, user_id: int, custom_period=None):
    if period_key == "period_today":
        return {
            "condition": "date = $2::date",
            "params": [user_id, current_date],
            "title_suffix": "сегодня",
            "period_info": current_date.strftime('%d.%m.%Y')
        }
    elif period_key == "period_week":
        week_start = current_date - timedelta(days=6)
        return {
            "condition": "date BETWEEN $2 AND $3",
            "params": [user_id, week_start, current_date],
            "title_suffix": "неделя",
            "period_info": f"{week_start.strftime('%d.%m.%Y')} - {current_date.strftime('%d.%m.%Y')}"
        }
    elif period_key == "period_month":
        month_start = current_date.replace(day=1)
        return {
            "condition": "date BETWEEN $2 AND $3",
            "params": [user_id, month_start, current_date],
            "title_suffix": "месяц",
            "period_info": f"{month_start.strftime('%d.%m.%Y')} - {current_date.strftime('%d.%m.%Y')}"
        }
    elif period_key == "period_all":
        return {
            "condition": "TRUE",
            "params": [user_id],
            "title_suffix": "всё время",
            "period_info": "за весь период"
        }
    elif period_key == "period_custom":
        if custom_period is None:
            raise ValueError("Для кастомного периода нужно передать даты")
        start_date, end_date = custom_period
        return {
            "condition": "date BETWEEN $2 AND $3",
            "params": [user_id, start_date, end_date],
            "title_suffix": f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
            "period_info": f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
        }
    else:
        raise ValueError(f"Unknown period key: {period_key}")

async def get_period_info_for_state(state: FSMContext, current_date: date, user_id: int):
    data = await state.get_data()
    period_key = data.get("period")
    custom_period = data.get("custom_period")

    if period_key == "period_custom" and custom_period is None:
        raise ValueError("Для кастомного периода нужно ввести даты. Пожалуйста, выберите кастомный период заново.")

    return get_period_filter(period_key, current_date, user_id, custom_period=custom_period)


def back_button(callback: str = "show_stats_menu"):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=callback))
    return builder

@stats_router.callback_query(F.data == "show_stats_menu")
async def show_stats_menu(call: CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="📅 За сегодня", callback_data="period_today"),
        InlineKeyboardButton(text="📅 За неделю", callback_data="period_week")
    )
    keyboard.row(
        InlineKeyboardButton(text="📅 За месяц", callback_data="period_month"),
        InlineKeyboardButton(text="📅 За всё время", callback_data="period_all")
    )
    keyboard.row(
        InlineKeyboardButton(text="📅 Свой период", callback_data="period_custom"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
    )

    markup = keyboard.as_markup()
    text = "📊 <b>Выберите период для статистики:</b>"

    try:
        await call.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except TelegramAPIError:
        try:
            await call.message.delete()
        except TelegramAPIError:
            pass  
        await call.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        
@stats_router.callback_query(F.data == "stat_type_categories")
async def show_stats_by_categories(call: CallbackQuery, state: FSMContext):
    pool = get_pool()
    if not pool:
        logging.error("❌ БД не инициализирована")
        return

    db_now = await pool.fetchval("SELECT NOW()")
    current_date = db_now.date()

    try:
        period_info = await get_period_info_for_state(state, current_date, call.from_user.id)
    except ValueError as e:
        await call.message.answer(str(e))
        return


    date_condition = period_info["condition"]
    params = period_info["params"]
    title = f"📊 Расходы по категориям ({period_info['title_suffix']})"

    try:
        query = f"""
            SELECT category, COUNT(*) as count, SUM(amount) as total
            FROM expenses
            WHERE user_id = $1 AND {date_condition}
            GROUP BY category
            ORDER BY total DESC
        """
        records = await pool.fetch(query, *params)

        if not records:
            text = f"{title}\n\nНет данных за выбранный период."
        else:
            lines = [f"{i+1}. {r['category']} — {r['count']} шт., {r['total']:.2f} ₽"
                     for i, r in enumerate(records)]
            text = f"{title}\n\n" + "\n".join(lines)

        await call.message.edit_text(text, reply_markup=back_button().as_markup())
        await call.answer()

    except Exception as e:
        logging.error(f"Ошибка при получении статистики по категориям: {e}", exc_info=True)
        await call.message.answer("❌ Не удалось получить статистику.")
        await call.answer()

@stats_router.callback_query(F.data == "stat_type_graph")
async def show_stats_graph_for_period(call: CallbackQuery, state: FSMContext):
    pool = get_pool()
    if not pool:
        logging.error("❌ БД не инициализирована")
        return

    data = await state.get_data()
    period_key = data.get("period")
    custom_period = data.get("custom_period")  # Важно

    if not period_key:
        await call.message.answer("⚠️ Не удалось определить период.")
        return

    db_now = await pool.fetchval("SELECT NOW()")
    current_date = db_now.date()

    try:
        period_info = get_period_filter(period_key, current_date, call.from_user.id, custom_period=custom_period)
    except ValueError as e:
        await call.message.answer(str(e))
        return

    date_condition = period_info["condition"]
    params = period_info["params"]
    title = f"📈 Диаграмма ({period_info['title_suffix']})"

    try:
        stats = await pool.fetch(
            f"""
            SELECT category, SUM(amount) as total
            FROM expenses
            WHERE user_id = $1 AND {date_condition}
            GROUP BY category
            ORDER BY total DESC
            """,
            *params
        )

        if not stats:
            await call.answer("ℹ️ Нет данных для построения графика.", show_alert=True)
            return

        categories = [row["category"] for row in stats]
        amounts = [float(row["total"]) for row in stats]
        total_sum = sum(amounts)

        labels = [
            f"{cat} — {amount:.2f} ₽ ({(amount/total_sum)*100:.1f}%)"
            for cat, amount in zip(categories, amounts)
        ]

        rcParams.update({'font.size': 12, 'font.weight': 'bold'})
        plt.figure(figsize=(8, 8))
        plt.gca().set_facecolor('#f0f0f0')

        wedges, texts, autotexts = plt.pie(
            amounts,
            labels=labels,
            startangle=140,
            autopct=lambda pct: f"{pct:.1f}%" if pct > 3 else "",
            colors=plt.cm.Paired.colors,
            wedgeprops={"edgecolor": "white"}
        )

        for text in texts + autotexts:
            text.set_fontsize(10)
            text.set_fontweight('bold')

        plt.title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        media = InputMediaPhoto(media=InputFile(buf, filename="stats_graph.png"), caption=title, parse_mode=ParseMode.HTML)

        await call.message.edit_media(media=media, reply_markup=back_button().as_markup())

        buf.close()
        await call.answer()

    except Exception as e:
        logging.error(f"Ошибка при построении графика: {e}", exc_info=True)
        await call.message.answer("❌ Не удалось построить график.")
        await call.answer()

@stats_router.callback_query(F.data.in_({"period_today", "period_week", "period_month", "period_all"}))
async def handle_stats_period(call: CallbackQuery, state: FSMContext):
    period_key = call.data
    await state.update_data(period=period_key)
    await state.set_state(StatsState.choosing_type)

    await call.message.edit_text(
        "📈 <b>Выберите тип статистики:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_stat_type_keyboard()
    )
    await call.answer()

@stats_router.message(Command("user_stats"))
async def user_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        logging.warning(
            f"⛔ Попытка доступа к /user_stats от пользователя ID: {message.from_user.id}, username: @{message.from_user.username}"
        )
        return await message.answer("❌ Доступ запрещен")

    logging.info(
        f"✅ Админ {message.from_user.id} запросил статистику пользователей (/user_stats)"
    )

    db_pool = get_pool()
    try:
        stats = await db_pool.fetch(
            """
            SELECT u.user_id, u.username, COUNT(e.id) AS expenses_count,
                   SUM(e.amount) AS total_amount, MAX(u.last_active) AS last_active
            FROM users u
            LEFT JOIN expenses e ON u.user_id = e.user_id
            GROUP BY u.user_id
            ORDER BY last_active DESC
            """
        )

        if not stats:
            return await message.answer("ℹ️ Пока нет данных о пользователях.")

        text = "📊 <b>Статистика пользователей:</b>\n\n"
        for row in stats:
            username_display = f"@{row['username']}" if row['username'] else f"ID: {row['user_id']}"
            last_active = row['last_active'].strftime('%d.%m.%Y %H:%M') if row['last_active'] else "—"
            total_amount = row['total_amount'] or 0.00

            text += (
                f"👤 {username_display}\n"
                f"├ Расходов: {row['expenses_count']}\n"
                f"├ Сумма: {total_amount:.2f} ₽\n"
                f"╰ Последняя активность: {last_active}\n\n"
            )

        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"❌ Ошибка при получении статистики пользователей: {e}", exc_info=True)
        await message.answer("❌ Не удалось загрузить статистику пользователей.")

@stats_router.callback_query(F.data == "stat_type_regular")
async def show_regular_stats(call: CallbackQuery, state: FSMContext):
    pool = get_pool()
    if not pool:
        logging.error("❌ БД не инициализирована")
        return

    data = await state.get_data()
    period_key = data.get("period")

    if not period_key:
        await call.message.answer("⚠️ Не удалось определить период.")
        return

    db_now = await pool.fetchval("SELECT NOW()")
    current_date = db_now.date()

    period_info = await get_period_info_for_state(state, current_date, call.from_user.id)

    date_condition = period_info["condition"]
    params = period_info["params"]
    title = f"📊 Статистика за {period_info['title_suffix']}"
    period_text = period_info["period_info"]

    try:
        total = await pool.fetchval(
            f"SELECT COALESCE(SUM(amount), 0) FROM expenses "
            f"WHERE user_id = $1 AND {date_condition}",
            *params
        )
        stats = await pool.fetch(
            f"SELECT category, COALESCE(SUM(amount), 0) as sum FROM expenses "
            f"WHERE user_id = $1 AND {date_condition} "
            f"GROUP BY category ORDER BY sum DESC",
            *params
        )

        response = (
            f"{title}\n"
            f"Период: {period_text}\n"
            f"Общие расходы: {float(total):.2f} ₽\n\n"
        )
        if stats:
            for i, row in enumerate(stats, 1):
                response += f"{i}. {row['category']}: {row['sum']:.2f} ₽\n"
        else:
            response += "Нет данных за выбранный период\n"

        await call.message.edit_text(response, reply_markup=back_button().as_markup())
        await call.answer()

    except Exception as e:
        logging.error(f"Ошибка при получении статистики: {e}", exc_info=True)
        await call.message.answer("❌ Не удалось загрузить статистику.")
        await call.answer()
