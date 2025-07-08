import os
import logging

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Чтение переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")  # Установите в Render: -1002344973979

if not BOT_TOKEN or not GROUP_ID:
    logging.error("Не заданы переменные окружения BOT_TOKEN и/или GROUP_ID")
    exit(1)

# Инициализация бота, диспетчера и памяти для FSM
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = FastAPI()

# Определение состояний FSM
class Form(StatesGroup):
    fio = State()
    phone = State()
    company = State()
    tariff = State()

# Обработчик команды /start
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await Form.fio.set()
    await message.answer("Привет! Пожалуйста, введите ваше ФИО:")

# Обработка ФИО
@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await Form.next()
    await message.answer("Введите номер телефона:")

# Обработка телефона
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await Form.next()
    await message.answer("Введите название вашей компании:")

# Обработка компании
@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    await Form.next()
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add("Старт", "Бизнес", "Корпоратив")
    await message.answer("Выберите тариф:", reply_markup=keyboard)

# Обработка тарифа и отправка заявки в группу
@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    await state.update_data(tariff=message.text)
    data = await state.get_data()
    text = (
        f"📥 Новая заявка из Telegram-бота:\n"
        f"👤 ФИО: {data['fio']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"💳 Тариф: {data['tariff']}"
    )
    await bot.send_message(chat_id=int(GROUP_ID), text=text)
    await message.answer("Спасибо, ваша заявка отправлена!", reply_markup=ReplyKeyboardRemove())
    await state.finish()

# Вебхук для Telegram
@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

# Точка входа для локального запуска uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
