from fastapi import FastAPI, Request
import uvicorn
import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from handlers import dp, bot
from data import user_data, processed_updates
from database import db, save_user_data
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

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
        from utils import set_bot_commands
        await set_bot_commands()
        if db:
            try:
                docs = db.collection('users').stream()
                for doc in docs:
                    try:
                        user_id_int = int(doc.id)
                        user_data[user_id_int] = doc.to_dict()
                        logging.info(f"Загружены данные пользователя {user_id_int} из Firestore")
                    except ValueError:
                        logging.warning(f"Пропуск невалидного user_id: {doc.id} (не число)")
                logging.info("Все user_data загружены из Firestore")
            except Exception as e:
                logging.error(f"Ошибка загрузки user_data из Firestore: {e}")
    except Exception as e:
        logging.error(f"Ошибка в lifespan (startup): {e}", exc_info=True)
    yield
    try:
        await bot.delete_webhook()
        logging.info("Webhook удалён при завершении работы")
    except Exception as e:
        logging.error(f"Ошибка в lifespan (shutdown): {e}", exc_info=True)

app = FastAPI(lifespan=lifespan)

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
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), workers=1)