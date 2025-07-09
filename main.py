# main.py

import os
import logging
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.utils.exceptions import TerminatedByOtherGetUpdates

# ——— Параметры ———
API_TOKEN       = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID   = int(os.getenv('GROUP_CHAT_ID'))
CREDS_FILE      = '/etc/secrets/triplea-bot-250fd4803dd8.json'
SPREADSHEET_ID  = '1AbCdEfGhIJkLmNoPqRsTuVwXyZ1234567890'
WORKSHEET_NAME  = 'Лист1'
# —————————————————

logging.basicConfig(level=logging.INFO)

# Авторизация в Google Sheets
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
gc    = gspread.authorize(creds)

def get_sheet():
    return gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Тексты для каждой локали
prompts = {
    'Русский': {
        'invalid_lang':    "Нужно выбрать кнопкой: Русский или Узбекский.",
        'ask_name':        "Введите ваше ФИО:",
        'ask_phone':       "Введите номер телефона:",
        'ask_company':     "Введите название компании:",
        'ask_tariff':      "Выберите тариф:",
        'invalid_tariff':  "Нужно выбрать один из трёх тарифов кнопками.",
        'thank_you':       "Спасибо! Ваша заявка отправлена.",
        'sheet_error':     "⚠️ Не удалось сохранить заявку в таблицу, но в группу она отправлена.",
        'fallback':        "Чтобы начать, введите команду /start"
    },
    'Узбекский': {
        'invalid_lang':    "Iltimos, tugmalardan foydalanib tanlang: Ruscha yoki O'zbekcha.",
        'ask_name':        "Iltimos, ismingiz va familiyangizni kiriting:",
        'ask_phone':       "Iltimos, telefon raqamingizni kiriting:",
        'ask_company':     "Iltimos, kompaniya nomini kiriting:",
        'ask_tariff':      "Iltimos, tarifni tanlang:",
        'invalid_tariff':  "Iltimos, quydagi tariflardan birini tanlang tugmalar orqali.",
        'thank_you':       "Rahmat! Murojaatingiz yuborildi.",
        'sheet_error':     "⚠️ Arizani jadvalga saqlashda muammo yuz berdi, lekin guruhga yuborildi.",
        'fallback':        "/start buyrug'ini kiriting, iltimos."
    }
}

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
    kb.add("Русский", "Узбекский")
    await Form.lang.set()
    await message.answer("Пожалуйста, выберите язык:", reply_markup=kb)

@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    choice = message.text
    if choice not in prompts:
        return await message.answer(prompts['Русский']['invalid_lang'])
    await state.update_data(lang=choice)
    await Form.name.set()
    await message.answer(prompts[choice]['ask_name'], reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    await state.update_data(name=message.text.strip())
    await Form.phone.set()
    await message.answer(prompts[lang]['ask_phone'])

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    await state.update_data(phone=message.text.strip())
    await Form.company.set()
    await message.answer(prompts[lang]['ask_company'])

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    await state.update_data(company=message.text.strip())
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    # Используем одни и те же названия тарифов
    kb.add("Старт", "Бизнес", "Корпоратив")
    await Form.tariff.set()
    await message.answer(prompts[lang]['ask_tariff'], reply_markup=kb)

@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data['lang']
    valid = ["Старт", "Бизнес", "Корпоратив"]
    if message.text not in valid:
        return await message.answer(prompts[lang]['invalid_tariff'])
    await state.update_data(tariff=message.text)

    # Собираем текст заявки
    data = await state.get_data()
    text = (
        f"📥 Новая заявка!\n\n"
        f"🌐 Язык: {data['lang']}\n"
        f"👤 ФИО: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"💼 Тариф: {data['tariff']}"
    )

    # Отправляем в Telegram-группу
    await bot.send_message(GROUP_CHAT_ID, text)

    # Пишем в Google Sheets
    try:
        sheet = get_sheet()
        sheet.append_row([
            data['lang'],
            data['name'],
            data['phone'],
            data['company'],
            data['tariff']
        ])
    except Exception as e:
        logging.error(f"Ошибка при записи в Google Sheets: {e}")
        await message.answer(prompts[lang]['sheet_error'])
    else:
        await message.answer(prompts[lang]['thank_you'])

    await state.finish()

# ── в конце вашего файла, заменяем старый fallback этим:

@dp.message_handler(
    lambda msg: msg.text and not msg.text.startswith('/'),
    state=None              # <— ловим только если нет активного state
)
async def fallback(message: types.Message):
    # если FSM уже окончена, но юзер пишет что-то не по команде — подсказываем ему /start
    await message.answer("Чтобы начать, введите команду /start")

# ── ниже ваш on_startup и запуск polling без изменений ──
async def on_startup(dp: Dispatcher):
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook удалён, готов к polling")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

        try:
            executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
            break
        except TerminatedByOtherGetUpdates:
            logging.warning("Конфликт polling, перезапуск через 5 сек")
            time.sleep(5)

if __name__ == '__main__':
    run()
