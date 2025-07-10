import os
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_polling
from datetime import datetime

# --- Configuration -------------------------------------------
API_TOKEN      = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID  = int(os.getenv('GROUP_CHAT_ID', '0'))
CREDS_FILE     = '/etc/secrets/triplea-bot-250fd4803dd8.json'
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '')
WORKSHEET_NAME = os.getenv('WORKSHEET_NAME', 'Лист1')
# -------------------------------------------------------------

# Setup logging
global_log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=global_log_format)
logging.info(f"Config loaded: GROUP_CHAT_ID={GROUP_CHAT_ID}, SPREADSHEET_ID={SPREADSHEET_ID}")

# Google Sheets authorization
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
gc    = gspread.authorize(creds)

def get_sheet():
    return gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Localization texts
TEXT = {
    'ru': {
        'choose_lang':  'Пожалуйста, выберите язык:',
        'invalid_lang': 'Нужно выбрать кнопкой: Русский или Узбекский.',
        'ask_name':     'Введите ваше ФИО:',
        'ask_phone':    'Введите номер телефона:',
        'ask_company':  'Введите название компании:',
        'ask_tariff':   'Выберите тариф:',
        'invalid_tariff':'Нужно выбрать одним из вариантов кнопками.',
        'thank_you':    'Спасибо! Ваша заявка отправлена.',
        'sheet_error':  '⚠️ Заявка отправлена в группу, но не сохранена в таблице.',
        'tariffs':      ['Старт', 'Бизнес', 'Корпоратив'],
        'back':         'Назад'
    },
    'uz': {
        'choose_lang':  "Iltimos, tilni tanlang:",
        'invalid_lang': "Iltimos, tugmalardan foydalanib tanlang: Ruscha yoki O'zbekcha.",
        'ask_name':     "Iltimos, FIOingizni kiriting:",
        'ask_phone':    "Iltimos, telefon raqamingizni kiriting:",
        'ask_company':  "Iltimos, kompaniya nomini kiriting:",
        'ask_tariff':   "Iltimos, tarifni tanlang:",
        'invalid_tariff':'Iltimos, variantlardan birini tanlang.',
        'thank_you':    'Rahmat! Arizangiz yuborildi.',
        'sheet_error':  '⚠️ Ariza guruhga yuborildi, lekin jadvalга yozilmadi.',
        'tariffs':      ['Boshlang‘ich', 'Biznes', 'Korporativ'],
        'back':         'Orqaga'
    }
}

# States
class Form(StatesGroup):
    lang    = State()
    name    = State()
    phone   = State()
    company = State()
    tariff  = State()

# Helper to build language keyboard
def build_lang_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add('Русский', "O'zbekcha")
    return kb

# /start handler
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await Form.lang.set()
    await message.answer(TEXT['ru']['choose_lang'], reply_markup=build_lang_kb())

# Language selection
@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    text = message.text.lower()
    if text == 'русский': lang = 'ru'
    elif text in ("o'zbekcha", 'узбекский'): lang = 'uz'
    else: return await message.answer(TEXT['ru']['invalid_lang'])
    await state.update_data(lang=lang)
    await Form.name.set()
    await message.answer(TEXT[lang]['ask_name'], reply_markup=types.ReplyKeyboardRemove())

# Name handler
@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    await Form.phone.set()
    await message.answer(TEXT[data['lang']]['ask_phone'])

# Phone handler
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    data = await state.get_data()
    await Form.company.set()
    await message.answer(TEXT[data['lang']]['ask_company'])

# Company handler
@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text.strip())
    data = await state.get_data()
    lang = data['lang']
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(TEXT[lang]['back'])
    for t in TEXT[lang]['tariffs']:
        kb.add(t)
    await Form.tariff.set()
    await message.answer(TEXT[lang]['ask_tariff'], reply_markup=kb)

