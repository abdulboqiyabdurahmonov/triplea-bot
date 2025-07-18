import os
import json
import logging
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.executor import start_webhook

# ============================================================
# Configuration
# ============================================================
API_TOKEN        = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID    = int(os.getenv('GROUP_CHAT_ID', '0'))
SPREADSHEET_ID   = os.getenv('SPREADSHEET_ID')
WORKSHEET_NAME   = os.getenv('WORKSHEET_NAME', 'Лист1')   # заявки
CALC_SHEET_NAME  = os.getenv('CALC_WORKSHEET_NAME', 'Calc')
MANAGER_URL      = os.getenv('MANAGER_URL', 'https://t.me/+998946772399')

WEBHOOK_HOST     = os.getenv('WEBHOOK_HOST')  # e.g. https://triplea-bot-5.onrender.com
WEBHOOK_PATH     = f"/webhook/{API_TOKEN}"
WEBHOOK_URL      = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST      = '0.0.0.0'
WEBAPP_PORT      = int(os.getenv('PORT', 8000))

# ============================================================
# Bot & Dispatcher
# ============================================================
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ============================================================
# Google Sheets setup
# ============================================================
SERVICE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
if SERVICE_CREDENTIALS_JSON:
    creds_dict = json.loads(SERVICE_CREDENTIALS_JSON)
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
    )
else:
    SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        SERVICE_ACCOUNT_FILE,
        ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
    )
gc = gspread.authorize(credentials)
# основной лист для заявок
sheet_leads = gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

# лист для калькулятора
try:
    sheet_calc = gc.open_by_key(SPREADSHEET_ID).worksheet(CALC_SHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    sh = gc.open_by_key(SPREADSHEET_ID)
    sheet_calc = sh.add_worksheet(title=CALC_SHEET_NAME, rows=2000, cols=20)
    sheet_calc.append_row([
        "timestamp_utc", "user_id", "username", "source",
        "operators", "salary", "calls_per_day", "work_days",
        "tax_pct", "hidden_pct", "cost_min", "cost_full"
    ])

# ============================================================
# Utility helpers
# ============================================================
def to_int(text, default=0):
    """Try to extract int from user text."""
    try:
        # remove spaces, commas
        clean = ''.join(ch for ch in str(text) if ch.isdigit())
        return int(clean) if clean else default
    except Exception:
        return default

def fmt(num):
    """Format int with space thousands."""
    try:
        return f"{int(round(num)):,}".replace(",", " ")
    except Exception:
        return str(num)

def calc_cost(ops, salary, calls_per_day, days, tax_pct, hidden_pct):
    """
    Unified cost formula.
    salary - per operator, before taxes
    tax_pct, hidden_pct in percents (0-100)
    """
    base   = salary * ops
    taxed  = base * (1 + (tax_pct/100.0))
    total  = taxed * (1 + (hidden_pct/100.0))
    total_calls = max(ops * calls_per_day * days, 1)
    cost_min  = taxed / total_calls
    cost_full = total / total_calls
    return base, taxed, total, total_calls, cost_min, cost_full

async def log_calc_result(source, user: types.User, data, cost_min, cost_full):
    """Append calculator data to Google Sheet."""
    try:
        sheet_calc.append_row([
            datetime.utcnow().isoformat(),
            user.id,
            f"@{user.username}" if user.username else "",
            source,
            data.get('ops'),
            data.get('salary'),
            data.get('calls'),
            data.get('days'),
            data.get('tax'),
            data.get('hidden'),
            cost_min,
            cost_full
        ])
    except Exception as e:
        logging.error(f"Ошибка записи калькулятора в Google Sheets: {e}")

async def log_lead_to_sheet(name, phone, company, tariff, lang):
    try:
        sheet_leads.append_row([name, phone, company, tariff, lang, datetime.utcnow().isoformat()])
    except Exception as e:
        logging.error(f"Ошибка при записи лида в Google Sheets: {e}")

# ============================================================
# FSM States: Lead Capture
# ============================================================
class Form(StatesGroup):
    lang    = State()
    name    = State()
    phone   = State()
    company = State()
    tariff  = State()

# ============================================================
# FSM States: Calculator
# ============================================================
class CalcForm(StatesGroup):
    lang    = State()  # reuse if known
    ops     = State()
    salary  = State()
    calls   = State()
    days    = State()
    tax     = State()
    hidden  = State()
    done    = State()

# ============================================================
# Start command
# ============================================================
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    # стартовое меню: язык + калькулятор
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Русский", callback_data="lang_ru"),
        InlineKeyboardButton("O'zbekcha", callback_data="lang_uz"),
    )
    keyboard.add(
        InlineKeyboardButton("🧮 Калькулятор стоимости", callback_data="calc_ru")
    )
    await message.answer(
        "👋 Привет! Я голосовой помощник TRIPLEA.\n\n"
        "Помогаю бизнесу:\n"
        "— продавать через автообзвоны,\n"
        "— взыскивать задолженность,\n"
        "— собирать аналитику и формировать отчёты.\n\n"
        "Хочешь протестировать на своей базе или посчитать себестоимость живых операторов?\n"
        "👇 Выбери язык или сразу запусти калькулятор:",
        reply_markup=keyboard
    )
    await Form.lang.set()

