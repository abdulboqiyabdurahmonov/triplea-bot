import os
import json
from fastapi import FastAPI, Request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# Загрузка конфигурации из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", 0))  # ID Telegram-группы для заявок
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Домен с https://
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
# Настройки Google Sheets
GSHEET_CREDENTIALS_JSON = os.getenv("GSHEET_CREDENTIALS_JSON")  # JSON сервисного аккаунта
GSHEET_SHEET_ID = os.getenv("GSHEET_SHEET_ID")               # ID таблицы

# Инициализация бота и хранилища состояний
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = FastAPI()

# Подключение к Google Sheets (если есть данные)
sheet = None
if GSHEET_CREDENTIALS_JSON and GSHEET_SHEET_ID:
    creds_dict = json.loads(GSHEET_CREDENTIALS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(GSHEET_SHEET_ID).sheet1

# Определение FSM-состояний
class Form(StatesGroup):
    lang = State()
    name = State()
    phone = State()
    company = State()
    tariff = State()

# Клавиатуры
lang_kb = types.InlineKeyboardMarkup(row_width=2)
lang_kb.add(
    types.InlineKeyboardButton("Русский", callback_data="ru"),
    types.InlineKeyboardButton("O‘zbek", callback_data="uz")
)
tariff_kb = types.InlineKeyboardMarkup(row_width=1)
tariff_kb.add(
    types.InlineKeyboardButton("Старт (750 сум/звонок)", callback_data="Старт"),
    types.InlineKeyboardButton("Бизнес (600 сум/звонок)", callback_data="Бизнес"),
    types.InlineKeyboardButton("Корпоратив (450 сум/звонок)", callback_data="Корпоратив")
)

# Хэндлеры
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(Form.lang)
    await message.answer(
        "Пожалуйста, выберите язык / Iltimos tilni tanlang:",
        reply_markup=lang_kb
    )

@dp.callback_query_handler(lambda c: c.data in ["ru", "uz"], state=Form.lang)
async def process_lang(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(lang=call.data)
    await state.set_state(Form.name)
    prompt = "Введите ваше ФИО:" if call.data == "ru" else "Ismingizni kiriting:"
    await call.message.answer(prompt)
    await call.answer()

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(Form.phone)
    await message.answer("Введите ваш номер телефона:")

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(Form.company)
    await message.answer("Введите название вашей компании:")

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    await state.set_state(Form.tariff)
    await message.answer("Выберите тариф:", reply_markup=tariff_kb)

@dp.callback_query_handler(lambda c: c.data in ["Старт", "Бизнес", "Корпоратив"], state=Form.tariff)
async def process_tariff(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tariff = call.data
    # Формируем сообщение для группы
    text = (
        f"📥 <b>Новая заявка</b>\n\n"
        f"👤 <b>Имя:</b> {data.get('name')}\n"
        f"📞 <b>Телефон:</b> {data.get('phone')}\n"
        f"🏢 <b>Компания:</b> {data.get('company')}\n"
        f"💼 <b>Тариф:</b> {tariff}"
    )
    await bot.send_message(GROUP_ID, text)
    # Отправка в Google Sheets (если настроено)
    if sheet:
        try:
            sheet.append_row([
                data.get('lang'),
                data.get('name'),
                data.get('phone'),
                data.get('company'),
                tariff
            ])
        except Exception as e:
            print("Ошибка записи в Google Sheets:", e)
    # Благодарим пользователя
    thank = (
        "Спасибо! Ваша заявка отправлена." 
        if data.get('lang') == "ru" 
        else "Rahmat! Arizangiz qabul qilindi."
    )
    await call.message.answer(thank)
    await state.finish()
    await call.answer()

@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply("Действие отменено.")

# Webhook и сервер
@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await storage.close()
    await storage.wait_closed()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("telegram_bot:app", host="0.0.0.0", port=port, log_level="info")
