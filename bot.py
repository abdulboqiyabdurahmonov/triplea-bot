import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ——— Параметры ———
API_TOKEN     = os.getenv('BOT_TOKEN', 'ВАШ_ТОКЕН_ЗДЕСЬ')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', '-1002344973979'))

CREDS_FILE       = 'credentials.json'        # файл с ключами Google API
SPREADSHEET_NAME = 'Имя_вашей_таблицы'
WORKSHEET_NAME   = 'Лист1'
# —————————————————

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Авторизация в Google Sheets
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]
creds   = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
gc      = gspread.authorize(creds)
sheet   = gc.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)


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
    kb.add("Русский", "English")
    await Form.lang.set()
    await message.answer("Пожалуйста, выберите язык:", reply_markup=kb)


@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    if message.text not in ["Русский", "English"]:
        return await message.answer("Нужно выбрать кнопкой: Русский или English.")
    await state.update_data(lang=message.text)
    await Form.name.set()
    await message.answer("Введите ваше ФИО:", reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await Form.phone.set()
    await message.answer("Введите номер телефона:")


@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await Form.company.set()
    await message.answer("Введите название компании:")


@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text.strip())
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("Старт", "Бизнес", "Корпоратив")
    await Form.tariff.set()
    await message.answer("Выберите тариф:", reply_markup=kb)


@dp.message_handler(state=Form.tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    if message.text not in ["Старт", "Бизнес", "Корпоратив"]:
        return await message.answer("Нужно выбрать один из трёх тарифов кнопками.")
    await state.update_data(tariff=message.text)

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

    # Записываем в Google Sheets
    sheet.append_row([
        data['lang'],
        data['name'],
        data['phone'],
        data['company'],
        data['tariff']
    ])

    await message.answer("Спасибо! Ваша заявка отправлена.")
    await state.finish()


@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Чтобы начать, введите команду /start")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
