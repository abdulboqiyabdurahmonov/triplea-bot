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

# ——— Config —————————————————————————————————————————————
API_TOKEN      = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID  = int(os.getenv('GROUP_CHAT_ID', '0'))
CREDS_FILE     = '/etc/secrets/triplea-bot-250fd4803dd8.json'
SPREADSHEET_ID = '1AbCdEfGhIJkLmNoPqRsTuVwXyZ1234567890'
WORKSHEET_NAME = 'Лист1'
# ————————————————————————————————————————————————————————————

logging.basicConfig(level=logging.INFO)

# Google Sheets setup
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
gc    = gspread.authorize(creds)

def get_sheet():
    return gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
# ————————————————————————————————————————————————————————————

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Localization
TEXT = {
    'ru': {
        'choose_lang':       'Пожалуйста, выберите язык:',
        'invalid_lang':      'Нужно выбрать кнопкой: Русский или Узбекский.',
        'ask_name':          'Введите ваше ФИО:',
        'ask_phone':         'Введите номер телефона:',
        'ask_company':       'Введите название компании:',
        'ask_tariff':        'Выберите тариф:',
        'invalid_tariff':    'Нужно выбрать одним из вариантов кнопками.',
        'thank_you':         'Спасибо! Ваша заявка отправлена.',
        'sheet_error':       '⚠️ Заявка отправлена в группу, но не сохранена в таблице.',
        'tariffs':           ['Старт', 'Бизнес', 'Корпоратив'],
        'back':              'Назад'
    },
    'uz': {
        'choose_lang':       "Iltimos, tilni tanlang:",
        'invalid_lang':      "Iltimos, tugmalardan foydalanib tanlang: Ruscha yoki O'zbekcha.",
        'ask_name':          "Iltimos, FIOingizni kiriting:",
        'ask_phone':         "Iltimos, telefon raqamingizni kiriting:",
        'ask_company':       "Iltimos, kompaniya nomini kiriting:",
        'ask_tariff':        "Iltimos, tarifni tanlang:",
        'invalid_tariff':    "Iltimos, variantlardan birini tanlang.",
        'thank_you':         "Rahmat! Arizangiz yuborildi.",
        'sheet_error':       "⚠️ Ariza guruhga yuborildi, lekin jadvalga yozilmadi.",
        'tariffs':           ['Boshlang‘ich', 'Biznes', 'Korporativ'],
        'back':              'Orqaga'
    }
}

class Form(StatesGroup):
    lang    = State()
    name    = State()
    phone   = State()
    company = State()
    tariff  = State()

# /start
@dp.message_handler(commands='start', state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add('Русский', "O'zbekcha")
    await Form.lang.set()
    await message.answer(TEXT['ru']['choose_lang'], reply_markup=kb)

# Language
@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    text = message.text.lower()
    if text == 'русский':
        lang = 'ru'
    elif text in ("o'zbekcha", 'узбекский'):
        lang = 'uz'
    else:
        return await message.answer(TEXT['ru']['invalid_lang'])
    await state.update_data(lang=lang)
    await Form.name.set()
    await message.answer(TEXT[lang]['ask_name'], reply_markup=types.ReplyKeyboardRemove())

# Name
@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    await Form.phone.set()
    await message.answer(TEXT[data['lang']]['ask_phone'])

# Phone
@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    data = await state.get_data()
    await Form.company.set()
    await message.answer(TEXT[data['lang']]['ask_company'])

# Company
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

# Tariff
@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    tariffs = TEXT[lang]['tariffs']
    if message.text not in tariffs:
        return await message.answer(TEXT[lang]['invalid_tariff'])
    await state.update_data(tariff=message.text)
    data = await state.get_data()

    # Send to group
    text = (
        f"📥 Новая заявка!\n"
        f"👤 ФИО: {data['name']}\n"
        f"📞 Тел: {data['phone']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"💼 Тариф: {data['tariff']}"
    )
    await bot.send_message(GROUP_CHAT_ID, text)

    # Send to sheet
    try:
        sheet = get_sheet()
        sheet.append_row([
            datetime.utcnow().isoformat(),
            data['name'], data['phone'], data['company'], data['tariff']
        ], value_input_option='USER_ENTERED')
    except Exception as e:
        logging.error(f"Sheet write error: {e}")
        await bot.send_message(message.chat.id, TEXT[lang]['sheet_error'])

    await message.answer(TEXT[lang]['thank_you'], reply_markup=types.ReplyKeyboardRemove())
    await state.finish()

# Back handlers
@dp.message_handler(lambda m: m.text in (TEXT['ru']['back'], TEXT['uz']['back']), state=Form.tariff)
async def back_to_company(message: types.Message, state: FSMContext):
    data = await state.get_data()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    lang = data['lang']
    kb.add(TEXT[lang]['back'])
    for t in TEXT[lang]['tariffs']:
        kb.add(t)
    await Form.company.set()
    await message.answer(TEXT[lang]['ask_company'], reply_markup=kb)

# Cancel
@dp.message_handler(lambda m: m.text.lower() == 'отмена', state='*')
async def cancel_all(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer('Отменено. /start для начала.', reply_markup=types.ReplyKeyboardRemove())

# Fallback
@dp.message_handler(state=None)
async def fallback(message: types.Message):
    await message.answer('Я вас не понял. /start для начала.')

if __name__ == '__main__':
    start_polling(dp, skip_updates=True)
```
