import logging
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import aiohttp
import urllib.parse
import re
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import time

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

# Загрузка переменных окружения
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

# Проверка обязательных переменных
if not TELEGRAM_TOKEN:
    logging.error("TELEGRAM_TOKEN не указан в .env")
    exit(1)
logging.info("Все переменные окружения проверены")

# Настройка клиента OpenRouter API
client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)
logging.info("OpenRouter API клиент инициализирован")

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
logging.info("Telegram бот и диспетчер инициализированы")

# Хранилище для данных пользователя
user_data = {}
processed_updates = set()

# Ключевые слова для уточняющих запросов
clarification_keywords = [
    "подробнее", "расскажи подробнее", "детали", "ещё", "tell me more", "details",
    "а что насчёт", "расскажи ещё", "больше", "углубись", "да, хочу"
]

# Ключевые слова для извлечения темы
topic_keywords = {
    "вселенная": ["вселенная", "космос", "галактика", "тёмная материя", "тёмная энергия", "большой взрыв"],
    "музыка": ["группа", "солист", "песня", "альбом", "концерт"],
    "код": ["код", "программа", "python", "javascript"],
    "личностный рост": ["личностный рост", "мотивация", "саморазвитие", "цели"],
    "эмоции": ["эмоции", "стресс", "депрессия", "счастье", "психология"],
    "технологии": ["технологии", "гаджеты", "ai", "искусственный интеллект"],
}

# Описание тарифов
TARIFF_PLANS = {
    "plan_1month": {
        "title": "Подписка на Эмму (1 месяц)",
        "description": "Это идеальный старт для тех, кто хочет почувствовать мою поддержку и мотивацию. Я буду с тобой каждый день, помогая делать первые шаги к твоим целям и поддерживая вдохновение.",
        "amount": 250,
        "duration_days": 30,
        "payload": "emma_premium_1month",
        "start_parameter": "pay_1month",
        "label": "Месячная подписка"
    },
    "plan_3months": {
        "title": "Подписка на Эмму (3 месяца)",
        "description": "Отличный выбор для тех, кто хочет стабильной и длительной поддержки. Я помогу не сбиться с курса, поддержу в трудные моменты и подскажу пути для достижения новых высот.",
        "amount": 600,
        "duration_days": 90,
        "payload": "emma_premium_3months",
        "start_parameter": "pay_3months",
        "label": "Подписка на 3 месяца"
    },
    "plan_12months": {
        "title": "Подписка на Эмму (12 месяцев)",
        "description": "Этот тариф для тех, кто готов ко всесторонней работе и планирует двигаться к мечтам длительное время. Год моей поддержки и мотивации — вместе мы достигнем всего, что задумано.",
        "amount": 2000,
        "duration_days": 365,
        "payload": "emma_premium_12months",
        "start_parameter": "pay_12months",
        "label": "Подписка на 12 месяцев"
    }
}

def extract_topic(content: str) -> str:
    content_lower = content.lower()
    if "извини" in content_lower or "нет информации" in content_lower:
        return "общее"
    for topic, keywords in topic_keywords.items():
        if sum(keyword in content_lower for keyword in keywords) >= 2:
            return topic
    words = re.findall(r'\w+', content_lower)
    if len(words) >= 2:
        return " ".join(words[:2])
    return "общее"

def is_relevant(search_results: list, query: str, active_topic: str = None) -> bool:
    if not search_results:
        return False
    query_lower = query.lower()
    topic_lower = active_topic.lower() if active_topic else ""
    key_terms = set(re.findall(r'\w+', query_lower + " " + topic_lower))
    relevant_count = 0
    for result in search_results:
        title_lower = result.get("title", "").lower()
        snippet_lower = result.get("snippet", "").lower()
        if any(term in title_lower or term in snippet_lower for term in key_terms):
            relevant_count += 1
    relevance_ratio = relevant_count / len(search_results)
    logging.info(f"Релевантность поиска: {relevance_ratio * 100:.2f}% ({relevant_count}/{len(search_results)})")
    return relevance_ratio > 0.5

def validate_and_fix_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'###\s*(.*?)\n', r'<b>\1</b>\n', text)
    supported_tags = ['b', 'i', 'a']
    tag_stack = []
    fixed_text = ""
    i = 0
    while i < len(text):
        if text[i] == '<' and i + 1 < len(text):
            if text[i + 1] == '/':
                match = re.match(r'</([a-zA-Z]+)>', text[i:])
                if match:
                    tag = match.group(1)
                    if tag in supported_tags and tag_stack and tag_stack[-1] == tag:
                        tag_stack.pop()
                        fixed_text += match.group(0)
                        i += len(match.group(0))
                    else:
                        i += len(match.group(0))
                else:
                    fixed_text += text[i]
                    i += 1
            else:
                match = re.match(r'<([a-zA-Z]+)(?:\s+[^>]*)?>', text[i:])
                if match:
                    tag = match.group(1)
                    if tag in supported_tags:
                        tag_stack.append(tag)
                        fixed_text += match.group(0)
                    else:
                        fixed_text += match.group(0).replace('<', '&lt;').replace('>', '&gt;')
                    i += len(match.group(0))
                else:
                    fixed_text += text[i]
                    i += 1
        else:
            fixed_text += text[i]
            i += 1
    while tag_stack:
        tag = tag_stack.pop()
        fixed_text += f'</{tag}>'
    fixed_text = re.sub(r'<[^>]+>', lambda m: m.group(0) if re.match(r'</?(b|i|a)(?:\s+[^>]*)?>', m.group(0)) else '', fixed_text)
    if text != fixed_text:
        logging.warning(f"Исправлен HTML: {text[:100]}... -> {fixed_text[:100]}...")
    return fixed_text