# ============================================================
# Language selection
# ============================================================
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('lang_'), state=Form.lang)
async def process_lang(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = callback.data.split('_')[1]
    await state.update_data(lang=lang)
    if lang == 'ru':
        await bot.send_message(callback.from_user.id, "Введите ваше ФИО:")
    else:
        await bot.send_message(callback.from_user.id, "Iltimos, to‘liq ismingizni yozing:")
    await Form.name.set()

# ============================================================
# Lead capture steps
# ============================================================
@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Введите ваш номер телефона:")
    else:
        await message.answer("Telefon raqamingizni kiriting:")
    await Form.phone.set()

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Введите название вашей компании:")
    else:
        await message.answer("Kompaniyangiz nomini yozing:")
    await Form.company.set()

@dp.message_handler(state=Form.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Старт (750 сум/звонок)", callback_data="tariff_start"),
        InlineKeyboardButton("Бизнес (600 сум/звонок)", callback_data="tariff_business"),
        InlineKeyboardButton("Корпоративный (450 сум/звонок)", callback_data="tariff_corp")
    )
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Выберите тариф:", reply_markup=keyboard)
    else:
        await message.answer(
            "Tarifni tanlang:\n- Start (750 so‘m/qo‘ng‘iroq)\n- Biznes (600 so‘m/qo‘ng‘iroq)\n- Korporativ (450 so‘m/qo‘ng‘iroq)",
            reply_markup=keyboard
        )
    await Form.tariff.set()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('tariff_'), state=Form.tariff)
async def process_tariff(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tariff = callback.data.split('_', 1)[1]
    data = await state.get_data()
    name    = data.get('name')
    phone   = data.get('phone')
    company = data.get('company')
    lang    = data.get('lang', 'ru')

    # send to group
    text = (
        f"📥 Новый запрос из бота ({lang})\n"
        f"👤 ФИО: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"🏢 Компания: {company}\n"
        f"💼 Тариф: {tariff}"
    )
    if GROUP_CHAT_ID != 0:
        await bot.send_message(GROUP_CHAT_ID, text)

    # log to sheets
    await log_lead_to_sheet(name, phone, company, tariff, lang)

    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("💬 Написать менеджеру", url=MANAGER_URL),
    )

    if lang == 'ru':
        thank_you = "✅ Спасибо! Ваша заявка принята.\n\nМенеджер свяжется с вами в ближайшее время."
    else:
        thank_you = "✅ Rahmat! So‘rovingiz qabul qilindi.\n\nMenejerimiz siz bilan tez orada bog‘lanadi."

    await bot.send_message(callback.from_user.id, thank_you, reply_markup=keyboard)
    await state.finish()

