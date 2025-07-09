# main.py

import os, logging, gspread, json
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

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

# Вот наша новая функция для доступа к таблице
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

# ... все остальные хендлеры до process_tariff ...

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

    await bot.send_message(GROUP_CHAT_ID, text)

    # вместо глобального sheet используем функцию
    sheet = get_sheet()
    sheet.append_row([
        data['lang'],
        data['name'],
        data['phone'],
        data['company'],
        data['tariff']
    ])

    await message.answer("Спасибо! Ваша заявка отправлена.")
    await state.finish()

# ... остальные хендлеры и запуск polling-а ...

@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Чтобы начать, введите команду /start")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