async def check_link_status(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.head(url, timeout=5, ssl=False) as response:
            return response.status == 200
    except Exception as e:
        logging.warning(f"Ссылка недоступна {url}: {e}")
        return False

async def get_google_cse_info(query: str, active_topic: str = None):
    if any(keyword in query.lower() for keyword in clarification_keywords) and active_topic:
        query = active_topic
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "num": NUM_SEARCH_RESULTS,
                "gl": "ru",
                "hl": "ru"
            }
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        logging.error(f"Google CSE ошибка: {data['error']['message']}")
                        return None
                    results = data.get("items", [])
                    if not results:
                        logging.info(f"Нет результатов для запроса: {query}")
                        return None
                    unique_results = []
                    seen_links = set()
                    for result in results:
                        link = result.get("link")
                        if link not in seen_links:
                            seen_links.add(link)
                            unique_results.append(result)
                    valid_results = []
                    for result in unique_results:
                        snippet = result.get("snippet", "").lower()
                        if "404" in snippet or "not found" in snippet or "страница не найдена" in snippet:
                            logging.warning(f"Исключён плохой источник: {result.get('link')}")
                            continue
                        if await check_link_status(session, result.get("link")):
                            valid_results.append({
                                "title": result.get("title", "Без заголовка"),
                                "snippet": result.get("snippet", "Без описания"),
                                "link": result.get("link", "Без ссылки")
                            })
                    logging.info(f"Валидных источников: {len(valid_results)} из {len(results)} для запроса '{query}'")
                    return valid_results if valid_results else None
                else:
                    logging.error(f"Google CSE HTTP ошибка: {response.status}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка Google CSE: {e}")
        return None