# ============================================================
# Trigger calculator from callback (start screen)
# ============================================================
@dp.callback_query_handler(lambda c: c.data in ('calc_ru', 'calc_uz'), state='*')
async def calc_from_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = 'ru' if callback.data == 'calc_ru' else 'uz'
    await start_calc_flow(callback.from_user.id, lang=lang)

# ============================================================
# Trigger calculator from message (/calc or text)
# ============================================================
@dp.message_handler(commands=['calc'], state='*')
async def calc_cmd(message: types.Message, state: FSMContext):
    # если ранее выбирали язык, возьмём его
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    await start_calc_flow(message.chat.id, lang=lang)

@dp.message_handler(lambda m: m.text and m.text.lower() in ('калькулятор', 'kalkulyator', 'calc', 'calculator'), state='*')
async def calc_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    await start_calc_flow(message.chat.id, lang=lang)

# ============================================================
# Calculator flow functions
# ============================================================
async def start_calc_flow(chat_id: int, lang='ru'):
    # set initial state
    state = dp.current_state(chat=chat_id, user=chat_id)
    await state.set_state(CalcForm.lang)
    await state.update_data(lang=lang)
    if lang == 'ru':
        await bot.send_message(chat_id, "🧮 Калькулятор стоимости оператора.\n\nСколько операторов у вас в штате? (число)")
    else:
        await bot.send_message(chat_id, "🧮 Operator narxi kalkulyatori.\n\nNechta operator ishlaydi? (son)")

    await CalcForm.ops.set()

@dp.message_handler(state=CalcForm.ops)
async def calc_ops_handler(message: types.Message, state: FSMContext):
    ops = to_int(message.text, default=1)
    if ops <= 0:
        ops = 1
    await state.update_data(ops=ops)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Зарплата 1 оператора (сум/мес)? (по рынку ~5 000 000)")
    else:
        await message.answer("Bitta operator maoshi (so‘m/oy)? (bozorda ~5 000 000)")
    await CalcForm.salary.set()

@dp.message_handler(state=CalcForm.salary)
async def calc_salary_handler(message: types.Message, state: FSMContext):
    salary = to_int(message.text, default=5_000_000)
    if salary < 1_000_000:
        # мягкое предупреждение
        await message.answer("⚠️ Цифра выглядит низкой. Всё равно использовать? Напишите ту же цифру или введите новую.")
        salary = max(salary, 1_000_000)
    await state.update_data(salary=salary)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Сколько реальных звонков делает один оператор в день? (рекомендую 150)")
    else:
        await message.answer("Kuniga nechta qo‘ng‘iroq? (tavsiya 150)")
    await CalcForm.calls.set()

@dp.message_handler(state=CalcForm.calls)
async def calc_calls_handler(message: types.Message, state: FSMContext):
    calls = to_int(message.text, default=150)
    if calls <= 0:
        calls = 150
    await state.update_data(calls=calls)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Сколько рабочих дней в мес? (22 по умолчанию)")
    else:
        await message.answer("Oydagi ish kunlari soni? (22 default)")
    await CalcForm.days.set()

@dp.message_handler(state=CalcForm.days)
async def calc_days_handler(message: types.Message, state: FSMContext):
    days = to_int(message.text, default=22)
    if days <= 0 or days > 31:
        days = 22
    await state.update_data(days=days)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Налоги + соц (% от оклада). (30 по умолчанию)")
    else:
        await message.answer("Soliqlar + ijtimoiy (%). (30 default)")
    await CalcForm.tax.set()

@dp.message_handler(state=CalcForm.tax)
async def calc_tax_handler(message: types.Message, state: FSMContext):
    tax = to_int(message.text, default=30)
    if tax < 0: tax = 0
    if tax > 100: tax = 100
    await state.update_data(tax=tax)
    data = await state.get_data()
    if data.get('lang') == 'ru':
        await message.answer("Скрытые расходы (% минимум). (15 рекомендую)")
    else:
        await message.answer("Yashirin xarajatlar (% min). (15 tavsiya)")
    await CalcForm.hidden.set()

