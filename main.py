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

# Переменные окружения
BOT_TOKEN   = os.getenv("BOT_TOKEN")
GROUP_ID    = os.getenv("GROUP_CHAT_ID")   # Должно совпадать с именем в Render
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT        = int(os.getenv("PORT", 8000))

if not BOT_TOKEN or not GROUP_ID or not WEBHOOK_URL:
    logging.error("Не заданы обязательные переменные окружения")
    exit(1)

# Инициализация бота и диспетчера с FSM
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = FastAPI()

# Определение состояний
class Form(StatesGroup):
    fio     = State()
    phone   = State()
    company = State()
    tariff  = State()

# Обработчик команды /start
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await state.set_state(Form.fio.state)  # задаём первую ступень FSM
    await message.answer("Привет! Пожалуйста, введите ваше ФИО:")

# Обработка ФИО
@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await state.set_state(Form.phone.state)
    await message.answer("Введите номер телефона:")

# Обработка телефона
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(Form.company.state)
    await message.answer("Введите название вашей компании:")

# Обработка компании
@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    await state.set_state(Form.tariff.state)
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add("Старт", "Бизнес", "Корпоратив")
    await message.answer("Выберите тариф:", reply_markup=keyboard)

# Обработка тарифа и отправка в группу
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

# Endpoint для вебхука
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        logging.exception("Не удалось распарсить JSON вебхука")
        return {"ok": False}
    logging.info(f"Webhook payload: {payload!r}")
    try:
        update = types.Update(**payload)
        await dp.process_update(update)
    except Exception:
        logging.exception("Ошибка при обработке Update")
    return {"ok": True}

# Локальный запуск для отладки
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
