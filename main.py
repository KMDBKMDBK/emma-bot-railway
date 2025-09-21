import os
import logging
import json
import base64
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from handlers import dp, bot, user_data, processed_updates
from utils import set_bot_commands
from database import db, load_user_data

# Настройка логов
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Загрузка переменных окружения
load_dotenv()
logging.info("Переменные окружения загружены")

# Инициализация Firebase
firebase_credentials = os.getenv("FIREBASE_CREDENTIALS_JSON")
if firebase_credentials:
    try:
        cred_json = base64.b64decode(firebase_credentials).decode()
        cred = credentials.Certificate(json.loads(cred_json))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase инициализирован успешно (base64)")
    except Exception as e:
        db = None
        logging.warning(f"Firebase не инициализирован из base64: {e}")
else:
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase инициализирован успешно (локальный путь)")
    else:
        db = None
        logging.warning("Firebase не инициализирован (проверь FIREBASE_CREDENTIALS_PATH или FIREBASE_CREDENTIALS_JSON)")

# Инициализация бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    logging.error("TELEGRAM_TOKEN не указан в .env")
    exit(1)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
user_data = {}
processed_updates = set()

# FastAPI приложение
app = FastAPI(lifespan=lifespan)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Запуск lifespan: настройка webhook и загрузка данных")
    try:
        render_url = os.getenv('RENDER_URL', 'emma-bot-render.onrender.com')
        webhook_url = f"https://{render_url}/webhook"
        logging.info(f"Установка webhook на {webhook_url}")
        await bot.set_webhook(webhook_url)
        info = await bot.get_webhook_info()
        logging.info(f"Webhook установлен: url={info.url}, pending_updates={info.pending_update_count}")
        await set_bot_commands()
        if db:
            await load_user_data()
    except Exception as e:
        logging.error(f"Ошибка в lifespan (startup): {e}", exc_info=True)
    yield
    try:
        await bot.delete_webhook()
        logging.info("Webhook удалён при завершении работы")
    except Exception as e:
        logging.error(f"Ошибка в lifespan (shutdown): {e}", exc_info=True)

@app.get("/health")
@app.head("/health")
async def health_check():
    logging.info("Запрос к /health")
    try:
        info = await bot.get_webhook_info()
        logging.info(f"Health check успешен: webhook_url={info.url}, pending_updates={info.pending_update_count}")
        return {
            "status": "ok",
            "bot_ready": True,
            "webhook_url": info.url,
            "pending_updates": info.pending_update_count
        }
    except Exception as e:
        logging.error(f"Ошибка в health check: {e}", exc_info=True)
        return {"status": "error", "bot_ready": False, "error": str(e)}

@app.post("/webhook")
async def webhook(request: Request):
    logging.debug(f"Получен webhook запрос: headers={request.headers}")
    try:
        body = await request.body()
        logging.debug(f"Тело запроса: {body}")
        if not body:
            logging.error("Пустое тело запроса")
            return {"status": "error", "message": "Empty request body"}
        update = await request.json()
        logging.debug(f"Получен update: {update}")
        update_id = update.get("update_id")
        if update_id in processed_updates:
            logging.info(f"Повторный update_id: {update_id}, пропущен")
            return {"status": "ok"}
        processed_updates.add(update_id)
        await dp.feed_raw_update(bot, update)
        logging.debug("Update успешно обработан")
        return {"status": "ok"}
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка декодирования JSON: {e}")
        return {"status": "error", "message": f"JSON decode error: {str(e)}"}
    except Exception as e:
        logging.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

if __name__ == '__main__':
    logging.info("Запуск приложения через uvicorn")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), workers=1)