@dp.message_handler(state=CalcForm.hidden)
async def calc_hidden_handler(message: types.Message, state: FSMContext):
    hidden = to_int(message.text, default=15)
    if hidden < 0: hidden = 0
    if hidden > 100: hidden = 100
    await state.update_data(hidden=hidden)

    # расчёт
    data = await state.get_data()
    lang  = data.get('lang', 'ru')
    base, taxed, total, total_calls, cost_min, cost_full = calc_cost(
        ops=data['ops'],
        salary=data['salary'],
        calls_per_day=data['calls'],
        days=data['days'],
        tax_pct=data['tax'],
        hidden_pct=data['hidden']
    )

    # логируем
    await log_calc_result("telegram", message.from_user, data, cost_min, cost_full)

    # вывод результата
    if lang == 'ru':
        txt = (
            "📊 *Результат расчёта*\n\n"
            f"Операторов: {data['ops']}\n"
            f"ФОТ (с налогами): {fmt(taxed)} сум/мес\n"
            f"Итого со скрытыми: {fmt(total)} сум/мес\n"
            f"Звонков в мес: {fmt(total_calls)}\n\n"
            f"Себестоимость звонка (мин): *{fmt(cost_min)} сум*\n"
            f"Себестоимость (со скрытыми): *{fmt(cost_full)} сум*\n\n"
            "🔁 Для сравнения: TripleA пакеты 750 / 600 / 450 сум/звонок.\n"
            "Хочешь коммерческое предложение или демо?"
        )
        pdf_txt = "Получить PDF расчёт"
        mgr_txt = "Связаться с менеджером"
        test_txt = "Тест 1000 звонков"
    else:
        txt = (
            "📊 *Hisob natijasi*\n\n"
            f"Operatorlar: {data['ops']}\n"
            f"Oylik (soliqlar bilan): {fmt(taxed)} so‘m/oy\n"
            f"Yashirin bilan: {fmt(total)} so‘m/oy\n"
            f"Oydagi qo‘ng‘iroqlar: {fmt(total_calls)}\n\n"
            f"Bir qo‘ng‘iroq narxi (min): *{fmt(cost_min)} so‘m*\n"
            f"Yashirin bilan: *{fmt(cost_full)} so‘m*\n\n"
            "TripleA: 750 / 600 / 450 so‘m.\n"
            "Tijoriy taklif yoki demo kerakmi?"
        )
        pdf_txt  = "PDF hisob"
        mgr_txt  = "Menejer bilan bog‘lanish"
        test_txt = "1000 qo‘ng‘iroq test"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(pdf_txt, callback_data="calc_pdf"))
    kb.add(InlineKeyboardButton(mgr_txt, url=MANAGER_URL))
    kb.add(InlineKeyboardButton(test_txt, callback_data="calc_test1000"))

    await message.answer(txt, reply_markup=kb, parse_mode="Markdown")
    await CalcForm.done.set()

# ============================================================
# Calculator callback buttons
# ============================================================
@dp.callback_query_handler(lambda c: c.data == "calc_pdf", state='*')
async def calc_pdf_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    # здесь можно генерить PDF и отправлять файл
    # пока отправим заглушку
    await bot.send_message(
        callback.from_user.id,
        "PDF расчёт готовится. Менеджер отправит вам файл в ближайшее время. "
        "Если нужно срочно — нажмите кнопку менеджера выше."
    )

@dp.callback_query_handler(lambda c: c.data == "calc_test1000", state='*')
async def calc_test_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    # уведомим группу, что юзер хочет тест
    u = callback.from_user
    text = f"🚀 Пользователь @{u.username or u.id} запросил *ТЕСТ 1000 звонков* через калькулятор."
    if GROUP_CHAT_ID != 0:
        await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")
    await bot.send_message(
        callback.from_user.id,
        "Отлично! Мы получили запрос на тест 1000 звонков. Менеджер свяжется с вами."
    )

# ============================================================
# Webhook setup
# ============================================================
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set: {WEBHOOK_URL}")

async def on_shutdown(dp):
    logging.info("Shutting down..")
    await bot.delete_webhook()

# ============================================================
# Entrypoint
# ============================================================
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
