
from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery

from init import logging, ADMIN_ID
from db.db_main import get_pool

category_router = Router()

MAX_CUSTOM_CATEGORIES = 5  # лимит пользовательских категорий

PREDEFINED_CATEGORIES = [
    "Продукты", "Жильё", "Связь и интернет", "Транспорт", "Здоровье",
    "Одежда и обувь", "Красота и уход", "Развлечения", "Образование",
    "Дом/ремонт", "Путешествия", "Подарки и праздники", "Неожиданные траты"
]

class ExpenseStates(StatesGroup):
    waiting_for_new_category = State()  # ← новое состояние
    waiting_for_edit_category = State()

#region Получение категорий
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

async def get_user_categories(user_id: int) -> list[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        # Получаем категории из user_categories (все добавленные пользователем)
        user_categories = await conn.fetch(
            "SELECT category FROM user_categories WHERE user_id = $1",
            user_id
        )
        # И категории, которые уже использовались в расходах
        used_categories = await conn.fetch(
            "SELECT DISTINCT category FROM expenses WHERE user_id = $1",
            user_id
        )
        
        # Объединяем и убираем дубликаты
        all_categories = {row['category'] for row in user_categories} | {row['category'] for row in used_categories}
        return list(all_categories)
#endregion
#region Меню категорий
@category_router.callback_query(F.data == "categories")
async def categories_menu(call: CallbackQuery, state: FSMContext):
    # Получаем текущие категории пользователя
    user_categories = await get_user_categories(call.from_user.id)
    predefined_categories = set(PREDEFINED_CATEGORIES)
    
    # Фильтруем только пользовательские категории (не предустановленные)
    custom_categories = [cat for cat in user_categories if cat not in predefined_categories]
    
    # Формируем текст сообщения
    text = "📊 <b>Управление категориями</b>\n\n"
    text += "<b>Стандартные категории:</b>\n"
    text += "\n".join(f"• {cat}" for cat in PREDEFINED_CATEGORIES)
    
    if custom_categories:
        text += "\n\n<b>Ваши категории:</b>\n"
        text += "\n".join(f"• {cat}" for cat in custom_categories)
    else:
        text += "\n\nУ вас пока нет своих категорий."
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    if custom_categories:
        builder.row(
            types.InlineKeyboardButton(text="➕ Добавить", callback_data="add_category"),
            types.InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_category"),
            types.InlineKeyboardButton(text="🗑️ Удалить", callback_data="delete_category"),
            width=3
        )
    else:
        builder.row(
            types.InlineKeyboardButton(text="➕ Добавить", callback_data="add_category"),
            width=1
        )
    
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="settings"),
        width=1
    )
    
    await call.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )
#endregion
#region Добавление новой категории
@category_router.message(ExpenseStates.waiting_for_new_category)
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

@category_router.callback_query(F.data == "add_category")
async def add_category_prompt(call: CallbackQuery, state: FSMContext):
    # Проверяем лимит категорий
    user_categories = await get_user_categories(call.from_user.id)
    predefined_categories = set(PREDEFINED_CATEGORIES)
    custom_categories = [cat for cat in user_categories if cat not in predefined_categories]
    
    if len(custom_categories) >= MAX_CUSTOM_CATEGORIES:
        await call.answer(f"❌ Достигнут лимит в {MAX_CUSTOM_CATEGORIES} пользовательских категорий", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="categories"),
        width=1
    )
    
    await call.message.edit_text(
        "Введите название новой категории:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(ExpenseStates.waiting_for_new_category)
#endregion
#region Удаление категории
@category_router.callback_query(F.data == "delete_category")
async def delete_category_menu(call: CallbackQuery):
    pool = get_pool()
    async with pool.acquire() as conn:
        # Получаем все пользовательские категории
        user_categories = await conn.fetch(
            "SELECT category FROM user_categories WHERE user_id = $1",
            call.from_user.id
        )
        # Получаем категории, которые уже использовались в расходах
        used_categories = await conn.fetch(
            "SELECT DISTINCT category FROM expenses WHERE user_id = $1",
            call.from_user.id
        )
    
    custom_categories = [row['category'] for row in user_categories]
    used_categories_set = {row['category'] for row in used_categories}
    
    if not custom_categories:
        await call.answer("❌ У вас нет пользовательских категорий для удаления", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    for category in custom_categories:
        # Добавляем пометку "(не использовалась)", если категория не встречается в расходах
        suffix = " (не использовалась)" if category not in used_categories_set else ""
        builder.row(
            types.InlineKeyboardButton(
                text=f"🗑️ {category}{suffix}",
                callback_data=f"confirm_delete:{category}"
            ),
            width=1
        )
    
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="categories"),
        width=1
    )
    
    await call.message.edit_text(
        "Выберите категорию для удаления:\n"
        "Категории с пометкой '(не использовалась)' можно удалить без последствий.",
        reply_markup=builder.as_markup()
    )

