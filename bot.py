import os
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters

TOKEN = os.environ['BOT_TOKEN']  # передаём ваш токен через переменную окружения

bot = Bot(token=TOKEN)
app = Flask(__name__)

# Настраиваем диспетчер, чтобы он разбирал обновления из Flask
dispatcher = Dispatcher(bot, update_queue=None, workers=0, use_context=True)

# Обработчики команд
def start(update: Update, context):
    update.message.reply_text("Привет! Я работаю на python-telegram-bot.")

def echo(update: Update, context):
    # просто эхо
    text = update.message.text
    update.message.reply_text(f"Вы написали: {text}")

# Регистрируем их
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))


# Точка входа для Telegram Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK", 200


# Точка для проверки живости сервиса
@app.route("/", methods=["GET"])
def index():
    return "Bot is alive!", 200


if __name__ == "__main__":
    # Для локального теста
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
