import os
from dotenv import load_dotenv

load_dotenv()

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FEEDBACK_CHAT_ID = os.getenv("FEEDBACK_CHAT_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
MINIAPP_URL = os.getenv("MINIAPP_URL", "")
MINIAPP_BUTTON_TEXT = os.getenv("MINIAPP_BUTTON_TEXT", "Открыть мини-приложение")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")
RENDER_URL = os.getenv("RENDER_URL")
PORT = int(os.getenv("PORT", "10000"))
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH")
PAY_IMAGE_PATH = os.getenv("PAY_IMAGE_PATH")
MODEL_NAME = os.getenv("MODEL_NAME")
NUM_SEARCH_RESULTS = int(os.getenv("NUM_SEARCH_RESULTS", "10"))