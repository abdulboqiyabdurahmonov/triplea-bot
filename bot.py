import os
import logging
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Update
from aiogram.dispatcher.webhook import ConfigureDispatcher

# 1) Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2) Читаем токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("Не задан BOT_TOKEN в окружении!")
    raise RuntimeError("BOT_TOKEN is required")

# 3) Инициализируем Bot и Dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# 4) FastAPI-приложение
app = FastAPI()

# 5) При старте приложения — устанавливаем вебхук
@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        logger.error("Не задана переменная WEBHOOK_URL!")
        raise RuntimeError("WEBHOOK_URL is required")
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

# 6) При завершении — удаляем вебхук
@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()

# 7) Обработчик Telegram-апдейтов по POST /webhook
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update(**data)
    except Exception as e:
        logger.exception("Не удалось распарсить Update")
        raise HTTPException(status_code=400, detail="Invalid update")
    # Передаём апдейт в Aiogram
    await dp.feed_update(update)
    return {"ok": True}

# 8) Регистрируем пару простых хендлеров
@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я эхо-бот. Пришли мне что угодно — я верну это обратно."
    )

@dp.message()  # любой текст
async def echo_all(message: types.Message):
    await message.answer(f"Вы сказали: {message.text}")

# 9) Для локального запуска (uvicorn bot:app)
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("bot:app", host="0.0.0.0", port=port, reload=True)

