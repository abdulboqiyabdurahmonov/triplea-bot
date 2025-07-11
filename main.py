import os
import re
import logging
import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_webhook
from datetime import datetime

# --- Configuration -------------------------------------------
API_TOKEN      = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID  = int(os.getenv('GROUP_CHAT_ID', '0'))
CREDS_FILE     = '/etc/secrets/triplea-bot-250fd4803dd8.json'
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '')
WORKSHEET_NAME = os.getenv('WORKSHEET_NAME', 'Лист1')

# Webhook settings
WEBHOOK_HOST   = os.getenv('WEBHOOK_HOST')                       # e.g. "https://your.domain.com"
WEBHOOK_PATH   = os.getenv('WEBHOOK_PATH', f"/webhook/{API_TOKEN}")
WEBHOOK_URL    = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST    = os.getenv('WEBAPP_HOST', '0.0.0.0')
WEBAPP_PORT    = int(os.getenv('WEBAPP_PORT', 8443))
# -------------------------------------------------------------

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"Config loaded: GROUP_CHAT_ID={GROUP_CHAT_ID}, SPREADSHEET_ID={SPREADSHEET_ID}")

# Initialize bot & dispatcher
bot = Bot(token=API_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Google Sheets authorization
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
gc    = gspread.authorize(creds)

def get_sheet():
    return gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

# Localization texts
TEXT = {
    'ru': {
        'choose_lang':    'Пожалуйста, выберите язык:',
        'invalid_lang':   "Нужно выбрать кнопкой: Русский или O'zbekcha.",
        'ask_name':       'Введите ваше ФИО:',
        'ask_phone':      'Введите номер телефона:',
        'invalid_phone':  'Неверный формат. Введите номер в формате +998XXXXXXXXX.',
        'ask_region':     'Введите ваш регион проживания:',
        'invalid_region': 'Нужно ввести название региона.',
        'ask_email':      'Введите ваш Email или отправьте /skip, чтобы пропустить:',
        'invalid_email':  'Неверный формат email. Попробуйте ещё раз или /skip.',
        'ask_company':    'Введите название компании:',
        'ask_tariff':     'Выберите тариф:',
        'invalid_tariff': 'Нужно выбрать одним из вариантов кнопками.',
        'thank_you':      'Спасибо! Ваша заявка отправлена.',
        'sheet_error':    '⚠️ Заявка отправлена в группу, но не сохранена в таблице.',
        'tariffs':        ['Старт', 'Бизнес', 'Корпоратив'],
        'back':           'Назад'
    },
    'uz': {
        'choose_lang':    "Iltimos, tilni tanlang:",
        'invalid_lang':   "Iltimos, tugmalardan foydalanib tanlang: Ruscha yoki O'zbekcha.",
        'ask_name':       "Iltimos, FIOingizni kiriting:",
        'ask_phone':      "Iltimos, telefon raqamingizni kiriting:",
        'invalid_phone':  "Noto‘g‘ri format. +998XXXXXXXXX.",
        'ask_region':     "Iltimos, yashash hududingizni kiriting:",
        'invalid_region': "Mintaqani kiriting.",
        'ask_email':      "Iltimos, Emailingizni kiriting yoki /skip yuboring:",
        'invalid_email':  "Noto‘g‘ri format. Yana urinib ko‘ring yoki /skip.",
        'ask_company':    "Iltimos, kompaniya nomini kiriting:",
        'ask_tariff':     "Iltimos, tarifni tanlang:",
        'invalid_tariff':'Tugmalardan birini tanlang.',
        'thank_you':      'Rahmat! Arizangiz yuborildi.',
        'sheet_error':    '⚠️ Ariza guruhga yuborildi, lekin jadvalga yozilmadi.',
        'tariffs':        ['Boshlang‘ich', 'Biznes', 'Korporativ'],
        'back':           'Orqaga'
    }
}

# States
class Form(StatesGroup):
    lang            = State()
    name            = State()
    name_confirm    = State()
    phone           = State()
    phone_confirm   = State()
    region          = State()
    region_confirm  = State()
    email           = State()
    email_confirm   = State()
    company         = State()
    company_confirm = State()
    tariff          = State()
    tariff_confirm  = State()

# Keyboards
def build_lang_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add('Русский', "O'zbekcha")
    return kb

def yes_no_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Да", callback_data="yes"),
        InlineKeyboardButton("Нет", callback_data="no")
    )
    return kb

