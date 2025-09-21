import os
from dotenv import load_dotenv
import logging

load_dotenv()
logging.info("Переменные окружения загружены")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FEEDBACK_CHAT_ID = os.getenv("FEEDBACK_CHAT_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-120b:free")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
MINIAPP_URL = os.getenv("MINIAPP_URL")
MINIAPP_BUTTON_TEXT = os.getenv("MINIAPP_BUTTON_TEXT", "🎀Просмотр🎀")
NUM_SEARCH_RESULTS = int(os.getenv("NUM_SEARCH_RESULTS", 7))
PAY_IMAGE_PATH = os.getenv("PAY_IMAGE_PATH", "./images/pay_image.jpg")
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", "./images/start_image.jpg")

if not TELEGRAM_TOKEN:
    logging.error("TELEGRAM_TOKEN не указан в .env")
    exit(1)
logging.info("Все переменные окружения проверены")