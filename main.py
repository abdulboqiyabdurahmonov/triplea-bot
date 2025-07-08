import os
import logging
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Переменные окружения
BOT_TOKEN            = os.getenv("BOT_TOKEN")
GROUP_ID             = os.getenv("GROUP_CHAT_ID")
WEBHOOK_URL          = os.getenv("WEBHOOK_URL")
GOOGLE_CREDS_JSON    = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_ID      = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_WORKSHEET_NAME= os.getenv("GOOGLE_WORKSHEET_NAME")
PORT                 = int(os.getenv("PORT", 8000))

# Проверка обязательных env vars
required = [BOT_TOKEN, GROUP_ID, WEBHOOK_URL, GOOGLE_CREDS_JSON, GOOGLE_SHEET_ID, GOOGLE_WORKSHEET_NAME]
if not all(required):
    logging.error("Не заданы обязательные env vars: BOT_TOKEN, GROUP_CHAT_ID, WEBHOOK_URL, GOOGLE_CREDS_JSON, GOOGLE_SHEET_ID, GOOGLE_WORKSHEET_NAME")
    exit(1)

# Инициализация Google Sheets
creds_info = json.loads(GOOGLE_CREDS_JSON)
credentials = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc = gspread.Client(auth=credentials)
worksheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_WORKSHEET_NAME)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = FastAPI()

# Статистика
stats = {"start_count": 0, "complete_count": 0, "durations": []}

# FSM-состояния
class Form(StatesGroup):
    fio     = State()
    phone   = State()
    company = State()
    tariff  = State()

# /start — начало сбора данных
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    stats["start_count"] += 1
    await state.set_state(Form.fio.state)
    await state.update_data(start_ts=datetime.utcnow().isoformat())
    await bot.send_message(chat_id=message.chat.id, text="Привет! Введите ваше ФИО:")

# Обработка ФИО
@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await state.set_state(Form.phone.state)
    await bot.send_message(chat_id=message.chat.id, text="Введите номер телефона:")

# Обработка телефона
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(Form.company.state)
    await bot.send_message(chat_id=message.chat.id, text="Введите название компании:")

# Обработка компании
@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    await state.set_state(Form.tariff.state)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("Старт", "Бизнес", "Корпоратив")
    await bot.send_message(chat_id=message.chat.id, text="Выберите тариф:", reply_markup=kb)

# Обработка тарифа с описанием
@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    tariff = message.text
    # Описание тарифов
    descriptions = {
        "Старт": "Тариф «Старт» — оптимальное решение для небольших команд, включает базовые возможности.",
        "Бизнес": "Тариф «Бизнес» — расширенный функционал для развития вашего бизнеса: CRM-интеграция, аналитика.",
        "Корпоратив": "Тариф «Корпоратив» — полный пакет услуг с приоритетной поддержкой и настройкой."
    }
    desc = descriptions.get(tariff)
    if desc:
        await bot.send_message(chat_id=message.chat.id, text=desc)
    # Сохраняем выбор
    await state.update_data(tariff=tariff)
    data = await state.get_data()
    # Аналитика времени
    start = datetime.fromisoformat(data['start_ts'])
    end = datetime.utcnow()
    duration = (end - start).total_seconds()
    stats['complete_count'] += 1
    stats['durations'].append(duration)
    # Запись в Google Sheets
    row = [data['fio'], data['phone'], data['company'], data['tariff'], data['start_ts'], end.isoformat(), duration]
    try:
        worksheet.append_row(row)
        logging.info("✅ Записали строку в Google Sheets")
    except Exception:
        logging.exception("❌ Не удалось записать строку в Google Sheets")
    # Отправка заявки в группу
    text = (
        f"📥 Новая заявка из Telegram-бота:\n"
        f"👤 ФИО: {data['fio']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"💳 Тариф: {data['tariff']}"
    )
    await bot.send_message(chat_id=int(GROUP_ID), text=text)

# Endpoint для вебхука
@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    logging.info(f"Webhook payload: {payload!r}")
    update = types.Update(**payload)
    await dp.process_update(update)
    return {"ok": True}

# Статистика
@app.get("/stats")
async def get_stats():
    total = stats['start_count']
    done = stats['complete_count']
    conv = done / total if total > 0 else 0
    avg_time = sum(stats['durations']) / len(stats['durations']) if stats['durations'] else 0
    return {"start_count": total, "complete_count": done, "conversion_rate": conv, "avg_time_sec": avg_time}

# Запуск локально
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