# ————————— Handlers —————————

@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await Form.lang.set()
    await message.answer(TEXT['ru']['choose_lang'], reply_markup=build_lang_kb())

@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt == 'русский':
        lang = 'ru'
    elif txt in ("o'zbekcha", 'узбекский'):
        lang = 'uz'
    else:
        return await message.answer(TEXT['ru']['invalid_lang'])
    await state.update_data(lang=lang)
    await Form.name.set()
    await message.answer(TEXT[lang]['ask_name'], reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    lang = (await state.get_data())['lang']
    await Form.name_confirm.set()
    await message.answer(f"Вы ввели ФИО: {name}\nВерно?", reply_markup=yes_no_kb())

@dp.callback_query_handler(lambda c: c.data in ['yes','no'], state=Form.name_confirm)
async def confirm_name(call: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())['lang']
    await call.answer()
    if call.data == 'yes':
        await Form.phone.set()
        await call.message.edit_text(TEXT[lang]['ask_phone'])
    else:
        await Form.name.set()
        await call.message.edit_text(TEXT[lang]['ask_name'])

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    digits = re.sub(r'\D', '', raw)
    if re.fullmatch(r'\d{9}', digits):
        phone = '+998' + digits
    elif re.fullmatch(r'998\d{9}', digits):
        phone = '+' + digits
    elif re.fullmatch(r'\+998\d{9}', raw):
        phone = raw
    else:
        lang = (await state.get_data())['lang']
        return await message.answer(TEXT[lang]['invalid_phone'])
    await state.update_data(phone=phone)
    lang = (await state.get_data())['lang']
    await Form.phone_confirm.set()
    await message.answer(f"Вы ввели телефон: {phone}\nВерно?", reply_markup=yes_no_kb())

@dp.callback_query_handler(lambda c: c.data in ['yes','no'], state=Form.phone_confirm)
async def confirm_phone(call: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())['lang']
    await call.answer()
    if call.data == 'yes':
        await Form.region.set()
        await call.message.edit_text(TEXT[lang]['ask_region'])
    else:
        await Form.phone.set()
        await call.message.edit_text(TEXT[lang]['ask_phone'])

@dp.message_handler(state=Form.region)
async def process_region(message: types.Message, state: FSMContext):
    reg = message.text.strip()
    if not reg:
        lang = (await state.get_data())['lang']
        return await message.answer(TEXT[lang]['invalid_region'])
    await state.update_data(region=reg)
    lang = (await state.get_data())['lang']
    await Form.region_confirm.set()
    await message.answer(f"Вы ввели регион: {reg}\nВерно?", reply_markup=yes_no_kb())

@dp.callback_query_handler(lambda c: c.data in ['yes','no'], state=Form.region_confirm)
async def confirm_region(call: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())['lang']
    await call.answer()
    if call.data == 'yes':
        await Form.email.set()
        await call.message.edit_text(TEXT[lang]['ask_email'])
    else:
        await Form.region.set()
        await call.message.edit_text(TEXT[lang]['ask_region'])

@dp.message_handler(state=Form.email)
async def process_email(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    lang = (await state.get_data())['lang']
    if raw.lower() == '/skip':
        await state.update_data(email='—')
    else:
        if not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", raw):
            return await message.answer(TEXT[lang]['invalid_email'])
        await state.update_data(email=raw)
    await Form.email_confirm.set()
    val = await state.get_data()
    await message.answer(f"Email: {val['email']}\nВерно?", reply_markup=yes_no_kb())

@dp.callback_query_handler(lambda c: c.data in ['yes','no'], state=Form.email_confirm)
async def confirm_email(call: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())['lang']
    await call.answer()
    if call.data == 'yes':
        await Form.company.set()
        await call.message.edit_text(TEXT[lang]['ask_company'])
    else:
        await Form.email.set()
        await call.message.edit_text(TEXT[lang]['ask_email'])

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    comp = message.text.strip()
    await state.update_data(company=comp)
    lang = (await state.get_data())['lang']
    await Form.company_confirm.set()
    await message.answer(f"Вы ввели компанию: {comp}\nВерно?", reply_markup=yes_no_kb())

@dp.callback_query_handler(lambda c: c.data in ['yes','no'], state=Form.company_confirm)
async def confirm_company(call: CallbackQuery, state: FSMContext):
    lang = (await state.get_data())['lang']
    await call.answer()
    if call.data == 'yes':
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(TEXT[lang]['back'], *TEXT[lang]['tariffs'])
        await Form.tariff.set()
        await call.message.edit_text(TEXT[lang]['ask_tariff'], reply_markup=kb)
    else:
        await Form.company.set()
        await call.message.edit_text(TEXT[lang]['ask_company'])

@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    if message.text not in TEXT[lang]['tariffs']:
        return await message.answer(TEXT[lang]['invalid_tariff'])
    await state.update_data(tariff=message.text)
    await Form.tariff_confirm.set()
    await message.answer(f"Вы выбрали тариф: {message.text}\nВерно?", reply_markup=yes_no_kb())

@dp.callback_query_handler(lambda c: c.data in ['yes','no'], state=Form.tariff_confirm)
async def confirm_tariff(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    await call.answer()
    if call.data == 'yes':
        # 1) Telegram
        summary = (
            f"📥 Новая заявка!\n"
            f"👤 ФИО: {data['name']}\n"
            f"📞 Тел: {data['phone']}\n"
            f"📧 Email: {data['email']}\n"
            f"🌍 Регион: {data['region']}\n"
            f"🏢 Компания: {data['company']}\n"
            f"💼 Тариф: {data['tariff']}"
        )
        try:
            await bot.send_message(GROUP_CHAT_ID, summary)
        except Exception as e:
            logging.error(f"Error sending to group: {e}")
            await call.message.answer(TEXT[lang]['sheet_error'])

        # 2) Google Sheets (A–G)
        try:
            sheet = get_sheet()
            sheet.append_row([
                datetime.utcnow().isoformat(),  # A
                data['name'],                   # B
                data['phone'],                  # C
                data['email'],                  # D
                data['region'],                 # E
                data['company'],                # F
                data['tariff']                  # G
            ], value_input_option='USER_ENTERED')
        except Exception as e:
            logging.error(f"Error writing to sheet: {e}")
            await call.message.answer(TEXT[lang]['sheet_error'])

        # Финал
        await call.message.edit_text(TEXT[lang]['thank_you'], reply_markup=types.ReplyKeyboardRemove())
        await state.finish()
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(TEXT[lang]['back'], *TEXT[lang]['tariffs'])
        await Form.tariff.set()
        await call.message.edit_text(TEXT[lang]['ask_tariff'], reply_markup=kb)

# ————— Fallback для confirm-стадий —————
@dp.message_handler(lambda m: True, state=[
    Form.name_confirm, Form.phone_confirm,
    Form.region_confirm, Form.email_confirm,
    Form.company_confirm, Form.tariff_confirm
])
async def fallback_confirm(message: types.Message):
    await message.reply("Пожалуйста, нажмите «Да» или «Нет».", reply_markup=yes_no_kb())

# Cancel
@dp.message_handler(lambda m: m.text.lower() == 'отмена', state='*')
async def cancel_all(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer('Отменено. /start для начала.', reply_markup=types.ReplyKeyboardRemove())

# Fallback (no state)
@dp.message_handler(state=None)
async def fallback(message: types.Message):
    await message.answer('Я вас не понял. /start для начала.')

# ————— Webhook startup/shutdown —————
async def on_startup(dispatcher):
    # Удаляем старый webhook
    await bot.delete_webhook(drop_pending_updates=True)
    # Устанавливаем новый
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"🚀 Webhook set to {WEBHOOK_URL}")

async def on_shutdown(dispatcher):
    logging.info("🌙 Shutting down, deleting webhook")
    await bot.delete_webhook()
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()

if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
