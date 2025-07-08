import os
import logging

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

# =========== Логирование ===========
logging.basicConfig(level=logging.INFO)

# =========== Переменные окружения ===========
BOT_TOKEN    = os.getenv("BOT_TOKEN")
GROUP_ID     = os.getenv("GROUP_CHAT_ID")   # ← сюда из Dashboard: GROUP_CHAT_ID = -1002344973979
WEBHOOK_URL  = os.getenv("WEBHOOK_URL")     # ← например https://triplea-bot-1.onrender.com/webhook
PORT         = int(os.getenv("PORT", 8000))

if not BOT_TOKEN or not GROUP_ID or not WEBHOOK_URL:
    logging.error("Не заданы BOT_TOKEN, GROUP_CHAT_ID или WEBHOOK_URL")
    exit(1)

# =========== Инициализация бота и диспетчера ===========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = FastAPI()

# =========== FSM-состояния ===========
class Form(StatesGroup):
    fio     = State()
    phone   = State()
    company = State()
    tariff  = State()

# ======== Хэндлеры ========
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await Form.fio.set()
    await message.answer("Привет! Введи, пожалуйста, ваше ФИО:")

@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await Form.next()
    await message.answer("Теперь номер телефона:")

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await Form.next()
    await message.answer("Название вашей компании:")

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    await Form.next()
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("Старт", "Бизнес", "Корпоратив")
    await message.answer("Выберите тариф:", reply_markup=kb)

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
    await message.answer("Спасибо, заявка отправлена!", reply_markup=ReplyKeyboardRemove())
    await state.finish()

# ======== Webhook endpoint для Telegram ========
@app.post("/webhook")
async def telegram_webhook(request: Request):
    upd = types.Update(**await request.json())
    await dp.process_update(upd)
    return {"ok": True}

# ======== Запуск при локальной отладке =========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