@category_router.callback_query(F.data.startswith("confirm_delete:"))
async def confirm_delete_category(call: CallbackQuery):
    category = call.data.split(":")[1]
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=f"do_delete:{category}"
        ),
        types.InlineKeyboardButton(
            text="❌ Нет, отмена",
            callback_data="delete_category"
        ),
        width=2
    )
    
    await call.message.edit_text(
        f"Вы уверены, что хотите удалить категорию <b>{category}</b>?\n"
        "Все связанные с ней расходы останутся, но категория будет изменена на 'Другое'.",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )

@category_router.callback_query(F.data.startswith("do_delete:"))
async def execute_delete_category(call: CallbackQuery):
    category = call.data.split(":")[1]
    user_id = call.from_user.id
    
    pool = get_pool()
    async with pool.acquire() as conn:
        # Удаляем категорию из пользовательских
        await conn.execute(
            "DELETE FROM user_categories WHERE user_id = $1 AND category = $2",
            user_id, category
        )
        
        # Обновляем расходы с этой категорией на "Другое"
        await conn.execute(
            "UPDATE expenses SET category = 'Другое' WHERE user_id = $1 AND category = $2",
            user_id, category
        )
    
    await call.answer(f"Категория '{category}' удалена", show_alert=True)
    await categories_menu(call, None)
#endregion
#region Изменение категории
@category_router.callback_query(F.data == "edit_category")
async def edit_category_menu(call: CallbackQuery):
    # Аналогично delete_category_menu, но для редактирования
    user_categories = await get_user_categories(call.from_user.id)
    predefined_categories = set(PREDEFINED_CATEGORIES)
    custom_categories = [cat for cat in user_categories if cat not in predefined_categories]
    
    if not custom_categories:
        await call.answer("❌ У вас нет пользовательских категорий для изменения", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    for category in custom_categories:
        builder.row(
            types.InlineKeyboardButton(
                text=f"✏️ {category}",
                callback_data=f"edit_select:{category}"
            ),
            width=1
        )
    
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="categories"),
        width=1
    )
    
    await call.message.edit_text(
        "Выберите категорию для изменения:",
        reply_markup=builder.as_markup()
    )

@category_router.callback_query(F.data.startswith("edit_select:"))
async def edit_category_prompt(call: CallbackQuery, state: FSMContext):
    old_category = call.data.split(":")[1]
    await state.update_data(old_category=old_category)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="edit_category"),
        width=1
    )
    
    await call.message.edit_text(
        f"Введите новое название для категории <b>{old_category}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(ExpenseStates.waiting_for_edit_category)
#endregion
#region Сохранение измененной категории
@category_router.message(ExpenseStates.waiting_for_edit_category)
async def save_edited_category(message: types.Message, state: FSMContext):
    new_category = message.text.strip()
    user_id = message.from_user.id
    data = await state.get_data()
    old_category = data.get("old_category")
    
    if not new_category:
        await message.answer("Название категории не может быть пустым")
        return
    
    if new_category in PREDEFINED_CATEGORIES:
        await message.answer("❌ Эта категория уже есть в стандартном списке")
        await state.clear()
        return
    
    pool = get_pool()
    async with pool.acquire() as conn:
        # Проверяем, есть ли уже такая категория
        exists = await conn.fetchval(
            "SELECT 1 FROM user_categories WHERE user_id = $1 AND LOWER(category) = LOWER($2)",
            user_id, new_category
        )
        if exists:
            await message.answer("❌ Такая категория уже существует")
            await state.clear()
            return
        
        # Обновляем категорию в user_categories
        await conn.execute(
            "UPDATE user_categories SET category = $1 WHERE user_id = $2 AND category = $3",
            new_category, user_id, old_category
        )
        
        # Обновляем категорию в expenses
        await conn.execute(
            "UPDATE expenses SET category = $1 WHERE user_id = $2 AND category = $3",
            new_category, user_id, old_category
        )
    
    await message.answer(f"✅ Категория изменена с «{old_category}» на «{new_category}»")
    await state.clear()
    
    # Создаем клавиатуру для меню категорий
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="➕ Добавить", callback_data="add_category"),
        types.InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_category"),
        types.InlineKeyboardButton(text="🗑️ Удалить", callback_data="delete_category"),
        width=3
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="settings"),
        width=1
    )
    
    await message.answer(
        "📊 <b>Управление категориями</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup()
    )
