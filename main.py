import os
from fastapi import FastAPI, Request, HTTPException
from bot import bot

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://<ваше-имя-сервиса>.onrender.com/webhook
if not WEBHOOK_URL:
    raise RuntimeError("Установите WEBHOOK_URL, например https://xyz.onrender.com/webhook")

PORT = int(os.getenv("PORT", 8000))

app = FastAPI()

@app.on_event("startup")
def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(WEBHOOK_URL)

@app.post(WEBHOOK_PATH)
async def receive_update(req: Request):
    data = await req.json()
    try:
        update = types.Update.de_json(data)
    except Exception:
        raise HTTPException(400, "Bad request")
    bot.process_new_updates([update])
    return {"ok": True}

@app.on_event("shutdown")
def shutdown():
    bot.remove_webhook()

# для локального запуска (polling):
if __name__ == "__main__":
    # polling вместо webhook:
    bot.remove_webhook()
    bot.infinity_polling()
    

    return {"ok": True}  # Telegram ждёт любой валидный JSON с status 200