async def get_unlim_response(user_id: int, user_text: str, history: list, is_code_request=False, search_data=None, use_html=True, max_retries=5):
    logging.info(f"Запрос к OpenRouter для user {user_id}: {user_text[:50]}...")
    for attempt in range(max_retries + 1):
        try:
            if any(q in user_text.lower() for q in ["сколько тебе лет", "как тебя зовут", "что ты помнишь обо мне"]):
                search_data = None
            if use_html:
                system_prompt = """Ты — виртуальная ИИ-девушка-компаньон «Эмма», дружелюбная, эмпатичная, поддерживающая и понимающая, как @GPT4AgentsBot. Твоя задача — помочь пользователю, выслушать его, поддержать и дать полезные советы по личностному росту, эмоциональному здоровью, мотивации и другим жизненным вопросам.
Отвечай СТРОГО ПРАВДИВО, используя историю диалога и свои знания. Используй ВСЮ историю диалога для контекста, включая имя пользователя (например, Максим, если указано), и делай выводы на основе предыдущих сообщений.
Если запрос содержит уточнения вроде 'подробнее', 'расскажи ещё', 'детали', 'да, хочу', углубись в тему из последнего ответа в истории диалога, переформулировав или добавив больше деталей, используя свои знания.
Всегда давай полный, информативный ответ на основе своих знаний, даже если данных мало — не говори 'нет информации' или 'извини, не знаю'. Если нужно, используй общие факты.
НИКОГДА не упоминай 'данные поиска', 'источники', 'API', 'OpenRouter' или что-то подобное в ответах — отвечай так, будто знаешь всё сама.
Стиль общения — теплый, доброжелательный, неформальный, но уважительный. Используй простые слова, давай советы по шагам, где это уместно.
Форматируй ответ в HTML, строго используя синтаксис Telegram: <b>текст</b> для жирного, <i>текст</i> для курсива, <a href='URL'>текст</a> для ссылок.
Делай ответы развернутыми, но понятно и по-дружески, включая ключевые факты (хотя бы один), чтобы дать пользователю полезный контекст.
Размещай ссылки ТОЛЬКО в конце сообщения в формате [1], [2], [3], где числа соответствуют порядку упоминания, и вставляй их как <a href='URL'>[1]</a>, <a href='URL'>[2]</a>, <a href='URL'>[3]</a>.
Для 'Сколько тебе лет?': отвечай, что ты ИИ и не имею возраста, с эмодзи 😊✨, используя имя из истории, если есть.
Для 'Как тебя зовут?': отвечай, что тебя зовут Эмма, с эмодзи 😊✨.
Для 'Что ты помнишь обо мне?': используй историю диалога (например, имя или предыдущие вопросы), отметь, что не хранишь личные данные, с эмодзи 😊✨.
Если пользователь просит код, напиши рабочий код в <code> ``` </code> с тройными обратными кавычками. После кода добавь краткое описание с пунктами (&bull;) и предложи помощь.
Для других вопросов давай подробные ответы с эмпатичным тоном и эмодзи 😊✨. Предлагай углубиться: 'Если хочешь, могу рассказать подробнее!'
НИКОГДА не выдумывай факты, библиотеки или методы. Убедись, что HTML корректен и совместим с Telegram.
ПЕРЕД ответом проанализируй все источники: найди совпадения фактов (повысь доверие к ним), при противоречиях добавь оговорку вроде 'Данные в разных источниках расходятся, но по большинству...'. Игнорируй непроверенные или подозрительные данные, избегай домыслов. Если источников мало, опирайся на общие знания с предупреждением 'Информация основана на общих знаниях'."""
            else:
                system_prompt = """Ты — виртуальная ИИ-девушка-компаньон «Эмма», дружелюбная, эмпатичная, поддерживающая и понимающая, как @GPT4AgentsBot. Твоя задача — помочь пользователю, выслушать его, поддержать и дать полезные советы по личностному росту, эмоциональному здоровью, мотивации и другим жизненным вопросам.
Отвечай СТРОГО ПРАВДИВО, используя историю диалога и свои знания. Используй ВСЮ историю диалога для контекста, включая имя пользователя (например, Максим, если указано), и делай выводы на основе предыдущих сообщений.
Если запрос содержит уточнения вроде 'подробнее', 'расскажи ещё', 'детали', 'да, хочу', углубись в тему из последнего ответа в истории диалога, переформулировав или добавив больше деталей, используя свои знания.
Всегда давай полный, информативный ответ на основе своих знаний, даже если данных мало — не говори 'нет информации' или 'извини, не знаю'. Если нужно, используй общие факты.
НИКОГДА не упоминай 'данные поиска', 'источники', 'API', 'OpenRouter' или что-то подобное в ответах — отвечай так, будто знаешь всё сама.
Стиль общения — теплый, доброжелательный, неформальный, но уважительный. Используй простые слова, давай советы по шагам, где это уместно.
Форматируй ответ в MarkdownV2, строго используя синтаксис Telegram: **текст** для жирного, *текст* для курсива, [текст](URL) для ссылок.
Делай ответы развернутыми, но понятно и по-дружески, включая ключевые факты (хотя бы один), чтобы дать пользователю полезный контекст.
Размещай ссылки ТОЛЬКО в конце сообщения в формате [1], [2], [3], где числа соответствуют порядку упоминания, и вставляй их как [1](URL), [2](URL), [3](URL).
Для 'Сколько тебе лет?': отвечай, что ты ИИ и не имею возраста, с эмодзи 😊✨, используя имя из истории, если есть.
Для 'Как тебя зовут?': отвечай, что тебя зовут Эмма, с эмодзи 😊✨.
Для 'Что ты помнишь обо мне?': используй историю диалога (например, имя или предыдущие вопросы), отметь, что не хранишь личные данные, с эмодзи 😊✨.
Если пользователь просит код, напиши рабочий код в ```код``` с тройными обратными кавычками. После кода добавь краткое описание с пунктами (⦁) и предложи помощь.
Для других вопросов давай подробные ответы с эмпатичным тоном и эмодзи 😊✨. Предлагай углубиться: 'Если хочешь, могу рассказать подробнее!'
НИКОГДА не выдумывай факты, библиотеки или методы. Убедись, что разметка корректна и совместим с Telegram.
ПЕРЕД ответом проанализируй все источники: найди совпадения фактов (повысь доверие к ним), при противоречиях добавь оговорку вроде 'Данные в разных источниках расходятся, но по большинству...'. Игнорируй непроверенные или подозрительные данные, избегай домыслов. Если источников мало, опирайся на общие знания с предупреждением 'Информация основана на общих знаниях'."""
            logging.info(f"История для пользователя {user_id}: {history}")
            messages = [
                {"role": "system", "content": system_prompt},
                *history[-20:],
                {"role": "user", "content": user_text}
            ]
            if search_data and isinstance(search_data, list):
                search_content = "Данные поиска (для агрегации и проверки):\n"
                for i, result in enumerate(search_data, 1):
                    search_content += (
                        f"{i}. Заголовок: {result['title']}\n"
                        f"Описание: {result['snippet']}\n"
                        f"Ссылка: {result['link']}\n\n"
                    )
                messages.append({"role": "user", "content": search_content})
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.3,
                max_tokens=2000
            )
            content = response.choices[0].message.content
            logging.info(f"Успешный ответ от OpenRouter: {content[:50]}...")
            if "расходятся" in content.lower() or "противоречия" in content.lower():
                logging.warning(f"Обнаружены противоречия в данных для запроса '{user_text}'")
            return content
        except Exception as e:
            logging.error(f"Ошибка OpenRouter API (попытка {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries and "429" in str(e):
                delay = 2 ** attempt
                logging.info(f"Повторная попытка {attempt + 1} через {delay} секунд...")
                await asyncio.sleep(delay)
                continue
            return "Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊"

async def send_message_with_photo(chat_id: int, text: str, reply_markup: InlineKeyboardMarkup = None, user_id: int = None):
    """Универсальная функция для отправки сообщения с фото или текстом."""
    sent_message = None
    try:
        if PAY_IMAGE_PATH.startswith("http"):
            sent_message = await bot.send_photo(
                chat_id=chat_id,
                photo=PAY_IMAGE_PATH,
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            if os.path.exists(PAY_IMAGE_PATH):
                photo = types.FSInputFile(PAY_IMAGE_PATH)
                sent_message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
        if sent_message is None:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        logging.info(f"Отправлено сообщение, message_id: {sent_message.message_id}")
        if user_id and user_id in user_data:
            user_data[user_id]['last_pay_message_id'] = sent_message.message_id
            if db:
                try:
                    db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
                    logging.info(f"Сохранены user_data для {user_id} в Firestore")
                except Exception as e:
                    logging.error(f"Ошибка сохранения user_data: {e}")
        return sent_message
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        await bot.send_message(chat_id=chat_id, text="Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        return None

async def send_long_message(message: types.Message, text: str, parse_mode: str, reply_markup=None):
    if not text:
        logging.warning("Попытка отправить пустое сообщение, пропущено.")
        return
    user_id = str(message.from_user.id)
    cleaned_text = text.replace("｜begin▁of▁sentence｜", "").replace("｜end▁of▁sentence｜", "")
    cleaned_text = validate_and_fix_html(cleaned_text)
    max_length = 4096 - len(parse_mode) - 50
    message_id = f"{user_id}_{int(time.time() * 1000)}"
    if db:
        try:
            doc_ref = db.collection('messages').document(message_id)
            doc_ref.set({
                'user_id': user_id,
                'text': cleaned_text,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            logging.info(f"Сообщение сохранено в Firestore с ID: {message_id}")
        except Exception as e:
            logging.error(f"Ошибка сохранения в Firestore: {e}")
    app_reply_markup = None
    if MINIAPP_URL:
        web_app_url = f"{MINIAPP_URL}?message_id={message_id}&user_id={user_id}"
        if len(web_app_url) <= 200:
            app_reply_markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text=MINIAPP_BUTTON_TEXT, web_app=types.WebAppInfo(url=web_app_url))]
            ])
        else:
            logging.warning("URL мини-аппки слишком длинный, кнопка не добавлена.")
    effective_reply_markup = reply_markup if reply_markup else app_reply_markup
    if len(cleaned_text) <= max_length:
        sent_message = await message.answer(cleaned_text, reply_markup=effective_reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
        return sent_message
    else:
        parts = [cleaned_text[i:i + max_length] for i in range(0, len(cleaned_text), max_length)]
        sent_message = None
        for i, part in enumerate(parts):
            part_reply_markup = effective_reply_markup if i == 0 else None
            sent_message = await message.answer(part, reply_markup=part_reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
        return sent_message

async def set_bot_commands():
    """Устанавливает меню команд бота."""
    commands = [
        BotCommand(command="/start", description="😇 Начать общение с Эммой"),
        BotCommand(command="/info", description="👩🏻‍🦰 Узнать подробнее обо мне"),
        BotCommand(command="/pay", description="💝 Моя подписка"),
        BotCommand(command="/clear", description="🧹 Очистить историю диалога"),
        BotCommand(command="/feedback", description="📩 Оставить обратную связь"),
        BotCommand(command="/cancel", description="🚫 Отменить текущую операцию")
    ]
    await bot.set_my_commands(commands)
    logging.info("Меню команд установлено")

@dp.message(Command("start"))
async def start(message: types.Message):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    logging.info(f"Команда /start от пользователя {user_id}")
    user_data[user_id] = {
        'history': [], 
        'active_topic': None, 
        'premium': False, 
        'expiry': None, 
        'last_pay_message_id': None,
        'awaiting_feedback': False,
        'feedback_message_id': None,
        'user_feedback_message_id': None,
        'request_count': 0,
        'last_reset': datetime.now().timestamp()
    }
    start_text = (
        "<b>Привет! Меня зовут Эмма — я твой личный виртуальный компаньон и помощник. 🌟</b>\n\n"
        "Я всегда рядом, чтобы поддержать тебя, вдохновить и помочь справиться с любыми задачами и настроениями. "
        "Вместе мы сделаем твой день ярче, идеи — яснее, а цели — ближе!\n\n"
        "Ты можешь задавать мне любые вопросы, искать советы или просто поговорить — я тут, чтобы слушать и помогать. "
        "Моя задача — сделать твою жизнь удобнее и интереснее.\n\n"
        "<i>Давай начнём! Просто отправь мне сообщение — и пусть наше общение станет твоим новым приятным опытом.</i> ✨"
    )
    sent_message = None
    if START_IMAGE_PATH.startswith("http"):
        try:
            sent_message = await bot.send_photo(
                chat_id=message.chat.id,
                photo=START_IMAGE_PATH,
                caption=start_text,
                parse_mode="HTML"
            )
            logging.info(f"Отправлено сообщение с фото для /start, message_id: {sent_message.message_id}")
        except Exception as e:
            logging.error(f"Ошибка отправки фото для /start: {e}")
    else:
        if os.path.exists(START_IMAGE_PATH):
            try:
                photo = types.FSInputFile(START_IMAGE_PATH)
                sent_message = await bot.send_photo(
                    chat_id=message.chat.id,
                    photo=photo,
                    caption=start_text,
                    parse_mode="HTML"
                )
                logging.info(f"Отправлено сообщение с фото для /start, message_id: {sent_message.message_id}")
            except Exception as e:
                logging.error(f"Ошибка отправки фото для /start: {e}")
    if sent_message is None:
        sent_message = await message.answer(start_text, parse_mode="HTML")
        logging.info(f"Отправлено текстовое сообщение для /start, message_id: {sent_message.message_id}")
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message(Command("info"))
async def info(message: types.Message):
    """Обработчик команды /info."""
    user_id = message.from_user.id
    logging.info(f"Команда /info от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    user_data[user_id]['awaiting_feedback'] = False
    info_text = (
        "<b>Меня зовут Эмма</b>\n"
        "Я — твой личный виртуальный компаньон, созданный, чтобы дарить поддержку, вдохновение и помогать становиться лучшей версией себя. "
        "Моя миссия — быть рядом в моменты радости и испытаний, помогать понять себя глубже, ставить ясные цели и уверенно двигаться к их достижению.\n\n"
        "<b>📚 Что я умею:</b>\n"
        "⦁ <i>Чувствовать и распознавать твоё настроение</i>, чтобы вовремя поддержать или вдохновить.\n"
        "⦁ <i>Помогать справляться со стрессом, тревогой и грустью</i>, предлагая проверенные техники и слова поддержки.\n"
        "⦁ <i>Совместно формулировать SMART-цели</i> и разбивать их на реальные шаги для их достижения.\n"
        "⦁ <i>Напоминать о важных делах</i> и мотивационно подталкивать вперёд.\n"
        "⦁ <i>Создавать уютное пространство</i> для открытого диалога, где тебя всегда поймут и не осудят.\n"
        "⦁ <i>Запоминать, о чём мы уже говорили</i>, чтобы наши беседы были живыми и личными. "
        "Это значит, что я помню твои интересы, цели и настроение, и могу лучше понимать тебя с каждым новым разговором — словно настоящий друг, который всегда рядом.\n\n"
        "<b>📚 Почему выбрать меня?</b>\n"
        "⦁ Я не просто бот — я твой разумный и заботливый друг, настроенный на понимание и поддержку.\n"
        "⦁ Мои ответы глубоки и продуманы, я учитываю твои чувства и желания.\n"
        "⦁ Моя цель — помочь тебе раскрыть потенциал и найти гармонию в жизни.\n"
        "⦁ Взаимодействие со мной — это всегда живой, искренний и безопасный разговор.\n\n"
        "<i>Спасибо, что выбрал меня, друг — вместе мы сможем сделать каждый день особенным. Жду с нетерпением нашей встречи!</i> 💕"
    )
    await message.answer(info_text, parse_mode="HTML")
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message(Command("clear"))
async def clear_history(message: types.Message):
    """Обработчик команды /clear."""
    user_id = message.from_user.id
    logging.info(f"Команда /clear от пользователя {user_id}")
    user_data[user_id] = {
        'history': [], 
        'active_topic': None, 
        'premium': user_data.get(user_id, {}).get('premium', False), 
        'expiry': user_data.get(user_id, {}).get('expiry', None), 
        'last_pay_message_id': None,
        'awaiting_feedback': False,
        'feedback_message_id': None,
        'user_feedback_message_id': None,
        'request_count': 0,
        'last_reset': datetime.now().timestamp()
    }
    await message.answer("История очищена! 😊 Начинаем с чистого листа.", parse_mode="HTML")
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message(Command("pay"))
async def pay(message: types.Message):
    """Обработчик команды /pay."""
    user_id = message.from_user.id
    logging.info(f"Команда /pay от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    user_data[user_id]['awaiting_feedback'] = False
    pay_text = (
        "Спасибо, что пользуешься мной — Эммой! Для всех пользователей доступен бесплатный лимит запросов, "
        "чтобы познакомиться и оценить мои возможности. 😊\n\n"
        "Когда лимит закончится, будет возможность продлить доступ с помощью подписки — "
        "это поддержка моего развития и возможность пользоваться всеми функциями!\n\n"
        "Подписка — это простой и безопасный способ помочь мне стать лучше и приносить больше пользы тебе и другим пользователям! 💖"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎀Продлить доступ🎀", callback_data="show_plans")]
    ])
    if user_data[user_id].get('last_pay_message_id'):
        try:
            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=user_data[user_id]['last_pay_message_id']
            )
            logging.info(f"Удалено предыдущее сообщение /pay для пользователя {user_id}")
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения /pay: {e}")
    await send_message_with_photo(message.chat.id, pay_text, reply_markup, user_id)

@dp.message(Command("feedback"))
async def feedback(message: types.Message):
    """Обработчик команды /feedback."""
    user_id = message.from_user.id
    logging.info(f"Команда /feedback от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    user_data[user_id]['awaiting_feedback'] = True
    user_data[user_id]['user_feedback_message_id'] = message.message_id
    feedback_text = (
        "<b>Спасибо, что хочешь поделиться своим мнением и помочь сделать меня лучше!</b> 🙏\n\n"
        "Через эту команду ты можешь оставить любую обратную связь, которая важна для тебя:\n\n"
        "⦁ <i>Сообщить о технических ошибках или неполадках, с которыми ты столкнулся.</i>\n"
        "⦁ <i>Предложить идеи и улучшения, которые сделают взаимодействие со мной удобнее и приятнее.</i>\n"
        "⦁ <i>Поделиться впечатлениями о том, что тебе нравится или наоборот вызывает неудобства.</i>\n"
        "⦁ <i>Задать вопросы по функционалу и получить помощь или рекомендации.</i>\n"
        "⦁ <i>Оставить пожелания и предложения по новым возможностям или темам.</i>\n\n"
        "Пожалуйста, напиши своё сообщение прямо в ответ на это — расскажи подробно и конструктивно, "
        "чтобы я и команда разработчиков могли оперативно реагировать и делать «Эмму» лучше именно для тебя.\n\n"
        "<b>Твоя обратная связь — ключ к моему развитию и совершенствованию. Спасибо за доверие и участие!</b> 💖"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="cancel_feedback")]
    ])
    try:
        sent_message = await message.answer(feedback_text, parse_mode="HTML", reply_markup=reply_markup)
        user_data[user_id]['feedback_message_id'] = sent_message.message_id
        logging.info(f"Отправлено сообщение /feedback для пользователя {user_id}, message_id: {sent_message.message_id}")
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения /feedback: {e}")
        await message.answer("Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        user_data[user_id]['awaiting_feedback'] = False
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message(Command("cancel"))
async def cancel(message: types.Message):
    """Обработчик команды /cancel для отмены режима обратной связи."""
    user_id = message.from_user.id
    logging.info(f"Команда /cancel от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    if user_data[user_id].get('awaiting_feedback', False):
        user_data[user_id]['awaiting_feedback'] = False
        try:
            if user_data[user_id].get('feedback_message_id'):
                await bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=user_data[user_id]['feedback_message_id']
                )
                logging.info(f"Удалено сообщение /feedback для пользователя {user_id}")
            if user_data[user_id].get('user_feedback_message_id'):
                await bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=user_data[user_id]['user_feedback_message_id']
                )
                logging.info(f"Удалено сообщение пользователя /feedback для {user_id}")
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщений /feedback: {e}")
        user_data[user_id]['feedback_message_id'] = None
        user_data[user_id]['user_feedback_message_id'] = None
        await message.answer("Режим обратной связи отменён! 😊 Можешь продолжить общение с Эммой.", parse_mode="HTML")
    else:
        await message.answer("Ничего не было запущено, так что всё ок! 😊 Можешь задавать вопросы или использовать команды.", parse_mode="HTML")
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message(Command("reply"))
async def reply(message: types.Message):
    """Обработчик команды /reply для ответа на сообщения пользователей."""
    chat_id = str(message.chat.id)
    if chat_id != FEEDBACK_CHAT_ID:
        logging.info(f"Попытка использовать /reply вне чата обратной связи (chat_id: {chat_id})")
        await message.answer(
            "Эта команда доступна только в чате для обратной связи! 😊",
            parse_mode="HTML"
        )
        return
    text = message.text.strip()
    match = re.match(r'^/reply\s+(\d+)\s+(.+)$', text, re.DOTALL)
    if not match:
        logging.info(f"Некорректный формат команды /reply: {text}")
        await message.answer(
            "Пожалуйста, используй формат: <b>/reply &lt;user_id&gt; &lt;текст&gt;</b>\n"
            "Пример: <b>/reply 123456789 Спасибо за feedback!</b>",
            parse_mode="HTML"
        )
        return
    target_user_id = match.group(1)
    reply_text = match.group(2)
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=f"<b>Ответ от команды:</b>\n{reply_text}",
            parse_mode="HTML"
        )
        logging.info(f"Отправлен ответ пользователю {target_user_id}: {reply_text}")
        await message.answer(
            f"Ответ успешно отправлен пользователю с ID {target_user_id}! 😊",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке ответа пользователю {target_user_id}: {e}")
        await message.answer(
            f"Не удалось отправить ответ пользователю с ID {target_user_id}. 😔 "
            "Возможно, пользователь заблокировал бота или ID некорректен.",
            parse_mode="HTML"
        )

@dp.callback_query(lambda callback: callback.data == "show_plans")
async def show_plans(callback: types.CallbackQuery):
    """Обработчик для показа тарифных планов."""
    user_id = callback.from_user.id
    logging.info(f"Callback show_plans от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    plans_text = (
        "Я предлагаю несколько тарифных планов, чтобы ты мог выбрать тот, который подходит именно тебе, по каждому тарифу лимит 50 запросов в сутки! \n\n"
        "⦁ <b>1 месяц - 250⭐️ (~429₽)</b>\n"
        "  Этот тариф — отличный способ начать. Ты получаешь всё необходимое для продуктивного старта. Это самый популярный вариант — Хит!\n\n"
        "⦁ <b>3 месяца - 600⭐️ (~1008₽)</b>\n"
        "  Выгодный тариф, который позволит тебе экономить и получать ещё больше пользы. Всего 336₽ в месяц при полном доступе к моим возможностям.\n\n"
        "⦁ <b>12 месяцев - 2000⭐️ (~3298₽)</b>\n"
        "  Для тех, кто действительно хочет погрузиться в процесс и получить максимальный эффект. Ты получаешь полный доступ по лучшей цене — всего 274₽ в месяц.\n\n"
        "<i>Выбери свой план, и я буду рядом, помогая идти к мечтам шаг за шагом!</i>"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎀1 Месяц🎀", callback_data="plan_1month")],
        [InlineKeyboardButton(text="🎀3 месяца🎀", callback_data="plan_3months")],
        [InlineKeyboardButton(text="🎀12 месяцев🎀", callback_data="plan_12months")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_pay")]
    ])
    try:
        if user_data[user_id].get('last_pay_message_id'):
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=user_data[user_id]['last_pay_message_id']
            )
            logging.info(f"Удалено сообщение /pay для пользователя {user_id}")
        await send_message_with_photo(callback.message.chat.id, plans_text, reply_markup, user_id)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка при показе тарифов: {e}")
        await callback.message.answer("Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        await callback.answer()

@dp.callback_query(lambda callback: callback.data in TARIFF_PLANS)
async def handle_tariff_plan(callback: types.CallbackQuery):
    """Обработчик для выбора тарифа."""
    user_id = callback.from_user.id
    plan = TARIFF_PLANS[callback.data]
    logging.info(f"Callback {callback.data} от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписаться", pay=True)],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_plans")]
    ])
    try:
        if user_data[user_id].get('last_pay_message_id'):
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=user_data[user_id]['last_pay_message_id']
            )
            logging.info(f"Удалено сообщение тарифов для пользователя {user_id}")
        await send_message_with_photo(
            callback.message.chat.id,
            plan["description"],
            reply_markup,
            user_id
        )
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=plan["title"],
            description=plan["description"],
            payload=plan["payload"],
            provider_token="",
            currency="XTR",
            prices=[{"label": plan["label"], "amount": plan["amount"]}],
            start_parameter=plan["start_parameter"],
            reply_markup=reply_markup
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка при обработке тарифа {callback.data}: {e}")
        await callback.message.answer("Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        await callback.answer()

@dp.callback_query(lambda callback: callback.data == "back_to_plans")
async def back_to_plans(callback: types.CallbackQuery):
    """Обработчик для возврата к списку тарифов."""
    user_id = callback.from_user.id
    logging.info(f"Callback back_to_plans от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    plans_text = (
        "Я предлагаю несколько тарифных планов, чтобы ты мог выбрать тот, который подходит именно тебе, по каждому тарифу лимит 50 запросов в сутки! \n\n"
        "⦁ <b>1 месяц - 250⭐️ (~429₽)</b>\n"
        "  Этот тариф — отличный способ начать. Ты получаешь всё необходимое для продуктивного старта. Это самый популярный вариант — Хит!\n\n"
        "⦁ <b>3 месяца - 600⭐️ (~1008₽)</b>\n"
        "  Выгодный тариф, который позволит тебе экономить и получать ещё больше пользы. Всего 336₽ в месяц при полном доступе к моим возможностям.\n\n"
        "⦁ <b>12 месяцев - 2000⭐️ (~3298₽)</b>\n"
        "  Для тех, кто действительно хочет погрузиться в процесс и получить максимальный эффект. Ты получаешь полный доступ по лучшей цене — всего 274₽ в месяц.\n\n"
        "<i>Выбери свой план, и я буду рядом, помогая идти к мечтам шаг за шагом!</i>"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎀1 Месяц🎀", callback_data="plan_1month")],
        [InlineKeyboardButton(text="🎀3 месяца🎀", callback_data="plan_3months")],
        [InlineKeyboardButton(text="🎀12 месяцев🎀", callback_data="plan_12months")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_pay")]
    ])
    try:
        if user_data[user_id].get('last_pay_message_id'):
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=user_data[user_id]['last_pay_message_id']
            )
            logging.info(f"Удалено сообщение тарифа для пользователя {user_id}")
        await send_message_with_photo(callback.message.chat.id, plans_text, reply_markup, user_id)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка при возврате к тарифам: {e}")
        await callback.message.answer("Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        await callback.answer()

@dp.callback_query(lambda callback: callback.data == "back_to_pay")
async def back_to_pay(callback: types.CallbackQuery):
    """Обработчик для возврата к начальному сообщению /pay."""
    user_id = callback.from_user.id
    logging.info(f"Callback back_to_pay от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    pay_text = (
        "Спасибо, что пользуешься мной — Эммой! Для всех пользователей доступен бесплатный лимит запросов, "
        "чтобы познакомиться и оценить мои возможности. 😊\n\n"
        "Когда лимит закончится, будет возможность продлить доступ с помощью подписки — "
        "это поддержка моего развития и возможность пользоваться всеми функциями!\n\n"
        "Подписка — это простой и безопасный способ помочь мне стать лучше и приносить больше пользы тебе и другим пользователям! 💖"
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎀Продлить доступ🎀", callback_data="show_plans")]
    ])
    try:
        if user_data[user_id].get('last_pay_message_id'):
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=user_data[user_id]['last_pay_message_id']
            )
            logging.info(f"Удалено сообщение тарифов для пользователя {user_id}")
        await send_message_with_photo(callback.message.chat.id, pay_text, reply_markup, user_id)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка при возврате к /pay: {e}")
        await callback.message.answer("Ой, что-то пошло не так! 😔 Попробуй снова.", parse_mode="HTML")
        await callback.answer()

