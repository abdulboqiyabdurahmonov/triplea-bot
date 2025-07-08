from fastapi.middleware.trustedhost import TrustedHostMiddleware

# Чтобы видеть полные стектрейсы в логах
uvicorn_logger = logging.getLogger("uvicorn.error")
uvicorn_logger.setLevel(logging.DEBUG)

import os
import logging
import json
import re
import uuid
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI, Request
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

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

# Проверка обязательных env-vars
required = [BOT_TOKEN, GROUP_ID, WEBHOOK_URL, GOOGLE_CREDS_JSON, GOOGLE_SHEET_ID, GOOGLE_WORKSHEET_NAME]
if not all(required):
    logging.error("Не заданы обязательные переменные окружения")
    exit(1)

# Инициализация Google Sheets
creds_info  = json.loads(GOOGLE_CREDS_JSON)
credentials = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc          = gspread.Client(auth=credentials)
worksheet   = gc.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_WORKSHEET_NAME)

# Инициализация бота и диспетчера
bot     = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp      = Dispatcher(bot, storage=storage)
app     = FastAPI()

# FSM-состояния
class Form(StatesGroup):
    lang    = State()
    fio     = State()
    phone   = State()
    company = State()
    tariff  = State()

# Сообщения на разных языках
MESSAGES = {
    'ru': {
        'select_lang': 'Выберите язык:',
        'ask_fio': 'Пожалуйста, введите ваше ФИО:',
        'invalid_fio': 'Некорректное ФИО. Только буквы и пробелы:',
        'ask_phone': 'Введите номер телефона (+71234567890):',
        'invalid_phone': 'Неверный формат. +71234567890:',
        'ask_company': 'Введите название компании:',
        'ask_tariff': 'Выберите тариф:',
        'thank_you': 'Ваша заявка принята! Код: {code}. Скоро свяжемся.',
        'cancelled': 'Операция отменена.'
    },
    'uz': {
        'select_lang': 'Tilni tanlang:',
        'ask_fio': "Iltimos, to'liq ismingizni kiriting:",
        'invalid_fio': "Ism noto'g'ri. Faqat harflar va bo'sh joylar:",
        'ask_phone': "Telefon raqamingizni kiriting (+998901234567):",
        'invalid_phone': "Format noto'g'ri. +998901234567:",
        'ask_company': 'Kompaniya nomi:',
        'ask_tariff': 'Tarifni tanlang:',
        'thank_you': "Arizangiz qabul qilindi! Kodi: {code}. Tez orada bog'lanamiz.",
        'cancelled': "Amal bekor qilindi."
    }
}

# /start — выбор языка
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton('Русский 🇷🇺', callback_data='lang_ru'),
        InlineKeyboardButton("O'zbekcha 🇺🇿", callback_data='lang_uz'),
    )
    await state.finish()
    await bot.send_message(
        chat_id=message.chat.id,
        text=MESSAGES['ru']['select_lang'],
        reply_markup=kb
    )
    await Form.lang.set()

# Обработка выбора языка
@dp.callback_query_handler(lambda c: c.data in ['lang_ru','lang_uz'], state=Form.lang)
async def process_lang(callback: types.CallbackQuery, state: FSMContext):
    # убираем inline-кнопки
    await callback.message.edit_reply_markup(None)

    lang = 'ru' if callback.data == 'lang_ru' else 'uz'
    await state.update_data(lang=lang, start_ts=datetime.utcnow().isoformat())
    # сразу спрашиваем ФИО
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=MESSAGES[lang]['ask_fio'],
        reply_markup=ReplyKeyboardRemove()
    )
    await Form.fio.set()
    await callback.answer()

# /cancel
@dp.message_handler(commands=['cancel'], state='*')
async def cmd_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang','ru')
    await state.finish()
    await message.answer(MESSAGES[lang]['cancelled'])

# ФИО
@dp.message_handler(state=Form.fio)
async def process_fio(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang','ru')
    if not re.match(r'^[A-Za-zА-Яа-яЁё ]+$', message.text):
        return await message.answer(MESSAGES[lang]['invalid_fio'])
    await state.update_data(fio=message.text)
    await Form.phone.set()
    await message.answer(MESSAGES[lang]['ask_phone'])

# Телефон
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang','ru')
    if not re.match(r'^\+?\d{7,15}$', message.text):
        return await message.answer(MESSAGES[lang]['invalid_phone'])
    await state.update_data(phone=message.text)
    await Form.company.set()
    await message.answer(MESSAGES[lang]['ask_company'])

# Компания
@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang','ru')
    await state.update_data(company=message.text)
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton('Старт', callback_data='tariff_Старт'),
        InlineKeyboardButton('Бизнес', callback_data='tariff_Бизнес'),
        InlineKeyboardButton('Корпоратив', callback_data='tariff_Корпоратив')
    )
    await Form.tariff.set()
    await message.answer(MESSAGES[lang]['ask_tariff'], reply_markup=kb)

# Тариф и завершение
@dp.callback_query_handler(lambda c: c.data.startswith('tariff_'), state=Form.tariff)
async def process_tariff(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang','ru')
    tariff = callback.data.split('_',1)[1]
    code = uuid.uuid4().hex[:8].upper()
    start_ts = data['start_ts']
    # Статистика времени
    duration = (datetime.utcnow() - datetime.fromisoformat(start_ts)).total_seconds()
    # Запись
    row = [data['fio'], data['phone'], data['company'], tariff, start_ts, datetime.utcnow().isoformat(), duration, code]
    try:
        worksheet.append_row(row)
    except:
        logging.exception("Ошибка записи в Google Sheets")
    # В группу
    await bot.send_message(int(GROUP_ID), (
        f"📥 Заявка:\n👤 {data['fio']}\n📞 {data['phone']}\n🏢 {data['company']}\n💳 {tariff}\n🔖 {code}"
    ))
    # Ответ пользователю
    await bot.send_message(callback.message.chat.id,
        MESSAGES[lang]['thank_you'].format(code=code), reply_markup=ReplyKeyboardRemove()
    )
    await state.finish()
    await callback.answer()

# /status
@dp.message_handler(commands=['status'], state='*')
async def cmd_status(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts)<2:
        return await message.answer("Использование: /status <код>")
    code = parts[1].strip().upper()
    for r in worksheet.get_all_records():
        if str(r.get('Code','')).upper()==code:
            return await message.answer("Ваша заявка принята и в работе.")
    await message.answer(f"Код {code} не найден.")

# Webhook endpoint
@app.post('/webhook')
async def webhook(request: Request):
    payload = await request.json()
    update = types.Update(**payload)
    await dp.process_update(update)
    return {'ok':True}

# Run
if __name__=='__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=PORT)
