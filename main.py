import sqlite3
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType,
    InputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.state import StateFilter
from dotenv import load_dotenv  # Для загрузки переменных из .env файла

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота и ID администратора
API_TOKEN = os.getenv('API_TOKEN')  # Убедитесь, что в .env файле есть строка API_TOKEN=ваш_токен
ADMIN_ID = 516337879
# ADMIN_ID = 217444514

if not API_TOKEN:
    logger.error("API_TOKEN не установлен. Проверьте .env файл.")
    exit(1)

# Создаем объект бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# FSM для заказа
class OrderForm(StatesGroup):
    name = State()
    phone = State()
    quantity = State()
    delivery = State()
    address = State()


# FSM для добавления/редактирования сыра
class CheeseForm(StatesGroup):
    name = State()
    description = State()
    price = State()
    photo = State()
    edit_cheese_id = State()

class AddCheeseForm(StatesGroup):
    name = State()
    description = State()
    price = State()
    photo = State()

class EditCheeseForm(StatesGroup):
    name = State()
    description = State()
    price = State()
    photo = State()

class DeleteCheeseForm(StatesGroup):
    confirm = State()
    cheese_id = State()


# Создание базы данных SQLite
def setup_db():
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cheeses (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        price REAL NOT NULL,
        photo TEXT NOT NULL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        telegram_username TEXT,  -- Добавлено поле для Telegram-ника
        cheese_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        delivery_method TEXT NOT NULL,
        address TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cheese_id) REFERENCES cheeses(id)
    )
    ''')
    conn.commit()
    conn.close()
    logger.info("База данных настроена.")




# Главное меню
def main_menu(is_admin=False):
    keyboard = [
        [KeyboardButton(text="Каталог")],
        [KeyboardButton(text="О нас"), KeyboardButton(text="Контакты")]
    ]

    if is_admin:
        # Добавляем кнопки только для администраторов
        keyboard.append([KeyboardButton(text="Добавить сыр"), KeyboardButton(text="Редактировать сыр")])
        keyboard.append([KeyboardButton(text="Удалить сыр"), KeyboardButton(text="Просмотреть заказы")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )


# Получение списка сыров из базы данных с поддержкой пагинации
def get_cheeses(offset=0, limit=10):
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cheeses LIMIT ? OFFSET ?', (limit, offset))
    cheeses = cursor.fetchall()
    conn.close()
    return cheeses


# Пагинация каталога
def catalog_pagination(page=0, limit=10):
    builder = InlineKeyboardBuilder()
    offset = page * limit
    cheeses = get_cheeses(offset=offset, limit=limit + 1)  # Запрашиваем на одну запись больше

    has_next = False
    if len(cheeses) > limit:
        has_next = True
        cheeses = cheeses[:limit]  # Обрезаем лишнюю запись

    for cheese in cheeses:
        builder.add(InlineKeyboardButton(text=cheese[1], callback_data=f"cheese_{cheese[0]}"))

    builder.adjust(2)  # Размещаем по 2 кнопки в строку

    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"catalog_prev_{page}"))
    if has_next:
        navigation_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"catalog_next_{page}"))

    if navigation_buttons:
        builder.row(*navigation_buttons)  # Навигационные кнопки на отдельной строке

    return builder.as_markup()

# Обработка кнопки "Добавить сыр"
@dp.message(F.text == "Добавить сыр", F.from_user.id == ADMIN_ID)
async def add_cheese_button(message: types.Message, state: FSMContext):
    await add_cheese(message, state)

# Обработка кнопки "Редактировать сыр"
@dp.message(F.text == "Редактировать сыр", F.from_user.id == ADMIN_ID)
async def edit_cheese_button(message: types.Message, state: FSMContext):
    await edit_cheese(message, state)



# Стартовый хэндлер
# Стартовый хэндлер
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(
        "Добро пожаловать в наш интернет-магазин сыров!",
        reply_markup=main_menu(is_admin=is_admin),
        parse_mode='HTML'
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота.")



# Обработка нажатия на "Каталог"
@dp.message(F.text == "Каталог")
async def show_catalog(message: types.Message):
    await message.answer("Выберите сыр из списка:", reply_markup=catalog_pagination(), parse_mode='HTML')
    logger.info(f"Пользователь {message.from_user.id} открыл каталог.")


# Обработка пагинации каталога (Вперед и Назад)
@dp.callback_query(F.data.startswith("catalog_"))
async def navigate_catalog(callback_query: types.CallbackQuery):
    try:
        _, action, current_page = callback_query.data.split('_')
        current_page = int(current_page)
        logger.debug(f"Навигация каталога: действие={action}, текущая страница={current_page}")
    except ValueError:
        await callback_query.answer("Некорректные данные пагинации.", show_alert=True)
        logger.error("Некорректные данные пагинации.")
        return

    if action == "next":
        new_page = current_page + 1
    elif action == "prev":
        new_page = current_page - 1
    else:
        new_page = 0

    # Убедитесь, что catalog_pagination возвращает InlineKeyboardMarkup
    reply_markup = catalog_pagination(page=new_page)

    await callback_query.message.edit_reply_markup(reply_markup=reply_markup)

    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} перешел на страницу {new_page} каталога.")

# Обработка кнопки "Просмотреть заказы"
@dp.message(F.text == "Просмотреть заказы", F.from_user.id == ADMIN_ID)
async def view_orders(message: types.Message):
    orders = get_all_orders()
    if not orders:
        await message.answer("Нет доступных заказов.", parse_mode='HTML')
        logger.info("Администратор запросил заказы, но они отсутствуют.")
    else:
        response = "Список заказов:\n\n"
        for order in orders:
            telegram_username = f"@{order['telegram_username']}" if order['telegram_username'] else "Не указан"
            response += (
                f"Заказ ID: {order['id']}\n"
                f"Telegram: {telegram_username}\n"
                f"Сыр: {order['cheese_name']}\n"
                f"Имя клиента: {order['customer_name']}\n"
                f"Телефон: {order['phone']}\n"
                f"Количество: {order['quantity']} грамм\n"
                f"Способ получения: {order['delivery_method']}\n"
                f"Адрес: {order['address'] if order['address'] else 'Не требуется'}\n"
                f"Время заказа: {order['timestamp']}\n\n"
            )
        await message.answer(response, parse_mode='HTML')
        logger.info(f"Администратор {message.from_user.id} просмотрел список заказов.")

@dp.message(F.text == "Удалить сыр", F.from_user.id == ADMIN_ID)
async def delete_cheese_button(message: types.Message, state: FSMContext):
    await list_cheeses_for_deletion(message, state)




# Обработка выбора сыра
@dp.callback_query(F.data.startswith('cheese_'))
async def cheese_info(callback_query: types.CallbackQuery):
    try:
        cheese_id = int(callback_query.data.split('_')[1])
        logger.debug(f"Информация о сыре с ID={cheese_id} запрошена.")
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID сыра.", show_alert=True)
        logger.error("Некорректный ID сыра.")
        return

    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price, photo FROM cheeses WHERE id = ?", (cheese_id,))
    cheese = cursor.fetchone()
    conn.close()

    if not cheese:
        await callback_query.answer("Сыр не найден.", show_alert=True)
        logger.warning(f"Сыр с ID={cheese_id} не найден.")
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Заказать", callback_data=f"order_{cheese_id}"),
        InlineKeyboardButton(text="Назад", callback_data="back_to_catalog")
    )

    await bot.send_photo(
        chat_id=callback_query.from_user.id,
        photo=cheese[3],
        caption=f"<b>{cheese[0]}</b>\n\n{cheese[1]}\n\nЦена за 100г: {cheese[2]} LKR.",
        reply_markup=builder.as_markup(),
        parse_mode='HTML'
    )
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} просматривает сыр {cheese[0]} (ID={cheese_id}).")


# Обработка нажатия кнопки "Назад" при выборе сыра
@dp.callback_query(F.data == "back_to_catalog")
async def go_back_to_catalog(callback_query: types.CallbackQuery):
    # Попытка удалить сообщение с информацией о сыре
    try:
        await callback_query.message.delete()
        logger.debug("Сообщение с информацией о сыре удалено.")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    await callback_query.message.answer("Выберите сыр из списка:", reply_markup=catalog_pagination(), parse_mode='HTML')
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} вернулся в каталог.")


# Обработка заказа
@dp.callback_query(F.data.startswith('order_'), StateFilter(None))
async def order_cheese(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        cheese_id = int(callback_query.data.split('_')[1])
        logger.debug(f"Пользователь {callback_query.from_user.id} заказал сыр с ID={cheese_id}.")
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID заказа.", show_alert=True)
        logger.error("Некорректный ID заказа.")
        return

    # Сохраняем ID выбранного сыра
    await state.update_data(cheese_id=cheese_id)
    await state.set_state(OrderForm.name)
    await bot.send_message(callback_query.from_user.id, "Введите ваше имя:", reply_markup=cancel_order_keyboard(), parse_mode='HTML')
    await callback_query.answer()


# Обработка имени
@dp.message(StateFilter(OrderForm.name))
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if name:
        await state.update_data(name=name)
        await state.set_state(OrderForm.phone)
        await message.answer("Введите ваш телефон:", reply_markup=cancel_order_keyboard(), parse_mode='HTML')
        logger.info(f"Пользователь {message.from_user.id} ввел имя: {name}")
    else:
        await message.answer("Пожалуйста, введите ваше имя.", reply_markup=cancel_order_keyboard(), parse_mode='HTML')
        logger.warning(f"Пользователь {message.from_user.id} попытался ввести пустое имя.")


# Обработка телефона
@dp.message(StateFilter(OrderForm.phone))
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if phone:
        await state.update_data(phone=phone)
        await state.set_state(OrderForm.quantity)
        await message.answer("Введите количество грамм сыра (от 100 до 2000 грамм, кратно 100):", reply_markup=cancel_order_keyboard(), parse_mode='HTML')
        logger.info(f"Пользователь {message.from_user.id} ввел телефон: {phone}")
    else:
        await message.answer("Пожалуйста, введите ваш телефон.", reply_markup=cancel_order_keyboard(), parse_mode='HTML')
        logger.warning(f"Пользователь {message.from_user.id} попытался ввести пустой телефон.")


# Обработка адреса доставки
@dp.message(StateFilter(OrderForm.address), F.from_user.id != ADMIN_ID)
async def process_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    if address:
        user_data = await state.get_data()
        # Получаем Telegram-ник пользователя
        telegram_username = message.from_user.username
        # Сохранение заказа с адресом
        save_order(
            user_id=message.from_user.id,
            telegram_username=telegram_username,
            cheese_id=user_data['cheese_id'],
            name=user_data['name'],
            phone=user_data['phone'],
            quantity=user_data['quantity'],
            delivery_method="Доставка",
            address=address
        )

        await notify_admin({
            'name': user_data['name'],
            'telegram_username': telegram_username,
            'phone': user_data['phone'],
            'quantity': user_data['quantity'],
            'delivery_method': "Доставка",
            'address': address,
            'cheese_id': user_data['cheese_id']
        })

        await message.answer(
            f"Спасибо за заказ, {user_data['name']}!\n\n"
            f"Телефон: {user_data['phone']}\n"
            f"Количество: {user_data['quantity']} грамм\n"
            f"Способ получения: Доставка\n"
            f"Адрес: {address}", reply_markup=cancel_order_keyboard(),
            parse_mode='HTML'
        )
        await state.clear()
        logger.info(f"Заказ пользователя {message.from_user.id} завершен и сохранён с адресом: {address}.")
    else:
        await message.answer("Пожалуйста, введите корректный адрес для доставки.", reply_markup=cancel_order_keyboard(), parse_mode='HTML')
        logger.warning(f"Пользователь {message.from_user.id} попытался ввести пустой адрес.")


# Обработка количества грамм сыра
@dp.message(StateFilter(OrderForm.quantity))
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if 100 <= quantity <= 2000 and quantity % 100 == 0:
            await state.update_data(quantity=quantity)
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="Самовывоз", callback_data="pickup"),
                InlineKeyboardButton(text="Доставка", callback_data="delivery")
            )
            await state.set_state(OrderForm.delivery)
            await message.answer("Выберите способ получения:", reply_markup=builder.as_markup(), parse_mode='HTML')
            logger.info(f"Пользователь {message.from_user.id} выбрал количество: {quantity} грамм.")
        else:
            await message.answer("Пожалуйста, введите количество грамм сыра от 100 до 2000, кратное 100.", parse_mode='HTML')
            logger.warning(f"Пользователь {message.from_user.id} ввел некорректное количество: {message.text}")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (например, 500).", parse_mode='HTML')
        logger.warning(f"Пользователь {message.from_user.id} ввел нечисловое значение для количества: {message.text}")



# Обработка выбора способа получения
@dp.callback_query(F.data.in_(['pickup', 'delivery']), StateFilter(OrderForm.delivery))
async def process_delivery(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    delivery_method = "Самовывоз" if callback_query.data == 'pickup' else "Доставка"
    logger.info(f"Пользователь {callback_query.from_user.id} выбрал способ получения: {delivery_method}")

    if delivery_method == "Самовывоз":
        # Получаем Telegram-ник пользователя
        telegram_username = callback_query.from_user.username
        # Сохранение заказа без адреса
        save_order(
            user_id=callback_query.from_user.id,
            telegram_username=telegram_username,
            cheese_id=user_data['cheese_id'],
            name=user_data['name'],
            phone=user_data['phone'],
            quantity=user_data['quantity'],
            delivery_method=delivery_method,
            address=None  # Адрес не требуется
        )

        await notify_admin({
            'name': user_data['name'],
            'telegram_username': telegram_username,
            'phone': user_data['phone'],
            'quantity': user_data['quantity'],
            'delivery_method': "Самовывоз",
            'address': "Самовывоз",
            'cheese_id': user_data['cheese_id']
        })

        await bot.send_message(
            callback_query.from_user.id,
            f"Спасибо за заказ, {user_data['name']}!\n\n"
            f"Телефон: {user_data['phone']}\n"
            f"Количество: {user_data['quantity']} грамм\n"
            f"Способ получения: {delivery_method}",
            parse_mode='HTML'
        )
        await state.clear()
        await callback_query.answer()
        logger.info(f"Заказ пользователя {callback_query.from_user.id} завершен и сохранён без адреса.")
    else:
        # Переходим к вводу адреса
        await state.set_state(OrderForm.address)
        await bot.send_message(
            callback_query.from_user.id,
            "Введите ваш адрес для доставки:", reply_markup=cancel_order_keyboard(),
            parse_mode='HTML'
        )
        await callback_query.answer()
        logger.info(f"Пользователь {callback_query.from_user.id} выбрал доставку и должен ввести адрес.")



# Админка для добавления сыра
@dp.message(Command("add_cheese"), F.from_user.id == ADMIN_ID)
async def add_cheese(message: types.Message, state: FSMContext):
    await state.set_state(AddCheeseForm.name)
    await message.answer("Введите название сыра:", parse_mode='HTML')
    logger.info(f"Администратор {message.from_user.id} начал добавление нового сыра.")


@dp.message(StateFilter(AddCheeseForm.name), F.from_user.id == ADMIN_ID)
async def process_cheese_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if name:
        await state.update_data(name=name)
        await state.set_state(AddCheeseForm.description)
        await message.answer("Введите описание сыра:", parse_mode='HTML')
        logger.info(f"Администратор {message.from_user.id} ввел название сыра: {name}")
    else:
        await message.answer("Пожалуйста, введите название сыра.", parse_mode='HTML')
        logger.warning(f"Администратор {message.from_user.id} попытался ввести пустое название.")


@dp.message(StateFilter(AddCheeseForm.description), F.from_user.id == ADMIN_ID)
async def process_cheese_description(message: types.Message, state: FSMContext):
    description = message.text.strip()
    if description:
        await state.update_data(description=description)
        await state.set_state(AddCheeseForm.price)
        await message.answer("Введите цену за 100 грамм:", parse_mode='HTML')
        logger.info(f"Администратор {message.from_user.id} ввел описание сыра: {description}")
    else:
        await message.answer("Пожалуйста, введите описание сыра.", parse_mode='HTML')
        logger.warning(f"Администратор {message.from_user.id} попытался ввести пустое описание.")


@dp.message(StateFilter(AddCheeseForm.price), F.from_user.id == ADMIN_ID)
async def process_cheese_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
        if price > 0:
            await state.update_data(price=price)
            await state.set_state(AddCheeseForm.photo)
            await message.answer("Отправьте фотографию сыра:", parse_mode='HTML')
            logger.info(f"Администратор {message.from_user.id} ввел цену: {price}")
        else:
            await message.answer("Цена должна быть положительным числом. Попробуйте еще раз.", parse_mode='HTML')
            logger.warning(f"Администратор {message.from_user.id} ввел отрицательную цену: {message.text}")
    except ValueError:
        await message.answer("Введите корректную цену (число). Попробуйте еще раз.", parse_mode='HTML')
        logger.warning(f"Администратор {message.from_user.id} ввел некорректную цену: {message.text}")


@dp.message(StateFilter(AddCheeseForm.photo), F.from_user.id == ADMIN_ID, F.content_type == ContentType.PHOTO)
async def process_cheese_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()
    logger.debug(f"Администратор {message.from_user.id} отправил фотографию для сыра: {photo_file_id}")

    # Сохранение данных в базу
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cheeses (name, description, price, photo) VALUES (?, ?, ?, ?)",
        (data['name'], data['description'], data['price'], photo_file_id)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("Сыр успешно добавлен!", parse_mode='HTML')
    logger.info(f"Администратор {message.from_user.id} добавил новый сыр: {data['name']}")


# Админка для редактирования сыра
@dp.message(Command("edit_cheese"), F.from_user.id == ADMIN_ID)
async def edit_cheese(message: types.Message, state: FSMContext):
    # Показываем список сыров
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM cheeses")
    cheeses = cursor.fetchall()
    conn.close()

    if not cheeses:
        await message.answer("Нет доступных сыров для редактирования.", parse_mode='HTML')
        logger.info("Администратор попытался редактировать сыр, но база пустая.")
        return

    # Создаем inline-кнопки для выбора сыра
    builder = InlineKeyboardBuilder()
    for cheese in cheeses:
        builder.add(InlineKeyboardButton(text=cheese[1], callback_data=f"edit_cheese_{cheese[0]}"))

    await message.answer("Выберите сыр для редактирования:", reply_markup=builder.as_markup(), parse_mode='HTML')
    logger.info(f"Администратор {message.from_user.id} начал редактирование сыра.")


# Обработка выбора сыра для редактирования
@dp.callback_query(F.data.startswith('edit_cheese_'), F.from_user.id == ADMIN_ID)
async def choose_cheese_for_edit(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        cheese_id = int(callback_query.data.split('_')[-1])
        logger.debug(f"Администратор {callback_query.from_user.id} выбрал для редактирования сыр с ID={cheese_id}.")
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID сыра.", show_alert=True)
        logger.error("Некорректный ID сыра при редактировании.")
        return

    await state.update_data(edit_cheese_id=cheese_id)

    # Получаем данные о выбранном сыра
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price FROM cheeses WHERE id = ?", (cheese_id,))
    cheese = cursor.fetchone()
    conn.close()

    if not cheese:
        await callback_query.answer("Сыр не найден.", show_alert=True)
        logger.warning(f"Сыр с ID={cheese_id} не найден при редактировании.")
        return

    await callback_query.message.answer(
        f"Текущие данные:\n"
        f"Название: {cheese[0]}\n"
        f"Описание: {cheese[1]}\n"
        f"Цена за 100 г: {cheese[2]}"
    )
    await callback_query.message.answer(
        "Введите новое название сыра (или отправьте текущее, если не хотите изменять):",
        parse_mode='HTML'
    )

    await state.set_state(EditCheeseForm.name)
    await callback_query.answer()
    logger.info(f"Администратор {callback_query.from_user.id} начал изменение названия сыра с ID={cheese_id}.")


# Продолжаем процесс редактирования сыра
@dp.message(StateFilter(EditCheeseForm.name), F.from_user.id == ADMIN_ID)
async def process_edit_cheese_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if name:
        await state.update_data(name=name)
        await state.set_state(EditCheeseForm.description)
        await message.answer("Введите новое описание сыра:", parse_mode='HTML')
        logger.info(f"Администратор {message.from_user.id} изменил название сыра на: {name}")
    else:
        await message.answer("Пожалуйста, введите название сыра.", parse_mode='HTML')
        logger.warning(f"Администратор {message.from_user.id} попытался ввести пустое название.")



@dp.message(StateFilter(EditCheeseForm.description), F.from_user.id == ADMIN_ID)
async def process_edit_cheese_description(message: types.Message, state: FSMContext):
    description = message.text.strip()
    if description:
        await state.update_data(description=description)
        await state.set_state(EditCheeseForm.price)
        await message.answer("Введите новую цену за 100 грамм:", parse_mode='HTML')
        logger.info(f"Администратор {message.from_user.id} изменил описание сыра на: {description}")
    else:
        await message.answer("Пожалуйста, введите описание сыра.", parse_mode='HTML')
        logger.warning(f"Администратор {message.from_user.id} попытался ввести пустое описание.")


@dp.message(StateFilter(EditCheeseForm.price), F.from_user.id == ADMIN_ID)
async def process_edit_cheese_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
        if price > 0:
            await state.update_data(price=price)
            await state.set_state(EditCheeseForm.photo)
            await message.answer("Отправьте новую фотографию сыра (или отправьте /skip для пропуска):", parse_mode='HTML')
            logger.info(f"Администратор {message.from_user.id} ввел новую цену: {price}")
        else:
            await message.answer("Цена должна быть положительным числом. Попробуйте ещё раз.", parse_mode='HTML')
            logger.warning(f"Администратор {message.from_user.id} ввел отрицательную цену: {message.text}")
    except ValueError:
        await message.answer("Введите корректную цену (число). Попробуйте ещё раз.", parse_mode='HTML')
        logger.warning(f"Администратор {message.from_user.id} ввел некорректную цену: {message.text}")


@dp.message(StateFilter(EditCheeseForm.photo), F.from_user.id == ADMIN_ID, F.content_type == ContentType.PHOTO)
async def process_edit_cheese_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cheese_id = data.get('edit_cheese_id')
    if not cheese_id:
        await message.answer("Ошибка: ID сыра не найден.", parse_mode='HTML')
        logger.error("ID сыра не найден в состоянии при обновлении фото.")
        await state.clear()
        return

    photo_file_id = message.photo[-1].file_id
    logger.debug(f"Администратор {message.from_user.id} отправил новую фотографию для сыра ID={cheese_id}.")

    # Обновление данных в базе данных
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cheeses SET name = ?, description = ?, price = ?, photo = ? WHERE id = ?",
        (data['name'], data['description'], data['price'], photo_file_id, cheese_id)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("Данные сыра успешно обновлены!", parse_mode='HTML')
    logger.info(f"Сыр с ID={cheese_id} успешно обновлен администратором {message.from_user.id}.")

# Обработка пагинации удаления сыра (Вперед и Назад)
@dp.callback_query(F.data.startswith("deleted_"), F.from_user.id == ADMIN_ID)
async def navigate_deletion_catalog(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        action, current_page = callback_query.data.split('_')[1], int(callback_query.data.split('_')[2])
        logger.debug(f"Навигация удаления каталога: действие={action}, текущая страница={current_page}")
    except (IndexError, ValueError):
        await callback_query.answer("Некорректные данные пагинации удаления.", show_alert=True)
        logger.error("Некорректные данные пагинации удаления.")
        return

    if action == "next":
        new_page = current_page
    elif action == "prev":
        new_page = current_page
    else:
        await callback_query.answer("Некорректное действие.", show_alert=True)
        logger.error("Некорректное действие пагинации удаления.")
        logger.error(action)
        return

    reply_markup = deletion_pagination(page=new_page)
    await callback_query.message.edit_reply_markup(reply_markup=reply_markup)

    await callback_query.answer()
    logger.info(f"Администратор {callback_query.from_user.id} перешел на страницу {new_page} удаления каталога.")


# Обработка выбора сыра для удаления
@dp.callback_query(F.data.startswith('delete_cheese_'), F.from_user.id == ADMIN_ID)
async def choose_cheese_for_deletion(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        cheese_id = int(callback_query.data.split('_')[2])
        logger.debug(f"Администратор {callback_query.from_user.id} выбрал для удаления сыр с ID={cheese_id}.")
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID сыра для удаления.", show_alert=True)
        logger.error("Некорректный ID сыра для удаления.")
        return

    # Сохраняем ID выбранного сыра в состоянии
    await state.update_data(cheese_id=cheese_id)
    await state.set_state(DeleteCheeseForm.confirm)

    # Получаем название сыра для отображения
    cheese_name = get_cheese_name(cheese_id)

    # Создаем клавиатуру с подтверждением
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Да, удалить", callback_data="confirm_delete"),
        InlineKeyboardButton(text="Нет, отменить", callback_data="cancel_delete")
    )

    await callback_query.message.answer(
        f"Вы уверены, что хотите удалить сыр <b>{cheese_name}</b>?",
        reply_markup=builder.as_markup(),
        parse_mode='HTML'
    )
    await callback_query.answer()
    logger.info(f"Администратор {callback_query.from_user.id} подтвердил удаление сыра ID={cheese_id}.")

# Обработка подтверждения удаления
@dp.callback_query(F.data == "confirm_delete", StateFilter(DeleteCheeseForm.confirm), F.from_user.id == ADMIN_ID)
async def confirm_delete(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cheese_id = data.get('cheese_id')

    if not cheese_id:
        await callback_query.answer("Ошибка: ID сыра не найден.", show_alert=True)
        logger.error("ID сыра не найден в состоянии при подтверждении удаления.")
        await state.clear()
        return

    # Удаление сыра из базы данных
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cheeses WHERE id = ?", (cheese_id,))
    conn.commit()
    conn.close()

    await callback_query.message.answer(f"Сыр <b>{get_cheese_name(cheese_id)}</b> успешно удален.", parse_mode='HTML')
    await state.clear()
    await callback_query.answer()
    logger.info(f"Администратор {callback_query.from_user.id} удалил сыр ID={cheese_id}.")

# Обработка отмены удаления
@dp.callback_query(F.data == "cancel_delete", StateFilter(DeleteCheeseForm.confirm), F.from_user.id == ADMIN_ID)
async def cancel_delete(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer("Удаление сыра отменено.", parse_mode='HTML')
    await state.clear()
    await callback_query.answer()
    logger.info(f"Администратор {callback_query.from_user.id} отменил удаление сыра.")



# Обработка команды /skip для пропуска изменения фотографии
@dp.message(StateFilter(EditCheeseForm.photo), F.from_user.id == ADMIN_ID, F.text.lower() == "/skip")
async def skip_edit_cheese_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cheese_id = data.get('edit_cheese_id')
    if not cheese_id:
        await message.answer("Ошибка: ID сыра не найден.", parse_mode='HTML')
        logger.error("ID сыра не найден в состоянии при пропуске изменения фото.")
        await state.clear()
        return

    logger.debug(f"Администратор {message.from_user.id} решил не изменять фотографию сыра ID={cheese_id}.")

    # Получение текущей фотографии сыра
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT photo FROM cheeses WHERE id = ?", (cheese_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        await message.answer("Сыр не найден.", parse_mode='HTML')
        logger.warning(f"Сыр с ID={cheese_id} не найден при пропуске изменения фото.")
        await state.clear()
        return

    photo_file_id = result[0]

    # Обновление данных в базе данных без изменения фото
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cheeses SET name = ?, description = ?, price = ?, photo = ? WHERE id = ?",
        (data['name'], data['description'], data['price'], photo_file_id, cheese_id)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("Данные сыра успешно обновлены без изменения фотографии!", parse_mode='HTML')
    logger.info(f"Сыр с ID={cheese_id} успешно обновлен без изменения фото администратором {message.from_user.id}.")


# Обработка кнопок "О нас" и "Контакты"
@dp.message(F.text == "О нас")
async def about_us(message: types.Message):
    await message.answer("Мы предлагаем лучшие сыры от проверенных производителей!", parse_mode='HTML')
    logger.info(f"Пользователь {message.from_user.id} запросил информацию 'О нас'.")

@dp.callback_query(F.data == "cancel_order")
async def cancel_order(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()  # Сбрасываем все состояния FSM
    await callback_query.message.answer("Ваш заказ был отменён.", reply_markup=types.ReplyKeyboardRemove())
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} отменил заказ.")

@dp.message(F.text == "Контакты")
async def contacts(message: types.Message):
    await message.answer("Свяжитесь с нами:\nТелефон: +7 (XXX) XXX-XX-XX\nEmail: contact@cheese-shop.ru",
                         parse_mode='HTML')
    logger.info(f"Пользователь {message.from_user.id} запросил информацию 'Контакты'.")

async def list_cheeses_for_deletion(message: types.Message, state: FSMContext):
    await state.set_state(None)  # Убедимся, что нет активных состояний
    await message.answer("Выберите сыр для удаления:", reply_markup=deletion_pagination(), parse_mode='HTML')
    logger.info(f"Администратор {message.from_user.id} начал процесс удаления сыра.")

def get_all_orders():
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT orders.id, orders.user_id, orders.telegram_username, cheeses.name, orders.name, orders.phone, orders.quantity, orders.address, orders.delivery_method, orders.timestamp
    FROM orders
    JOIN cheeses ON orders.cheese_id = cheeses.id
    ORDER BY orders.timestamp DESC
    ''')
    orders = cursor.fetchall()
    conn.close()

    # Преобразуем результат в список словарей для удобства
    orders_list = []
    for order in orders:
        orders_list.append({
            'id': order[0],
            'user_id': order[1],
            'telegram_username': order[2],
            'cheese_name': order[3],
            'customer_name': order[4],
            'phone': order[5],
            'quantity': order[6],
            'address': order[7],
            'delivery_method': order[8],
            'timestamp': order[9]
        })
    return orders_list