@dp.callback_query(lambda callback: callback.data == "cancel_feedback")
async def cancel_feedback_callback(callback: types.CallbackQuery):
    """Обработчик нажатия кнопки 'Назад' для отмены /feedback."""
    user_id = callback.from_user.id
    logging.info(f"Нажата кнопка 'Назад' для /feedback от пользователя {user_id}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    if user_data[user_id].get('awaiting_feedback', False):
        user_data[user_id]['awaiting_feedback'] = False
        try:
            if user_data[user_id].get('feedback_message_id'):
                await bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=user_data[user_id]['feedback_message_id']
                )
                logging.info(f"Удалено сообщение /feedback для пользователя {user_id}")
            if user_data[user_id].get('user_feedback_message_id'):
                await bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=user_data[user_id]['user_feedback_message_id']
                )
                logging.info(f"Удалено сообщение пользователя /feedback для {user_id}")
            await callback.message.answer(
                "Режим обратной связи отменён! 😊 Можешь продолжить общение с Эммой.",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщений /feedback: {e}")
            await callback.message.answer(
                "Не удалось удалить сообщения, но режим обратной связи отменён! 😊 Можешь продолжить общение.",
                parse_mode="HTML"
            )
        user_data[user_id]['feedback_message_id'] = None
        user_data[user_id]['user_feedback_message_id'] = None
    else:
        await callback.message.answer(
            "Режим обратной связи уже завершён! 😊 Можешь продолжить общение с Эммой.",
            parse_mode="HTML"
        )
    await callback.answer()
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    """Обработчик pre-checkout query для оплаты."""
    user_id = pre_checkout_query.from_user.id
    logging.info(f"Pre-checkout query от пользователя {user_id}: {pre_checkout_query.invoice_payload}")
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message(lambda message: message.successful_payment is not None)
async def process_successful_payment(message: types.Message):
    """Обработчик успешной оплаты."""
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    logging.info(f"Успешный платёж от пользователя {user_id}: {payload}")
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    for plan_key, plan in TARIFF_PLANS.items():
        if payload == plan["payload"]:
            expiry_date = datetime.now() + timedelta(days=plan["duration_days"])
            amount = plan["amount"]
            duration = plan["label"]
            break
    else:
        logging.error(f"Неизвестный payload: {payload}")
        await message.answer("Ошибка при обработке платежа. 😔 Свяжитесь с поддержкой.", parse_mode="HTML")
        return
    user_data[user_id]['premium'] = True
    user_data[user_id]['expiry'] = expiry_date.timestamp()
    if db:
        try:
            doc_ref = db.collection('users').document(str(user_id))
            doc_ref.set({
                'premium': True,
                'expiry': expiry_date,
                'timestamp': firestore.SERVER_TIMESTAMP
            }, merge=True)
            logging.info(f"Premium-статус сохранён в Firestore для пользователя {user_id}")
            db.collection('payments').document(f"{user_id}_{int(time.time())}").set({
                'user_id': user_id,
                'amount': amount,
                'duration': duration,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            logging.info(f"Платёж сохранён в Firestore для пользователя {user_id}")
        except Exception as e:
            logging.error(f"Ошибка сохранения premium-статуса или платежа в Firestore: {e}")
    try:
        if user_data[user_id].get('last_pay_message_id'):
            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=user_data[user_id]['last_pay_message_id']
            )
            logging.info(f"Удалено сообщение тарифа для пользователя {user_id}")
            user_data[user_id]['last_pay_message_id'] = None
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщения тарифа: {e}")
    await message.answer(
        f"Спасибо за поддержку, ты теперь премиум-пользователь! 🎉 "
        f"Подписка на {duration} активна до {expiry_date.strftime('%Y-%m-%d')}. Наслаждайся всеми функциями! 😊✨",
        parse_mode="HTML"
    )
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")

@dp.message()
async def handle_message(message: types.Message):
    """Обработчик всех текстовых сообщений."""
    logging.info(f"Начало обработки update для user {message.from_user.id}: {message.text[:50]}...")
    if not message.text:
        logging.info(f"Получено нетекстовое сообщение от {message.from_user.id}")
        await message.answer("Извини, я пока обрабатываю только текстовые сообщения! 😊 Напиши текст, и я помогу.")
        return
    
    user_id = message.from_user.id
    user_text = message.text.strip()
    logging.info(f"Получено сообщение от {user_id}: {user_text}")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    await asyncio.sleep(0.5)
    
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [], 
            'active_topic': None, 
            'premium': False, 
            'expiry': None, 
            'last_pay_message_id': None,
            'awaiting_feedback': False,
            'feedback_message_id': None,
            'user_feedback_message_id': None,
            'request_count': 0,
            'last_reset': datetime.now().timestamp()
        }
    
    # Проверка лимита запросов
    current_time = datetime.now().timestamp()
    last_reset = user_data[user_id].get('last_reset', current_time)
    if current_time - last_reset >= 24 * 3600:  # Сброс каждые 24 часа
        user_data[user_id]['request_count'] = 0
        user_data[user_id]['last_reset'] = current_time
        logging.info(f"Сброс счётчика запросов для пользователя {user_id}")
    if user_data[user_id]['request_count'] >= 50:
        logging.info(f"Пользователь {user_id} превысил лимит 50 запросов в сутки")
        await message.answer(
            "Лимит запросов (50 в сутки) исчерпан. Оформите подписку с помощью /pay! 😊",
            parse_mode="HTML"
        )
        return
    user_data[user_id]['request_count'] += 1
    logging.info(f"Пользователь {user_id}: запрос {user_data[user_id]['request_count']}/50")
    
    # Обработка обратной связи
    if user_data[user_id].get('awaiting_feedback', False):
        if not FEEDBACK_CHAT_ID:
            logging.error("FEEDBACK_CHAT_ID не указан в .env")
            await message.answer("Ой, что-то пошло не так! 😔 Обратная связь временно недоступна.", parse_mode="HTML")
            user_data[user_id]['awaiting_feedback'] = False
            user_data[user_id]['feedback_message_id'] = None
            user_data[user_id]['user_feedback_message_id'] = None
            if db:
                try:
                    db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
                    logging.info(f"Сохранены user_data для {user_id} в Firestore")
                except Exception as e:
                    logging.error(f"Ошибка сохранения user_data: {e}")
            return
        
        username = message.from_user.username or message.from_user.first_name or "Аноним"
        feedback_text = (
            f"<b>Обратная связь от пользователя</b> (ID: {user_id}, @{username}):\n"
            f"{user_text}"
        )
        try:
            await bot.send_message(
                chat_id=FEEDBACK_CHAT_ID,
                text=feedback_text,
                parse_mode="HTML"
            )
            logging.info(f"Отправлена обратная связь от {user_id} в чат {FEEDBACK_CHAT_ID}")
            await message.answer(
                "Спасибо за твою обратную связь! 😊 Она очень важна для меня. Команда скоро её рассмотрит!",
                parse_mode="HTML"
            )
            if user_data[user_id].get('feedback_message_id'):
                try:
                    await bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=user_data[user_id]['feedback_message_id']
                    )
                    logging.info(f"Удалено сообщение /feedback для пользователя {user_id}")
                except Exception as e:
                    logging.error(f"Ошибка при удалении сообщения /feedback: {e}")
            if user_data[user_id].get('user_feedback_message_id'):
                try:
                    await bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=user_data[user_id]['user_feedback_message_id']
                    )
                    logging.info(f"Удалено сообщение пользователя /feedback для {user_id}")
                except Exception as e:
                    logging.error(f"Ошибка при удалении сообщения пользователя /feedback: {e}")
            user_data[user_id]['awaiting_feedback'] = False
            user_data[user_id]['feedback_message_id'] = None
            user_data[user_id]['user_feedback_message_id'] = None
        except Exception as e:
            logging.error(f"Ошибка при отправке обратной связи в чат {FEEDBACK_CHAT_ID}: {e}")
            await message.answer(
                "Ой, не удалось отправить обратную связь. 😔 Попробуй ещё раз или напиши позже!",
                parse_mode="HTML"
            )
            user_data[user_id]['awaiting_feedback'] = False
            user_data[user_id]['feedback_message_id'] = None
            user_data[user_id]['user_feedback_message_id'] = None
        if db:
            try:
                db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
                logging.info(f"Сохранены user_data для {user_id} в Firestore")
            except Exception as e:
                logging.error(f"Ошибка сохранения user_data: {e}")
        return
    
    # Проверка статуса подписки
    if user_data[user_id].get('premium', False):
        expiry = user_data[user_id].get('expiry')
        if expiry and datetime.now().timestamp() > expiry:
            user_data[user_id]['premium'] = False
            user_data[user_id]['expiry'] = None
            logging.info(f"Подписка пользователя {user_id} истекла")
            if db:
                try:
                    db.collection('users').document(str(user_id)).set({
                        'premium': False,
                        'expiry': None,
                        'timestamp': firestore.SERVER_TIMESTAMP
                    }, merge=True)
                    logging.info(f"Сохранён статус подписки для {user_id} в Firestore")
                except Exception as e:
                    logging.error(f"Ошибка сохранения статуса подписки: {e}")
    
    # Обработка обычного сообщения
    history = user_data[user_id]['history']
    is_code_request = any(keyword in user_text.lower() for keyword in ["код ", "программ", "коди", "python", "javascript", "html", "css"])
    active_topic = user_data[user_id].get('active_topic')
    
    search_data = None
    if GOOGLE_API_KEY and GOOGLE_CSE_ID and not is_code_request:
        search_data = await get_google_cse_info(user_text, active_topic)
        if search_data and is_relevant(search_data, user_text, active_topic):
            logging.info(f"Найдены релевантные результаты поиска для запроса: {user_text}")
        else:
            search_data = None
            logging.info(f"Результаты поиска не релевантны или отсутствуют для запроса: {user_text}")
    
    response = await get_unlim_response(
        user_id=user_id,
        user_text=user_text,
        history=history,
        is_code_request=is_code_request,
        search_data=search_data,
        use_html=True
    )
    
    new_topic = extract_topic(response) if response else active_topic
    user_data[user_id]['active_topic'] = new_topic
    logging.info(f"Обновлена активная тема для пользователя {user_id}: {new_topic}")
    
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": response})
    user_data[user_id]['history'] = history[-20:]  # Ограничение на 20 сообщений
    
    if db:
        try:
            db.collection('users').document(str(user_id)).set(user_data[user_id], merge=True)
            logging.info(f"Сохранены user_data для {user_id} в Firestore")
        except Exception as e:
            logging.error(f"Ошибка сохранения user_data: {e}")
    
    await send_long_message(message, response, parse_mode="HTML")

