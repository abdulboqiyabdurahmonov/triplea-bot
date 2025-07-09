# main.py

import os
import logging
import time

import gspread
import json
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


class Form(StatesGroup):
    lang    = State()
    name    = State()
    phone   = State()
    company = State()
    tariff  = State()


@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    # Начинаем заново
    await state.finish()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    # Теперь выбор: Русский и Узбекский
    kb.add("Русский", "Узбекский")
    await Form.lang.set()
    await message.answer("Пожалуйста, выберите язык:", reply_markup=kb)


@dp.message_handler(state=Form.lang)
async def process_lang(message: types.Message, state: FSMContext):
    # Принимаем только Русский и Узбекский
    if message.text not in ["Русский", "Узбекский"]:
        return await message.answer("Нужно выбрать кнопкой: Русский или Узбекский.")
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

    # Пытаемся записать в Google Sheets
    try:
        sheet = get_sheet()
        sheet.append_row([
            data['lang'],
            data['name'],
            data['phone'],
            data['company'],
            data['tariff']
        ])
        logging.info("Заявка успешно добавлена в Google Sheets")
    except Exception as e:
        logging.error(f"Ошибка при записи в Google Sheets: {e}")

    await message.answer("Спасибо! Ваша заявка отправлена.")
    await state.finish()


@dp.message_handler(lambda msg: msg.text and not msg.text.startswith('/'), state='*')
async def fallback(message: types.Message):
    await message.answer("Чтобы начать, введите команду /start")


@dp.errors_handler(exception=TerminatedByOtherGetUpdates)
async def ignore_conflict(update, exception):
    # Игнорируем конфликт polling’ов
    logging.warning("Игнорируем TerminatedByOtherGetUpdates – продолжим polling")
    return True


async def on_startup(dp: Dispatcher):
    # Отключаем вебхук и сбрасываем накопившиеся обновления
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook удалён, готов к polling-режиму")


def run():
    # Цикл перезапуска polling при конфликтах
    while True:
        try:
            executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
            break
        except TerminatedByOtherGetUpdates:
            logging.warning("Второй polling обнаружен, перезапуск через 5с")
            time.sleep(5)
        except Exception:
            logging.exception("Неожиданная ошибка, выхожу")
            break


if __name__ == '__main__':
    run()
