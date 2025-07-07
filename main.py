import os
from fastapi import FastAPI, Request, HTTPException
from bot import bot, dp
from aiogram.types import Update

WEBHOOK_PATH = "/webhook"
# полная публичная ссылка, например https://your-service.onrender.com/webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise RuntimeError("Set WEBHOOK_URL environment variable, e.g. https://xyz.onrender.com/webhook")

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8000))

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # регистрируем webhook в Telegram
    await bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    # снимаем webhook
    await bot.delete_webhook()
    await bot.session.close()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    body = await req.json()
    update = Update(**body)
    # прокидываем апдейт в диспетчер
    await dp.process_update(update)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT)
