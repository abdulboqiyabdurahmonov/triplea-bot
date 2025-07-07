import os
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

# 1) Читаем токен из переменных среды
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=TOKEN)
app = Flask(__name__)

# 2) Создаём dispatcher — он разобьёт входящее Update на нужный handler
dispatcher = Dispatcher(bot, None, use_context=True)

# 3) Опишите команды
def start(update: Update, context):
    update.message.reply_text("Привет! Я бот на TripleA.")

def echo(update: Update, context):
    update.message.reply_text(f"Вы сказали: {update.message.text}")

# 4) Регистрируем наши обработчики
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# 5) Точка входа для Telegram Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return "OK"

# 6) Локальный запуск (не нужен на Render, но полезен для отладки)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