# Tariff handler
@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    data = await state.get_data(); lang = data['lang']; tariffs = TEXT[lang]['tariffs']
    if message.text not in tariffs:
        return await message.answer(TEXT[lang]['invalid_tariff'])
    await state.update_data(tariff=message.text)
    data = await state.get_data()
    summary = (
        f"📥 Новая заявка!\n"
        f"👤 ФИО: {data.get('name','')}\n"
        f"📞 Тел: {data.get('phone','')}\n"
        f"🏢 Компания: {data.get('company','')}\n"
        f"💼 Тариф: {data.get('tariff','')}"
    )
    logging.info(f"Sending to GROUP_CHAT_ID={GROUP_CHAT_ID}: {summary}")
    try:
        sent = await bot.send_message(GROUP_CHAT_ID, summary)
        logging.info(f"Sent message_id={sent.message_id}")
    except Exception as e:
        logging.error(f"Error sending to group: {e}")
        await message.answer(TEXT[lang]['sheet_error'])
    try:
        sheet = get_sheet()
        sheet.append_row([
            datetime.utcnow().isoformat(), data.get('name',''), data.get('phone',''),
            data.get('company',''), data.get('tariff','')
        ], value_input_option='USER_ENTERED')
        logging.info("Append to sheet succeeded")
    except Exception as e:
        logging.error(f"Error writing to sheet: {e}")
        await message.answer(TEXT[lang]['sheet_error'])
    await message.answer(TEXT[lang]['thank_you'], reply_markup=types.ReplyKeyboardRemove())
    await state.finish()

# Back handler
@dp.message_handler(lambda m: m.text in (TEXT['ru']['back'], TEXT['uz']['back']), state=Form.tariff)
async def back_to_company(message: types.Message, state: FSMContext):
    data = await state.get_data(); lang = data['lang']
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(TEXT[lang]['back'])
    for t in TEXT[lang]['tariffs']:
        kb.add(t)
    await Form.company.set()
    await message.answer(TEXT[lang]['ask_company'], reply_markup=kb)

# Debug Sheets command
@dp.message_handler(commands=['debug_sheet'], state='*')
async def cmd_debug_sheet(message: types.Message):
    try:
        ss = gc.open_by_key(SPREADSHEET_ID)
        names = [ws.title for ws in ss.worksheets()]
        await message.answer(f"Worksheets: {names}")
    except Exception as e:
        await message.answer(f"Error accessing sheet: {e}")
        logging.error(f"DEBUG_SHEET_ERROR: {e}")

# Test Sheets command
@dp.message_handler(commands=['test_sheet'], state='*')
async def cmd_test_sheet(message: types.Message):
    try:
        sheet = get_sheet()
        row = [
            datetime.utcnow().isoformat(),
            '✅ TEST',
            message.from_user.full_name,
            message.from_user.id,
            'Acme Inc.',
            'Старт'
        ]
        sheet.append_row(row, value_input_option='USER_ENTERED')
        await message.answer('✅ Тестовая строка добавлена в Google Sheets!')
    except Exception as e:
        await message.answer(f'❌ Не удалось записать строку: {e}')
        logging.error(f'TEST_SHEET_ERROR: {e}')

# Cancel handler
@dp.message_handler(lambda m: m.text.lower() == 'отмена', state='*')
async def cancel_all(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer('Отменено. /start для начала.', reply_markup=types.ReplyKeyboardRemove())

import datetime

@dp.message_handler(commands=['debug_sheet'], state='*')
async def debug_sheet(message: types.Message, state: FSMContext):
    # сбросим FSM, чтобы не мешалось
    await state.finish()
    try:
        sheet = get_sheet()
        # вставляем тестовую строку с отметкой времени
        sheet.append_row([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "DEBUG",
            "TEST ROW"
        ])
        await message.answer("✅ Успех! Тестовая строка добавлена в таблицу.")
    except Exception as e:
        await message.answer(f"❌ Ошибка доступа к таблице: {e}")

# Fallback handler (last)
@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer('Я вас не понял. /start для начала.')

# Run bot
if __name__ == '__main__':
    start_polling(dp, skip_updates=True)

@dp.message_handler(commands=['debug_sheet'], state='*')
async def debug_sheet(message: types.Message):
    try:
        sheet = get_sheet()
        sheet.append_row(['🐞 debug', str(datetime.datetime.now())])
        await message.reply("✅ Sheet append OK")
    except Exception as e:
        await message.reply(f"❌ Sheet append FAILED:\n{e}")
        
@dp.message_handler(commands=['cancel'], state='*')
async def cancel_cmd(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Отменено. /start чтобы начать заново.", reply_markup=types.ReplyKeyboardRemove())

# прямо под всеми import-ами и авторизацией Google Sheets
from aiogram.dispatcher import filters

@dp.message_handler(commands=['cancel'], state='*')
@dp.message_handler(lambda m: m.text == "Отмена", state='*')
async def cancel_all(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "Отменено. /start — чтобы начать заново.",
        reply_markup=types.ReplyKeyboardRemove()
    )


