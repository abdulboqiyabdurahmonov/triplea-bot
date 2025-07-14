import os
import json
import logging
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.executor import start_webhook

# --- Configuration -------------------------------------------
API_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', '0'))
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
WORKSHEET_NAME = os.getenv('WORKSHEET_NAME', 'Лист1')

WEBHOOK_HOST = os.getenv('WEBHOOK_HOST')      # e.g. "https://your.domain.com"
WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.getenv('PORT', 8000))

# --- Bot & Dispatcher ----------------------------------------
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- Google Sheets setup -------------------------------------
# Use JSON credentials from environment to avoid missing file
SERVICE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
if SERVICE_CREDENTIALS_JSON:
    creds_dict = json.loads(SERVICE_CREDENTIALS_JSON)
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ])
else:
    SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
    credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ])
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

# --- FSM States ----------------------------------------------
class Form(StatesGroup):
    lang = State()
    name = State()
    phone = State()
    company = State()
    tariff = State()

# --- Handlers -------------------------------------------------
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Русский", callback_data="lang_ru"),
        InlineKeyboardButton("English", callback_data="lang_en")
    )
    await message.answer("Пожалуйста, выберите язык / Please choose language:", reply_markup=keyboard)
    await Form.lang.set()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('lang_'), state=Form.lang)
async def process_lang(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = callback.data.split('_')[1]
    await state.update_data(lang=lang)
    await bot.send_message(callback.from_user.id, f"Вы выбрали язык: {lang}")
    await bot.send_message(callback.from_user.id, "Введите ваше ФИО:")
    await Form.name.set()

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите ваш номер телефона:")
    await Form.phone.set()

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введите название вашей компании:")
    await Form.company.set()

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Старт", callback_data="tariff_start"),
        InlineKeyboardButton("Бизнес", callback_data="tariff_business"),
        InlineKeyboardButton("Корпоративный", callback_data="tariff_corp")
    )
    await message.answer("Выберите тариф:", reply_markup=keyboard)
    await Form.tariff.set()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('tariff_'), state=Form.tariff)
async def process_tariff(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    tariff = callback.data.split('_', 1)[1]
    data = await state.get_data()
    name = data.get('name')
    phone = data.get('phone')
    company = data.get('company')
    lang = data.get('lang')

    # Send to Telegram group
    text = (
        f"📥 Новый запрос из бота ({lang})\n"
        f"👤 ФИО: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"🏢 Компания: {company}\n"
        f"💼 Тариф: {tariff}"
    )
    await bot.send_message(GROUP_CHAT_ID, text)

    # Write to Google Sheets
    try:
        sheet.append_row([name, phone, company, tariff, datetime.utcnow().isoformat()])
    except Exception as e:
        logging.error(f"Ошибка при записи в Google Sheets: {e}")

    await bot.send_message(callback.from_user.id, "Спасибо! Ваша заявка отправлена.")
    await state.finish()

# --- Webhook setup -------------------------------------------
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
