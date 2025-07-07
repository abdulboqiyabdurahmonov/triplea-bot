import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# — ВАШ ТОКЕН И ID ГРУППЫ —
TOKEN = "7993696802:AAHsaOyLkComr4mr2WsC-EgnB5jcHKjd7Ho"
GROUP_CHAT_ID = -1002344973979  # ID вашей группы

# — Состояния разговора —
NAME, PHONE, TARIFF, COMPANY = range(4)

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запуск разговора, просим ФИО."""
    await update.message.reply_text("Привет! Пожалуйста, введите ваше ФИО:")
    return NAME


async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["fio"] = update.message.text
    await update.message.reply_text("Спасибо! Теперь введите ваш номер телефона:")
    return PHONE


async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["phone"] = update.message.text
    await update.message.reply_text(
        "Отлично. Выберите тариф (Старт, Бизнес или Корпоративный):"
    )
    return TARIFF


async def tariff_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["tariff"] = update.message.text
    await update.message.reply_text("И, наконец, введите название вашей компании:")
    return COMPANY


async def company_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["company"] = update.message.text

    # Формируем итоговое сообщение
    data = context.user_data
    summary = (
        f"📬 *Новая заявка!*\n"
        f"• *ФИО:* _{data['fio']}_\n"
        f"• *Телефон:* `{data['phone']}`\n"
        f"• *Тариф:* _{data['tariff']}_\n"
        f"• *Компания:* _{data['company']}_"
    )

    # Отправляем в группу
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID, text=summary, parse_mode="Markdown"
    )

    # Подтверждаем пользователю
    await update.message.reply_text("Спасибо! Ваша заявка отправлена в группу.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Опрос отменён.")
    return ConversationHandler.END


def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
            TARIFF: [MessageHandler(filters.TEXT & ~filters.COMMAND, tariff_handler)],
            COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, company_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)

    # Для локального запуска через polling
    app.run_polling()


if __name__ == "__main__":
    main()
