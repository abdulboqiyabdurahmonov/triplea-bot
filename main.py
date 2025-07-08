import os
import logging
import json
import re
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup

# Логирование
logging.basicConfig(level=logging.INFO)

# Переменные окружения
BOT_TOKEN             = os.getenv("BOT_TOKEN")
GROUP_ID              = os.getenv("GROUP_CHAT_ID")
WEBHOOK_URL           = os.getenv("WEBHOOK_URL")
GOOGLE_CREDS_JSON     = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_SHEET_ID       = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME")
PORT                  = int(os.getenv("PORT", 8000))

# Проверка обязательных переменных окружения
required = [BOT_TOKEN, GROUP_ID, WEBHOOK_URL, GOOGLE_CREDS_JSON, GOOGLE_SHEET_ID, GOOGLE_WORKSHEET_NAME]
if not all(required):
    logging.error("Не заданы обязательные env vars: BOT_TOKEN, GROUP_CHAT_ID, WEBHOOK_URL, GOOGLE_CREDS_JSON, GOOGLE_SHEET_ID, GOOGLE_WORKSHEET_NAME")
    exit(1)

# Инициализация Google Sheets client
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

# Парсер текстового сообщения заявки
def parse_request_text(text: str):
    # Ожидаем строки с форматом '👤 ФИО: ...', '📞 Телефон: ...', '🏢 Компания: ...', '💳 Тариф: ...'
    data = {}
    for line in text.splitlines():
        if line.startswith('👤') and ':' in line:
            data['fio'] = line.split(':',1)[1].strip()
        if line.startswith('📞') and ':' in line:
            data['phone'] = line.split(':',1)[1].strip()
        if line.startswith('🏢') and ':' in line:
            data['company'] = line.split(':',1)[1].strip()
        if line.startswith('💳') and ':' in line:
            data['tariff'] = line.split(':',1)[1].strip()
    return data

# /start: начало FSM-сессии
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    stats["start_count"] += 1
    await state.set_state(Form.fio.state)
    await state.update_data(start_ts=datetime.utcnow().isoformat())
    await bot.send_message(chat_id=message.chat.id, text="Привет! Введите ваше ФИО:")

# Обработка шагов FSM
@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await state.set_state(Form.phone.state)
    await bot.send_message(message.chat.id, text="Введите номер телефона:")

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(Form.company.state)
    await bot.send_message(message.chat.id, text="Введите название компании:")

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    await state.set_state(Form.tariff.state)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("Старт", "Бизнес", "Корпоратив")
    await bot.send_message(message.chat.id, text="Выберите тариф:", reply_markup=kb)

@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    await state.update_data(tariff=message.text)
    data = await state.get_data()
    # расчёт времени
    start = datetime.fromisoformat(data['start_ts'])
    end = datetime.utcnow()
    duration = (end - start).total_seconds()
    stats['complete_count'] += 1
    stats['durations'].append(duration)
    # сохранение в Google Sheets
    row = [data.get('fio'), data.get('phone'), data.get('company'), data.get('tariff'), data['start_ts'], end.isoformat(), duration]
    try:
        worksheet.append_row(row)
        logging.info("✅ Сохранена заявка бота в Google Sheets")
    except Exception:
        logging.exception("❌ Ошибка сохранения заявки бота")
    # отправка в группу
    text = ("📥 Новая заявка из Telegram-бота:\n" +
            f"👤 {data.get('fio')}\n" +
            f"📞 {data.get('phone')}\n" +
            f"🏢 {data.get('company')}\n" +
            f"💳 {data.get('tariff')}")
    await bot.send_message(chat_id=int(GROUP_ID), text=text)
    await state.finish()

# Логирование заявок из группы, включая сайта
@dp.message_handler(lambda msg: msg.chat.id == int(GROUP_ID), content_types=types.ContentTypes.TEXT)
async def log_group_request(msg: types.Message):
    # Разбираем текст заявки
    if msg.text.startswith("📥 Новая заявка"):
        data = parse_request_text(msg.text)
        # Время и источник
        source = "бот" if "бота" in msg.text else "сайта"
        now = datetime.utcfromtimestamp(msg.date).isoformat()
        row = [
            data.get('fio'), data.get('phone'), data.get('company'), data.get('tariff'),
            now, source
        ]
        try:
            worksheet.append_row(row)
            logging.info(f"✅ Сохранена заявка {source} в Google Sheets")
        except Exception:
            logging.exception(f"❌ Ошибка сохранения заявки {source}")

# Вебхук для Telegram
@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    logging.info(f"Webhook payload: {payload!r}")
    update = types.Update(**payload)
    await dp.process_update(update)
    return {"ok": True}

# Эндпоинт статистики
@app.get("/stats")
async def get_stats():
    total = stats['start_count']
    done = stats['complete_count']
    conv = done / total if total > 0 else 0
    avg_time = sum(stats['durations']) / len(stats['durations']) if stats['durations'] else 0
    return {"start_count": total, "complete_count": done, "conversion_rate": conv, "avg_time_sec": avg_time}

from fastapi import HTTPException, Header

# Секретный ключ, чтобы никто чужой не постучался
SITE_SECRET = os.getenv("SITE_WEBHOOK_SECRET")

@app.post("/site-request")
async def site_request(request: Request, x_site_secret: str = Header(...)):
    # 0) Проверяем заголовок безопасности
    if SITE_SECRET is None or x_site_secret != SITE_SECRET:
        raise HTTPException(401, "Unauthorized")

    # 1) Читаем JSON из тела
    payload = await request.json()
    # Ожидаем что-то вроде:
    # { "fio":"Иванов Иван", "phone":"+71234567890", "company":"Acme", "tariff":"Бизнес" }
    fio     = payload.get("fio")
    phone   = payload.get("phone")
    company = payload.get("company")
    tariff  = payload.get("tariff")
    if not all([fio, phone, company, tariff]):
        raise HTTPException(400, "Missing fields")

    # 2) Записываем в Google Sheets
    now = datetime.utcnow().isoformat()
    row = [fio, phone, company, tariff, now, "сайта"]
    try:
        worksheet.append_row(row)
        logging.info("✅ Записали сайт-заявку в Google Sheets")
    except Exception:
        logging.exception("❌ Ошибка записи сайт-заявки")

    # 3) Шлём в Telegram-группу
    text = (
        "📥 Новая заявка с сайта:\n"
        f"👤 {fio}\n"
        f"📞 {phone}\n"
        f"🏢 {company}\n"
        f"💳 {tariff}"
    )
    await bot.send_message(chat_id=int(GROUP_ID), text=text)

    return {"ok": True}

# Запуск для локальной отладки
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
