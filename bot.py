import os
from flask import Flask, request
import telebot

# 1) Токен из окружения
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных среды")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# 2) Хэндлер на команду /start
@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я бот на TripleA.")

# 3) Эхо-хэндлер
@bot.message_handler(func=lambda m: True)
def echo_all(message):
    bot.reply_to(message, f"Вы сказали: {message.text}")

# 4) Вебхук-энпоинт
@app.route("/webhook", methods=["POST"])
def webhook():
    json_str = request.get_data(as_text=True)
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# 5) Для локального запуска
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
from telegram import Update
from telegram.ext import CommandHandler, ApplicationBuilder, ContextTypes

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        f"Chat ID = `{chat.id}`",
        parse_mode="Markdown"
    )

def main():
    app = ApplicationBuilder().token("ВАШ_ТОКЕН").build()
    app.add_handler(CommandHandler("getid", getid))
    app.run_polling()
