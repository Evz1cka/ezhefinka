# region Импорт библиотек

# 📌 Стандартные библиотеки
import os
import html
import logging
import asyncio
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile
import json
# 📌 Сторонние библиотеки
import aiogram.exceptions
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)

# 📌 Локальные модули
from init import ADMIN_ID

# endregion

# Храним старт запуска (нужно импортировать его!)

logs_router = Router()

CONFIG_FILE = "config.json"
LOG_PATH = "bot.log"
CLEAN_INTERVAL_DAYS = 7
# Храним глобальное время последней очистки

def load_config():
    """Загружает конфигурацию из JSON-файла."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"ai_assistant_enabled": True, "send_media_alerts": False} 

def save_config(data):
    """Сохраняет конфигурацию в JSON-файл."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

def get_last_cleanup_time() -> datetime:
    config = load_config()
    time_str = config.get("last_cleanup_time")
    if time_str:
        try:
            return datetime.fromisoformat(time_str)
        except ValueError:
            logging.warning("⚠️ Ошибка чтения времени last_cleanup_time, используется текущее.")
    return datetime.now()

def set_last_cleanup_time(dt: datetime):
    config = load_config()
    config["last_cleanup_time"] = dt.isoformat()
    save_config(config)
    
config = load_config()

def init_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Удаляем старые обработчики
    if logger.hasHandlers():
        logger.handlers.clear()

    # 🔹 Файл логов
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d | %H:%M:%S"  # ⬅️ Вот здесь убраны миллисекунды
        )
    file_handler.setFormatter(formatter)


    # 🔹 Консоль (терминал)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

async def start_log_cleanup_cycle():
    start_time = datetime.now()
    notified = False  # Было ли уже отправлено предупреждение

    while True:
        now = datetime.now()
        time_passed = now - start_time
        time_until_clean = timedelta(days=CLEAN_INTERVAL_DAYS) - time_passed

        # 📢 Уведомление за 24 часа до очистки
        if not notified and time_until_clean <= timedelta(days=1):
            '''
            await message.answer(
                f"📢 Через 24 часа лог-файл будет автоматически очищен!\n"
                f"🕓 Время очистки: {start_time + timedelta(days=7):%Y-%m-%d %H:%M}"
            )
            notified = True
            '''
        # 🧹 Очистка, если прошло 7 дней
        if time_passed >= timedelta(days=CLEAN_INTERVAL_DAYS):
            if os.path.exists(LOG_PATH):
                with open(LOG_PATH, "w", encoding="utf-8") as f:
                    f.write("")
                logging.info("🧹 Лог-файл очищен автоматически.")
                #await message.answer("🧹 Лог-файл очищен автоматически.")
            
           # 🔁 Сброс отсчёта
            start_time = datetime.now()
            set_last_cleanup_time(start_time)
            notified = False

        await asyncio.sleep(3600)  # Проверять раз в час (можно чаще, если хочешь)

def get_last_log_lines(n: int = 100) -> list[str] | None:
    """Возвращает последние N строк логов из файла."""
    if not os.path.exists(LOG_PATH):
        logging.warning("⚠️ Лог-файл не найден.")
        return None

    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
        return all_lines[-n:]
    except Exception as e:
        logging.exception("❌ Ошибка при чтении логов:")
        return None

@logs_router.message(Command("logs"))
@logs_router.callback_query(F.data == "logs")
async def send_logs(event: types.Message | CallbackQuery):
    user = event.from_user if isinstance(event, CallbackQuery) else event.from_user
    if user.id != ADMIN_ID:
        if isinstance(event, CallbackQuery):
            await event.answer("❌ У вас нет доступа к логам.", show_alert=True)
        else:
            await event.answer("❌ У вас нет доступа к логам.")
        return

    message = event.message if isinstance(event, CallbackQuery) else event
    args = message.text.split() if message.text else []
    lines = int(args[1]) if len(args) > 1 and args[1].isdigit() else 100

    tail = get_last_log_lines(lines)
    if tail is None:
        await message.answer("⚠️ Не удалось прочитать лог-файл.")
        return

    with NamedTemporaryFile("w+", delete=False, suffix=".log", encoding="utf-8") as temp_file:
        temp_file.writelines(tail)
        temp_path = temp_file.name

    await message.answer_document(
        FSInputFile(temp_path),
        caption=(
            f"🧾 Последние {lines} строк логов\n"
            "Если нужно больше, отправьте команду: /logs [кол-во строк]."
        ),
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Вывести в сообщение", callback_data="logs_as_text")]
        ])
    )
    os.remove(temp_path)

@logs_router.callback_query(F.data == "logs_as_text")
async def send_logs_as_text(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Недостаточно прав.", show_alert=True)
        return

    log_file_path = "bot.log"
    if not os.path.exists(log_file_path):
        await call.message.edit_text("⚠️ Лог-файл не найден.")
        return

    tail = get_last_log_lines(100)
    if tail is None:
        await call.message.edit_text("⚠️ Не удалось прочитать лог-файл.")
        return


    log_text = "".join(tail).strip()
    if len(log_text) > 4000:
        log_text = "[...]\n" + log_text[-4000:]  # обрезаем до 4000 символов

    escaped = html.escape(log_text)

    try:
        await call.message.edit_text(
            f"📄 <b>Последние логи:</b>\n\n<pre>{escaped}</pre>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить логи", callback_data="logs_as_text")]
            ])
        )
    except aiogram.exceptions.TelegramBadRequest:
        # если не редактируется — просто отправим новое сообщение
        await call.message.answer(
            f"📄 <b>Последние логи:</b>\n\n<pre>{escaped}</pre>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить логи", callback_data="logs_as_text")]
            ])
        )

    await call.answer("✅ Логи обновлены")

@logs_router.message(Command("clearlog"))
@logs_router.callback_query(F.data == "clearlog")
async def clear_logs(event: types.Message | CallbackQuery):
    user = event.from_user if isinstance(event, CallbackQuery) else event.from_user
    if user.id != ADMIN_ID:
        if isinstance(event, CallbackQuery):
            await event.answer("❌ У вас нет прав.", show_alert=True)
        else:
            await event.answer("❌ У вас нет прав.")
        return

    message = event.message if isinstance(event, CallbackQuery) else event

    now = datetime.now()
    last_cleanup_time = get_last_cleanup_time()
    next_cleanup_time = last_cleanup_time + timedelta(days=CLEAN_INTERVAL_DAYS)

    remaining = next_cleanup_time - now

    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60

    warn_text = (
        f"🧹 До автоматической очистки логов осталось: "
        f"<b>{hours} ч {minutes} мин</b>\n\n"
        f"Вы уверены, что хотите очистить логи вручную сейчас?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Очистить сейчас", callback_data="confirm_clearlog")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clearlog")]
    ])

    await message.answer(warn_text, reply_markup=keyboard, parse_mode="HTML")

@logs_router.callback_query(lambda c: c.data == "confirm_clearlog")
async def confirm_clearlog(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Недостаточно прав.", show_alert=True)
        return

    log_file = "bot.log"
    if os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("")
        await call.message.edit_text("🧹 Лог-файл был очищен вручную!")
    else:
        await call.message.edit_text("⚠️ Лог-файл не найден.")


@logs_router.callback_query(lambda c: c.data == "cancel_clearlog")
async def cancel_clearlog(call: CallbackQuery):
    await call.message.edit_text("❌ Очистка логов отменена.")