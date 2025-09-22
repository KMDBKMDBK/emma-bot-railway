import logging
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from api_key_manager import TELEGRAM_TOKEN, RENDER_URL
from utils import set_bot_commands

logging.basicConfig(level=logging.INFO)

app = FastAPI()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

@app.on_event("startup")
async def on_startup():
    webhook_url = f"{RENDER_URL}/webhook"
    try:
        await bot.set_webhook(webhook_url)
        logging.info(f"Webhook установлен: {webhook_url}")
        await set_bot_commands()
    except Exception as e:
        logging.error(f"Ошибка установки webhook: {e}")

@app.post("/webhook")
async def webhook(request: Request):
    try:
        update = await request.json()
        update = Update(**update)
        await dp.feed_raw_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Ошибка обработки webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    try:
        bot_info = await bot.get_me()
        webhook_info = await bot.get_webhook_info()
        updates = await bot.get_updates(limit=1)
        return {
            "status": "ok",
            "bot_ready": bool(bot_info),
            "webhook_url": webhook_info.url,
            "pending_updates": len(updates)
        }
    except Exception as e:
        logging.error(f"Ошибка health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))