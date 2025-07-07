import os
from telebot import TeleBot, types

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Установите переменную окружения BOT_TOKEN")

bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    bot.reply_to(message, "👋 Привет! Я простой бот на telebot.")

@bot.message_handler(func=lambda m: True)
def echo_all(message: types.Message):
    bot.reply_to(message, f"Вы написали: {message.text}")