def save_order(user_id, telegram_username, cheese_id, name, phone, quantity, delivery_method, address=None):
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO orders (user_id, telegram_username, cheese_id, name, phone, quantity, delivery_method, address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (user_id, telegram_username, cheese_id, name, phone, quantity, delivery_method, address)
    )
    conn.commit()
    conn.close()
    logger.info(f"Заказ сохранён: Пользователь ID={user_id}, Ник={telegram_username}, Сыр ID={cheese_id}, Количество={quantity}г, Способ получения={delivery_method}, Адрес={address}")

async def notify_admin(order_data):
    telegram_username = f"@{order_data['telegram_username']}" if order_data['telegram_username'] else "Не указан"
    message = (
        f"🆕 Новый заказ!\n\n"
        f"Имя: {order_data['name']}\n"
        f"Telegram: {telegram_username}\n"
        f"Телефон: {order_data['phone']}\n"
        f"Количество: {order_data['quantity']} грамм\n"
        f"Способ получения: {order_data['delivery_method']}\n"
        f"Адрес: {order_data.get('address', 'Самовывоз')}\n\n"
        f"🧀 Заказанный сыр: {get_cheese_name(order_data['cheese_id'])}"
    )

    try:
        await bot.send_message(ADMIN_ID, message, parse_mode='HTML')
        logger.info(f"Уведомление о новом заказе отправлено администратору (ID: {ADMIN_ID}).")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления администратору: {e}")

