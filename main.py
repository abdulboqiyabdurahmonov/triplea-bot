import os
import logging
import json
import re
import uuid
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Настройка логирования
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

# FSM-состояния
class Form(StatesGroup):
    lang    = State()
    fio     = State()
    phone   = State()
    company = State()
    tariff  = State()

# Сообщения для разных языков: Russian и Uzbek
MESSAGES = {
    'ru': {
        'select_lang': 'Выберите язык:',
        'ask_fio': 'Пожалуйста, введите ваше ФИО:',
        'invalid_fio': 'Некорректное ФИО. Используйте только буквы и пробелы. Попробуйте ещё раз:',
        'ask_phone': 'Введите номер телефона (например, +71234567890):',
        'invalid_phone': 'Некорректный номер. Используйте формат +71234567890. Попробуйте ещё раз:',
        'ask_company': 'Введите название компании:',
        'ask_tariff': 'Выберите тариф:',
        'thank_you': 'Ваша заявка принята! Код для отслеживания: {code}. Мы скоро свяжемся с вами.',
        'cancelled': 'Операция отменена.'
    },
    'uz': {
        'select_lang': 'Tilni tanlang:',
        'ask_fio': "Iltimos, to'liq ismingizni kiriting:",
        'invalid_fio': "Ism noto'g'ri. Faqat harflar va bo'sh joylardan foydalaning. Qayta urinib ko'ring:",
        'ask_phone': "Telefon raqamingizni kiriting (masalan, +998901234567):",
        'invalid_phone': "Noto'g'ri raqam. +998901234567 formatidan foydalaning. Qayta urinib ko'ring:",
        'ask_company': 'Kompaniya nomini kiriting:',
        'ask_tariff': 'Tarifni tanlang:',
        'thank_you': "Arizangiz qabul qilindi! Kuzatish kodi: {code}. Tez orada bog'lanamiz.",
        'cancelled': "Amal bekor qilindi."
    }
}

# /start — выбор языка
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton('Русский 🇷🇺', callback_data='lang_ru'),
        InlineKeyboardButton("O'zbekcha 🇺🇿", callback_data='lang_uz')
    )
    await state.finish()
    await bot.send_message(chat_id=message.chat.id, text=MESSAGES['ru']['select_lang'], reply_markup=kb)
    await Form.lang.set()

# Обработка выбора языка
@dp.callback_query_handler(lambda c: c.data in ['lang_ru','lang_uz'], state=Form.lang)
async def process_lang(callback: types.CallbackQuery, state: FSMContext):
    lang = 'ru' if callback.data == 'lang_ru' else 'uz'
    await state.update_data(lang=lang, start_ts=datetime.utcnow().isoformat())
    await bot.send_message(chat_id=callback.message.chat.id, text=MESSAGES[lang]['ask_fio'])
    await Form.fio.set()
    await callback.answer()

# Команда /cancel
@dp.message_handler(commands=['cancel'], state='*')
async def process_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    await state.finish()
    await bot.send_message(chat_id=message.chat.id, text=MESSAGES[lang]['cancelled'])

# Обработка ФИО
@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    if not re.match(r'^[A-Za-zА-Яа-яЁё ]+$', message.text):
        return await bot.send_message(chat_id=message.chat.id, text=MESSAGES[lang]['invalid_fio'])
    await state.update_data(fio=message.text)
    await Form.phone.set()
    await bot.send_message(chat_id=message.chat.id, text=MESSAGES[lang]['ask_phone'])

# Обработка телефона
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    if not re.match(r'^\+?\d{7,15}$', message.text):
        return await bot.send_message(chat_id=message.chat.id, text=MESSAGES[lang]['invalid_phone'])
    await state.update_data(phone=message.text)
    await Form.company.set()
    await bot.send_message(chat_id=message.chat.id, text=MESSAGES[lang]['ask_company'])

# Обработка компании
@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    await state.update_data(company=message.text)
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton('Старт', callback_data='tariff_Старт'),
        InlineKeyboardButton('Бизнес', callback_data='tariff_Бизнес'),
        InlineKeyboardButton('Корпоратив', callback_data='tariff_Корпоратив')
    )
    await Form.tariff.set()
    await bot.send_message(chat_id=message.chat.id, text=MESSAGES[lang]['ask_tariff'], reply_markup=kb)

# Обработка тарифа и завершение
@dp.callback_query_handler(lambda c: c.data.startswith('tariff_'), state=Form.tariff)
async def process_tariff(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    tariff = callback.data.split('_', 1)[1]
    code = uuid.uuid4().hex[:8].upper()
    start_ts = data['start_ts']
    await state.update_data(tariff=tariff, code=code)

    # Аналитика времени
    start = datetime.fromisoformat(start_ts)
    end = datetime.utcnow()
    duration = (end - start).total_seconds()

    # Запись в Google Sheets
    row = [data['fio'], data['phone'], data['company'], tariff, start_ts, end.isoformat(), duration, code]
    try:
        worksheet.append_row(row)
        logging.info("✅ Записали строку в Google Sheets")
    except Exception:
        logging.exception("❌ Ошибка записи в Google Sheets")

    # Отправка в Telegram-группу
    text = (
        f"📥 Новая заявка из Telegram-бота:\n"
        f"👤 {data['fio']}\n"
        f"📞 {data['phone']}\n"
        f"🏢 {data['company']}\n"
        f"💳 {tariff}\n"
        f"🔖 Код заявки: {code}"
    )
    await bot.send_message(chat_id=int(GROUP_ID), text=text)

    # Подтверждение пользователю
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=MESSAGES[lang]['thank_you'].format(code=code),
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.finish()
    await callback.answer()

# Команда /status
@dp.message_handler(commands=['status'], state='*')
async def process_status(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("Использование: /status <код заявки>")
    code = parts[1].strip().upper()
    records = worksheet.get_all_records()
    for r in records:
        if str(r.get('Code', '')).upper() == code:
            return await message.reply(
                "Ваша заявка принята и в обработке."
            )
    await message.reply(f"Заявка с кодом {code} не найдена.")

# Endpoint для вебхука
@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    update = types.Update(**payload)
    await dp.process_update(update)
    return {"ok": True}

# Запуск локально
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
