import logging
from fastapi import FastAPI, Request
import uvicorn
from aiogram import Bot, Dispatcher
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
from handlers import register_handlers
from database import init_firebase

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
logger.info("Переменные окружения загружены")

# Инициализация FastAPI
app = FastAPI()

# Инициализация бота и диспетчера
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN не указан в .env")
    exit(1)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Регистрация обработчиков и Firebase
register_handlers(dp)
init_firebase()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск lifespan: настройка webhook и загрузка данных")
    try:
        render_url = os.getenv("RENDER_URL", "emma-bot-render.onrender.com")
        webhook_url = f"https://{render_url}/webhook"
        logger.info(f"Установка webhook на {webhook_url}")
        await bot.set_webhook(webhook_url)
        info = await bot.get_webhook_info()
        logger.info(f"Webhook установлен: url={info.url}, pending_updates={info.pending_update_count}")
        from handlers import set_bot_commands
        await set_bot_commands(bot)
    except Exception as e:
        logger.error(f"Ошибка в lifespan (startup): {e}", exc_info=True)
    yield
    try:
        await bot.delete_webhook()
        await bot.session.close()
        logger.info("Webhook удалён, сессия закрыта")
    except Exception as e:
        logger.error(f"Ошибка в lifespan (shutdown): {e}", exc_info=True)

app = FastAPI(lifespan=lifespan)

@app.get("/health")
@app.head("/health")
async def health_check():
    logger.info("Запрос к /health")
    try:
        info = await bot.get_webhook_info()
        logger.info(f"Health check успешен: webhook_url={info.url}, pending_updates={info.pending_update_count}")
        return {
            "status": "ok",
            "bot_ready": True,
            "webhook_url": info.url,
            "pending_updates": info.pending_update_count,
        }
    except Exception as e:
        logger.error(f"Ошибка в health check: {e}", exc_info=True)
        return {"status": "error", "bot_ready": False, "error": str(e)}

@app.post("/webhook")
async def webhook(request: Request):
    logger.debug(f"Получен webhook запрос: headers={request.headers}")
    try:
        body = await request.body()
        logger.debug(f"Тело запроса: {body}")
        if not body:
            logger.error("Пустое тело запроса")
            return {"status": "error", "message": "Empty request body"}
        update = await request.json()
        logger.debug(f"Получен update: {update}")
        update_id = update.get("update_id")
        from utils import processed_updates
        if update_id in processed_updates:
            logger.info(f"Повторный update_id: {update_id}, пропущен")
            return {"status": "ok"}
        processed_updates.add(update_id)
        await dp.feed_raw_update(bot, update)
        logger.debug("Update успешно обработан")
        return {"status": "ok"}
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON: {e}")
        return {"status": "error", "message": f"JSON decode error: {str(e)}"}
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    logger.info("Запуск приложения через uvicorn")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), workers=1)