def get_cheese_name(cheese_id):
    conn = sqlite3.connect('cheese_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM cheeses WHERE id = ?", (cheese_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Неизвестный сыр"

# Функция для получения сыров с пагинацией для удаления
def get_cheeses_for_deletion(offset=0, limit=10):
    return get_cheeses(offset=offset, limit=limit)

# Пагинация для удаления сыра
def deletion_pagination(page=0, limit=10):
    builder = InlineKeyboardBuilder()
    offset = page * limit
    cheeses = get_cheeses_for_deletion(offset=offset, limit=limit + 1)  # Запрашиваем на одну запись больше

    has_next = False
    if len(cheeses) > limit:
        has_next = True
        cheeses = cheeses[:limit]  # Обрезаем лишнюю запись

    for cheese in cheeses:
        builder.add(InlineKeyboardButton(text=cheese[1], callback_data=f"delete_cheese_{cheese[0]}"))

    builder.adjust(2)  # Размещаем по 2 кнопки в строку

    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"deleted_prev_{page-1}"))
    if has_next:
        navigation_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"deleted_next_{page+1}"))

    if navigation_buttons:
        builder.row(*navigation_buttons)  # Навигационные кнопки на отдельной строке

    return builder.as_markup()

def cancel_order_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Отменить заказ", callback_data="cancel_order"))
    return builder.as_markup()

# Главная функция для запуска бота
async def main():
    setup_db()
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


# Запуск бота
if __name__ == '__main__':
    asyncio.run(main())
