import os, logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

logging.basicConfig(level=logging.INFO)

BOT_TOKEN   = os.getenv("BOT_TOKEN")
GROUP_ID    = os.getenv("GROUP_CHAT_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT        = int(os.getenv("PORT", 8000))

if not BOT_TOKEN or not GROUP_ID or not WEBHOOK_URL:
    logging.error("Не заданы обязательные переменные окружения")
    exit(1)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = FastAPI()

class Form(StatesGroup):
    fio     = State()
    phone   = State()
    company = State()
    tariff  = State()

@dp.message_handler(commands=["start"], state="*")
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.finish()
    await Form.fio.set()
    await msg.answer("Привет! Введи, пожалуйста, ваше ФИО:")

@dp.message_handler(state=Form.fio)
async def process_fio(msg: types.Message, state: FSMContext):
    await state.update_data(fio=msg.text)
    await Form.next()
    await msg.answer("Теперь номер телефона:")

@dp.message_handler(state=Form.phone)
async def process_phone(msg: types.Message, state: FSMContext):
    await state.update_data(phone=msg.text)
    await Form.next()
    await msg.answer("Название вашей компании:")

@dp.message_handler(state=Form.company)
async def process_company(msg: types.Message, state: FSMContext):
    await state.update_data(company=msg.text)
    await Form.next()
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("Старт", "Бизнес", "Корпоратив")
    await msg.answer("Выберите тариф:", reply_markup=kb)

@dp.message_handler(state=Form.tariff)
async def process_tariff(msg: types.Message, state: FSMContext):
    await state.update_data(tariff=msg.text)
    data = await state.get_data()
    text = (
        f"📥 Новая заявка из Telegram-бота:\n"
        f"👤 ФИО: {data['fio']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"💳 Тариф: {data['tariff']}"
    )
    await bot.send_message(chat_id=int(GROUP_ID), text=text)
    await msg.answer("Спасибо, заявка отправлена!", reply_markup=ReplyKeyboardRemove())
    await state.finish()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    upd = types.Update(**await request.json())
    await dp.process_update(upd)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
from aiogram import Bot
from aiogram.dispatcher.dispatcher import Dispatcher

@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    update = types.Update(**payload)

    # 👉 Принудительно выставляем текущий бот и диспетчер
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    await dp.process_update(update)

    # 👉 Сбрасываем, чтобы не засорять contextvars
    Dispatcher.set_current(None)
    Bot.set_current(None)

    return {"ok": True}
