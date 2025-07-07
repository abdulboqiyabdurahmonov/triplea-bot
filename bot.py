import os
from aiogram import Bot, Dispatcher, types

# Берём токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я бот TripleA.")

@dp.message_handler()
async def echo_all(message: types.Message):
    # просто эхо всех входящих текстов
    await message.answer(f"Вы сказали: {message.text}")
