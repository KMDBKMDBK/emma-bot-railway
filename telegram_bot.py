import os
import logging
import json
import base64
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from firebase_admin import credentials, firestore, initialize_app
from openai import AsyncOpenAI
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()

# Инициализация OpenRouter
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

# Инициализация Firebase
firebase_credentials = os.getenv("FIREBASE_CREDENTIALS_JSON")
if firebase_credentials:
    try:
        cred_json = base64.b64decode(firebase_credentials).decode()
        cred = credentials.Certificate(json.loads(cred_json))
        initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase инициализирован")
    except Exception as e:
        db = None
        logging.warning(f"Firebase не инициализирован: {e}")
else:
    db = None
    logging.warning("FIREBASE_CREDENTIALS_JSON не указан")

# Переменные окружения
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-120b:free")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
MINIAPP_URL = os.getenv("MINIAPP_URL")
MINIAPP_BUTTON_TEXT = os.getenv("MINIAPP_BUTTON_TEXT", "🎀Просмотр🎀")
NUM_SEARCH_RESULTS = int(os.getenv("NUM_SEARCH_RESULTS", 7))
PAY_IMAGE_PATH = os.getenv("PAY_IMAGE_PATH")
START_IMAGE_PATH = os.getenv("START_IMAGE_PATH")
FEEDBACK_CHAT_ID = os.getenv("FEEDBACK_CHAT_ID")

# Установка команд бота
async def set_bot_commands():
    await bot.set_my_commands([
        {"command": "/start", "description": "Запустить бота"},
        {"command": "/pay", "description": "Оформить подписку"},
        {"command": "/feedback", "description": "Оставить отзыв"},
        {"command": "/reply", "description": "Ответить на отзыв (админ)"}
    ])

# Обработчик /start
@dp.message(CommandStart())
async def start_command(message: Message):
    user_id = message.from_user.id
    start_text = (
        "Привет! Я Эмма, твой умный помощник! 😊\n"
        "Я могу отвечать на вопросы, искать информацию и многое другое.\n"
        "Попробуй спросить меня что-нибудь или используй команды:\n"
        "💸 /pay — оформить подписку\n"
        "📝 /feedback — оставить отзыв"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=MINIAPP_BUTTON_TEXT, web_app={"url": MINIAPP_URL})
    ]])
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=START_IMAGE_PATH,
        caption=start_text,
        reply_markup=reply_markup
    )
    if db:
        db.collection("users").document(str(user_id)).set({
            "username": message.from_user.username or "unknown",
            "first_seen": firestore.SERVER_TIMESTAMP
        })

# Обработчик /pay
@dp.message(Command("pay"))
async def pay_command(message: Message):
    pay_text = (
        "💸 Подписка на Эмму даёт доступ к эксклюзивным функциям!\n"
        "Стоимость: 100 Telegram Stars в месяц.\n"
        "Нажми ниже, чтобы оплатить!"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Оплатить", pay=True)
    ]])
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=PAY_IMAGE_PATH,
        caption=pay_text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

# Обработчик /feedback
@dp.message(Command("feedback"))
async def feedback_command(message: Message):
    feedback_text = message.text.replace("/feedback", "").strip()
    if not feedback_text:
        await message.answer("Пожалуйста, напиши отзыв после команды /feedback")
        return
    user_id = message.from_user.id
    if db:
        feedback_ref = db.collection("messages").document()
        feedback_ref.set({
            "user_id": user_id,
            "username": message.from_user.username or "unknown",
            "text": feedback_text,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "replied": False
        })
        await bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=f"Новый отзыв от @{message.from_user.username or user_id}:\n{feedback_text}"
        )
        await message.answer("Спасибо за отзыв! 😊")
    else:
        await message.answer("Ошибка: база данных недоступна.")

# Обработчик /reply (админ)
@dp.message(Command("reply"))
async def reply_command(message: Message):
    if str(message.from_user.id) != FEEDBACK_CHAT_ID:
        await message.answer("Эта команда только для админов.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /reply <user_id> <ответ>")
        return
    user_id, reply_text = parts[1], parts[2]
    if db:
        feedback_ref = db.collection("messages").where("user_id", "==", int(user_id)).where("replied", "==", False).get()
        for doc in feedback_ref:
            doc.reference.update({"replied": True})
        await bot.send_message(user_id, f"Ответ на ваш отзыв: {reply_text}")
        await message.answer("Ответ отправлен.")

# Обработчик текстовых сообщений (AI + Google Custom Search)
@dp.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if db:
        user_doc = db.collection("users").document(str(user_id)).get().to_dict()
        premium = user_doc.get("premium", False)
        expiry = user_doc.get("expiry")
        if expiry and datetime.now() > expiry:
            premium = False
            db.collection("users").document(str(user_id)).update({"premium": False})
    else:
        premium = False
    if not premium and len(text) > 100:
        await message.answer("Для длинных запросов нужна подписка! Используй /pay")
        return
    # Google Custom Search
    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        result = service.cse().list(q=text, cx=GOOGLE_CSE_ID, num=NUM_SEARCH_RESULTS).execute()
        search_results = [item["snippet"] for item in result.get("items", [])]
    except Exception as e:
        search_results = []
        logging.warning(f"Google Search ошибка: {e}")
    context = "\n".join(search_results)
    response = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "Ты умный помощник Эмма. Отвечай на русском, кратко и по делу."},
            {"role": "user", "content": f"Запрос: {text}\nКонтекст: {context}"}
        ]
    )
    answer = response.choices[0].message.content
    await message.answer(answer)
    if db:
        db.collection("messages").document().set({
            "user_id": user_id,
            "text": text,
            "response": answer,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

# Webhook настройка
async def on_startup(app):
    webhook_url = f"https://{os.getenv('HEROKU_APP_NAME', 'emma-bot-2025')}.herokuapp.com/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook установлен на {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Webhook удалён")

# Основная функция
async def main():
    await set_bot_commands()
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())