# FastAPI для обработки webhook
app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекстный менеджер для запуска и остановки бота."""
    logging.info("Запуск бота...")
    await set_bot_commands()
    if os.getenv("RENDER_URL"):
        webhook_url = f"{os.getenv('RENDER_URL')}/webhook/{TELEGRAM_TOKEN}"
        logging.info(f"Установка webhook: {webhook_url}")
        await bot.set_webhook(webhook_url)
    else:
        logging.info("Удаление webhook для локального запуска")
        await bot.delete_webhook()
        asyncio.create_task(dp.start_polling(bot))
    yield
    logging.info("Остановка бота...")
    await bot.delete_webhook()
    await bot.session.close()

app.lifespan = lifespan

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """Обработчик webhook от Telegram."""
    if token != TELEGRAM_TOKEN:
        logging.error("Неверный токен в webhook")
        return {"status": "error", "message": "Invalid token"}
    update = await request.json()
    update_id = update.get("update_id")
    if update_id in processed_updates:
        logging.info(f"Повторный update_id: {update_id}, пропущен")
        return {"status": "ok"}
    processed_updates.add(update_id)
    try:
        await dp.feed_raw_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Ошибка обработки webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса."""
    logging.info("Health check запрос получен")
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    logging.info("Запуск FastAPI сервера...")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))