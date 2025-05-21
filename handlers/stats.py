import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,

)
import asyncpg
from datetime import datetime, date, time, timedelta

from init import logging, ADMIN_ID
from db.db_main import get_pool

stats_router = Router()

@stats_router.callback_query(F.data == "show_stats_menu")
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

@stats_router.callback_query(F.data == "stats_categories") # Обработка кнопки "Статистика"
async def show_stats_categories(callback: CallbackQuery):
    await callback.answer("🚧 Эта функция пока в разработке.", show_alert=True)

@stats_router.callback_query(F.data == "stats_graphs") # Обработка кнопки "Статистика"
async def show_stats_graph(call: CallbackQuery):
    await call.answer("🚧 Эта функция пока в разработке.", show_alert=True)

@stats_router.callback_query(F.data == "stats_period") # Обработка кнопки "Статистика"
async def show_stats(call: CallbackQuery):
    # Создаем клавиатуру для выбора периода
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="За сегодня", callback_data="period_today"),
        InlineKeyboardButton(text="За неделю", callback_data="period_week")
    )
    keyboard.row(
        InlineKeyboardButton(text="За месяц", callback_data="period_month"),
        InlineKeyboardButton(text="Назад", callback_data="show_stats_menu")
    )
    await call.message.edit_text(
        "Выберите период для статистики:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard.as_markup()
    )
    

@stats_router.callback_query(F.data.in_({"period_today", "period_week", "period_month"}))
async def handle_stats_period(call: CallbackQuery):
    pool = get_pool()
    if not pool:
        logging.error("❌ Ошибка: база данных не инициализирована! pool=None")
        return
    
    user_id = call.from_user.id
    period_key = call.data

    # Получаем текущую дату из БД
    db_now = await pool.fetchval("SELECT NOW()")
    current_date = db_now.date()

    if period_key == "period_today":
        date_condition = "date = $2::date"
        params = [user_id, current_date]
        title = "📊 Статистика за сегодня"
        period_info = f"{current_date.strftime('%d.%m.%Y')}"
    elif period_key == "period_week":
        week_start = current_date - timedelta(days=6)
        date_condition = "date BETWEEN $2 AND $3"
        params = [user_id, week_start, current_date]
        title = "📊 Статистика за неделю"
        period_info = f"{week_start.strftime('%d.%m.%Y')} - {current_date.strftime('%d.%m.%Y')}"
    else:  # period_month
        month_start = current_date.replace(day=1)
        date_condition = "date BETWEEN $2 AND $3"
        params = [user_id, month_start, current_date]
        title = "📊 Статистика за месяц"
        period_info = f"{month_start.strftime('%d.%m.%Y')} - {current_date.strftime('%d.%m.%Y')}"

    # Выполняем запросы
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
            f"Период: {period_info}\n"
            f"Общие расходы: {float(total):.2f} ₽\n\n"
        )
        if stats:
            for i, row in enumerate(stats, 1):
                response += f"{i}. {row['category']}: {row['sum']:.2f} ₽\n"
        else:
            response += "Нет данных за выбранный период\n"
        keyboard = InlineKeyboardBuilder()
        keyboard.add(
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="stats_period"
            )
        )
        await call.message.edit_text(response, reply_markup=keyboard.as_markup() )
        await call.answer()  

    except Exception as e:
        logging.error(f"Ошибка при получении статистики: {e}", exc_info=True)
        await call.message.answer("❌ Не удалось загрузить статистику")
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
