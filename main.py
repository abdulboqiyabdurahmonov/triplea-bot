import os
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_webhook, start_polling
from datetime import datetime

# ——— Параметры —————————————————————————————————————————————
API_TOKEN      = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID  = int(os.getenv('GROUP_CHAT_ID', '0'))
CREDS_FILE     = '/etc/secrets/triplea-bot-250fd4803dd8.json'
SPREADSHEET_ID = '1AbCdEfGhIJkLmNoPqRsTuVwXyZ1234567890'
WORKSHEET_NAME = 'Лист1'

# Для Webhook (если не задан — polling):
WEBHOOK_HOST   = os.getenv('WEBHOOK_HOST', '')
WEBHOOK_PATH   = f'/webhook/{API_TOKEN}'
WEBHOOK_URL    = WEBHOOK_HOST + WEBHOOK_PATH
WEBAPP_HOST    = '0.0.0.0'
WEBAPP_PORT    = int(os.getenv('PORT', '8000'))
# ————————————————————————————————————————————————————————————

logging.basicConfig(level=logging.INFO)

# — Google Sheets ———————————————————————————————————————
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
gc    = gspread.authorize(creds)

def get_sheet():
    return gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
# ————————————————————————————————————————————————————————————

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

# — Локализация ————————————————————————————————————————
prompts = {
    'Русский': {
        'invalid_lang':   'Нужно выбрать кнопкой: Русский или Узбекский.',
        'ask_name':       'Введите ваше ФИО:',
        'ask_phone':      'Введите номер телефона:',
        'ask_company':    'Введите название компании:',
        'ask_tariff':     'Выберите тариф:',
        'invalid_tariff': 'Нужно выбрать один из тарифов кнопками.',
        'thank_you':      'Спасибо! Ваша заявка отправлена.',
        'sheet_error':    '⚠️ Не удалось сохранить заявку в таблицу, но в группу она отправлена.',
        'fallback':       'Чтобы начать, введите команду /start',
        'back':           'Назад',
        'tariffs':        ['Старт', 'Бизнес', 'Корпоратив']
    },
    'Узбекский': {
        'invalid_lang':   "Iltimos, tugmalardan foydalanib tanlang: Ruscha yoki O'zbekcha.",
        'ask_name':       'Iltimos, ismingiz va familiyangizni kiriting:',
        'ask_phone':      'Iltimos, telefon raqamingizni kiriting:',
        'ask_company':    'Iltimos, kompaniya nomini kiriting:',
        'ask_tariff':     'Iltimos, quydan tarifni tanlang:',
        'invalid_tariff': 'Iltimos, quydagi tariflardan birini tanlang.',
        'thank_you':      'Rahмат! Murojaatingiz yuborildi.',
        'sheet_error':    '⚠️ Arizani jadvalga saqlashda muammo yuz berdi, lekin guruhga yuborildi.',
        'fallback':       "/start buyrug'ini kiriting, iltimos.",
        'back':           'Orqaga',
        'tariffs':        ['Boshlang‘ich', 'Biznes', 'Korporativ']
    }
}
# ————————————————————————————————————————————————————————————

class Form(StatesGroup):
    lang    = State()
    name    = State()
    phone   = State()
    company = State()
    tariff  = State()

@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add('Русский', 'Узбекский')
    await Form.lang.set()
    await message.answer('Пожалуйста, выберите язык:', reply_markup=kb)

@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    if message.text not in prompts:
        return await message.answer(prompts['Русский']['invalid_lang'])
    await state.update_data(lang=message.text)
    await Form.name.set()
    await message.answer(prompts[message.text]['ask_name'], reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(name=message.text.strip())
    await Form.phone.set()
    await message.answer(prompts[data['lang']]['ask_phone'])

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(phone=message.text.strip())
    await Form.company.set()
    await message.answer(prompts[data['lang']]['ask_company'])

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p = prompts[data['lang']]
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(p['back'])
    for t in p['tariffs']:
        kb.add(t)
    await Form.tariff.set()
    await message.answer(p['ask_tariff'], reply_markup=kb)

@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p = prompts[data['lang']]
    valid = prompts['Русский']['tariffs'] + prompts['Узбекский']['tariffs']
    if message.text not in valid:
        return await message.answer(p['invalid_tariff'])
    await state.update_data(tariff=message.text)
    data = await state.get_data()

    summary = (
        f"📥 Новая заявка!\n\n"
        f"🌐 Язык: {data['lang']}\n"
        f"👤 ФИО: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"💼 Тариф: {data['tariff']}"
    )
    await bot.send_message(GROUP_CHAT_ID, summary)

    # Debug: попытка записи простого сообщения
    try:
        sheet = get_sheet()
        sheet.append_row([
            datetime.utcnow().isoformat(),
            data['lang'], data['name'], data['phone'], data['company'], data['tariff']
        ], value_input_option='USER_ENTERED')
        logging.info('Запись в таблицу прошла успешно')
    except Exception as e:
        logging.error(f"Ошибка при записи в Google Sheets: {e}")
        # посылаем диагностику пользователю
        await bot.send_message(message.chat.id, f"Ошибка записи в таблицу: {e}")

    await message.answer(p['thank_you'], reply_markup=types.ReplyKeyboardRemove())
    await state.finish()

# Команда для проверки доступа к таблице и листам
@dp.message_handler(commands=['debug_sheet'])
async def debug_sheet(message: types.Message):
    try:
        ss = gc.open_by_key(SPREADSHEET_ID)
        names = [ws.title for ws in ss.worksheets()]
        await message.answer(f"Worksheets: {names}")
    except Exception as e:
        await message.answer(f"Error accessing sheet: {e}")

# «Назад» обработчики
for st in ('tariff','company','phone','name'):
    @dp.message_handler(lambda m, st=st: m.text == prompts['Русский']['back'] or m.text == prompts['Узбекский']['back'], state=getattr(Form, st))
    async def go_back(message: types.Message, state: FSMContext, st=st):
        prev = {
            'tariff': Form.company,
            'company': Form.phone,
            'phone': Form.name,
            'name': Form.lang
        }[st]
        await prev.set()
        data = await state.get_data()
        lang = data.get('lang', 'Русский')
        await message.answer(prompts[lang][f'ask_{prev.name}'], reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(lambda m: m.text.lower() == 'отмена', state='*')
async def cancel_all(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer('Отменено. /start чтобы начать заново.', reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=None, content_types=types.ContentTypes.TEXT)
async def fallback(message: types.Message):
    await message.answer(prompts['Русский']['fallback'])

# Webhook vs Polling старт
async def on_startup(dp):
    if WEBHOOK_HOST:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook установлен: {WEBHOOK_URL}")
    else:
        logging.info("WEBHOOK_HOST не задан, запускаем polling")

async def on_shutdown(dp):
    logging.warning("Shutting down..")
    if WEBHOOK_HOST:
        await bot.delete_webhook()
        logging.warning("Webhook удалён")

if __name__ == '__main__':
    if WEBHOOK_HOST:
        start_webhook(
            dispatcher=dp,
            webhook_path=WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host=WEBAPP_HOST,
            port=WEBAPP_PORT,
        )
    else:
        start_polling(dp, skip_updates=True, on_startup=on_startup)
