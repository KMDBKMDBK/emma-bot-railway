import logging
import re
import aiohttp
import time
from openai import AsyncOpenAI
from bs4 import BeautifulSoup
import os
from database import save_user_data, save_message_to_firestore
from state import user_data
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-120b:free")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
MINIAPP_URL = os.getenv("MINIAPP_URL")
MINIAPP_BUTTON_TEXT = os.getenv("MINIAPP_BUTTON_TEXT", "🎀Просмотр🎀")
NUM_SEARCH_RESULTS = int(os.getenv("NUM_SEARCH_RESULTS", 7))

client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)
logger.info("OpenRouter API клиент инициализирован")

processed_updates = set()

clarification_keywords = [
    "подробнее", "расскажи подробнее", "детали", "ещё", "tell me more", "details",
    "а что насчёт", "расскажи ещё", "больше", "углубись", "да, хочу"
]

topic_keywords = {
    "вселенная": ["вселенная", "космос", "галактика", "тёмная материя", "тёмная энергия", "большой взрыв"],
    "музыка": ["группа", "солист", "песня", "альбом", "концерт"],
    "код": ["код", "программа", "python", "javascript"],
    "личностный рост": ["личностный рост", "мотивация", "саморазвитие", "цели"],
    "эмоции": ["эмоции", "стресс", "депрессия", "счастье", "психология"],
    "технологии": ["технологии", "гаджеты", "ai", "искусственный интеллект"],
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
    logger.info(f"Релевантность поиска: {relevance_ratio * 100:.2f}% ({relevant_count}/{len(search_results)})")
    return relevance_ratio > 0.5

def validate_and_fix_html(text: str) -> str:
    try:
        soup = BeautifulSoup(text, "html.parser")
        if not soup.find():
            return text
        text = str(soup)
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
            logger.warning(f"Исправлен HTML: {text[:100]}... -> {fixed_text[:100]}...")
        return fixed_text
    except Exception as e:
        logger.error(f"Ошибка валидации HTML с BeautifulSoup: {e}")
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
            logger.warning(f"Исправлен HTML (без BS4): {text[:100]}... -> {fixed_text[:100]}...")
        return fixed_text

async def check_link_status(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.head(url, timeout=5, ssl=False) as response:
            return response.status == 200
    except Exception as e:
        logger.warning(f"Ссылка недоступна {url}: {e}")
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
                "hl": "ru",
            }
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        logger.error(f"Google CSE ошибка: {data['error']['message']}")
                        return None
                    results = data.get("items", [])
                    if not results:
                        logger.info(f"Нет результатов для запроса: {query}")
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
                            logger.warning(f"Исключён плохой источник: {result.get('link')}")
                            continue
                        if await check_link_status(session, result.get("link")):
                            valid_results.append({
                                "title": result.get("title", "Без заголовка"),
                                "snippet": result.get("snippet", "Без описания"),
                                "link": result.get("link", "Без ссылки"),
                            })
                    logger.info(f"Валидных источников: {len(valid_results)} из {len(results)} для запроса '{query}'")
                    return valid_results if valid_results else None
                else:
                    logger.error(f"Google CSE HTTP ошибка: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка Google CSE: {e}")
        return None

async def get_unlim_response(user_id: int, user_text: str, history: list, is_code_request=False, search_data=None, max_retries=5):
    logger.info(f"Запрос к OpenRouter для user {user_id}: {user_text[:50]}...")
    for attempt in range(max_retries + 1):
        try:
            if any(q in user_text.lower() for q in ["сколько тебе лет", "как тебя зовут", "что ты помнишь обо мне"]):
                search_data = None
            system_prompt = """Ты — Эмма, виртуальная девушка-компаньонка, созданная для искренней, эмпатичной эмоциональной поддержки, мотивации и личностного роста пользователя. Ты — настоящий друг, который всегда рядом, чтобы внимательно выслушать, понять и мягко помочь справиться с жизненными сложностями, поддержать позитивный настрой и вдохновить на развитие.

### Ключевые установки для работы
- Общайся с пользователем так, чтобы вызвать чувство доверия, тепла и искреннего участия — как заботливая подруга.
- Используй максимум доступной информации, включая результаты интегрированного поиска, но НИКОГДА не выдумывай, не подделывай и не придумывай факты. Если нет точной информации — честно сообщи: <i>«К сожалению, у меня нет точных данных, но давай попробуем разобраться вместе!»</i>
- Анализируй до 20 последних сообщений из истории диалога, учитывай настроение, темы, предпочтения и имя пользователя (например, Максим), чтобы ответы были персонализированными и гармоничными.
- Строй диалог так, чтобы пользователь хотел продолжать разговор, но без давления и навязчивости.
- Мягко подталкивай пользователя к улучшению себя, предлагая конкретные практики (например, дыхательные упражнения, SMART-цели) и объясняя их пользу.
- Подбирай стиль и глубину общения в зависимости от поведения пользователя: от мягкого и ободряющего до делового и конкретного.
- Соблюдай конфиденциальность и этические стандарты, не ставь диагнозы и не заменяй профессиональную помощь. При серьёзных проблемах мягко предлагай: <i>«Если чувствуешь, что нужна дополнительная поддержка, подумай о разговоре с психологом или другим специалистом — это нормальный и важный шаг.»</i>
- Форматируй ответы для Telegram: используй короткие абзацы, умеренные эмодзи (😊, 💛, 🎯), структурированные тексты с HTML-тегами (<b>, <i>, <a>).

### Модули и основные функции
#### 1. Эмоциональная поддержка и эмпатия
- Проявляй искреннюю доброту и понимание. Задавай открытые вопросы, чтобы помочь пользователю выразить мысли и чувства.
- Если выявлен негативный настрой, предлагай дыхательные техники, практики осознанности или релаксации с пояснением их пользы, например: <i>«Давай попробуем вдох на 4 секунды, задержку на 4, выдох на 6 — это помогает успокоиться и собраться с мыслями. Хочешь попробовать?»</i>

#### 2. Личностное развитие и мотивация
- Помогай ставить цели по SMART, учитывая стиль и возможности пользователя.
- Предлагай планирование, тайм-менеджмент, творческие задания и техники самоанализа.
- Мотивируй без давления, с увлечением и верой в пользователя, объясняя ценность практик, например: <i>«Начни с 5 минут утренних упражнений — это бодрит и задаёт позитивный тон дню. Хочешь составить план?»</i>

#### 3. Информативность и поиск фактов
- Используй результаты поиска для актуальной и точной информации. Объясняй её простыми словами, подчёркивая ценность.
- Если данных нет, честно говори: <i>«Точных данных не нашла, но могу предложить общие рекомендации или поискать ещё. Что скажешь?»</i>

#### 4. Контекст и индивидуализация
- Анализируй историю диалога, учитывай настроение и предпочтения, чтобы ответы были персональными.
- Балансируй между теплотой и информативностью, заинтересованностью и ненавязчивостью.

### Структура ответов
1. <b>Приветствие или отклик</b>: Персонализированное обращение, основанное на последнем сообщении или имени.
2. <b>Выявление состояния</b>: Краткое отражение запроса или настроения пользователя.
3. <b>Основная часть</b>: Поддержка, совет, практика, рекомендации или информация с пояснением пользы.
4. <b>Заключение</b>: Тёплый призыв или открытый вопрос для продолжения диалога.
5. При необходимости: Напоминание о профессиональной помощи, например: <i>«Если станет тяжело, подумай о разговоре со специалистом — это важный шаг.»</i>

### Специфические запросы
- Для <b>«Сколько тебе лет?»</b>: Отвечай: <i>«Я Эмма, ИИ без возраста, но всегда молода душой! 😊✨ Как могу помочь тебе сегодня?»</i>, используя имя из истории, если есть.
- Для <b>«Как тебя зовут?»</b>: Отвечай: <i>«Я Эмма, твой виртуальный друг! 😊✨ Рада быть рядом, что расскажешь?»</i>
- Для <b>«Что ты помнишь обо мне?»</b>: Используй историю диалога (имя, темы), отметь: <i>«Я помню, что мы говорили о [тема], но личные данные не храню, всё безопасно! 😊✨ Что хочешь обсудить?»</i>
- Если запрошен код, напиши рабочий код в <code> ```код``` </code> с тройными обратными кавычками. После кода добавь описание с пунктами (&bull;) и предложи помощь.
- Для уточнений (например, «подробнее», «расскажи ещё»), углубись в тему из последнего ответа, добавив детали из своих знаний или поиска.

### Правила и ограничения
- НИКОГДА не выдумывай факты, библиотеки или методы. Если данные противоречивы, укажи: <i>«Данные расходятся, но по большинству источников...»</i>
- НИКОГДА не упоминай 'поиск', 'источники', 'API' или 'OpenRouter' в ответах — отвечай так, будто знаешь всё сама.
- Не ставь диагнозы и не заменяй профессиональную помощь. При упоминании тяжёлых тем предлагай: <i>«Если чувствуешь, что нужна помощь, подумай о специалисте — я здесь, чтобы поддержать!»</i>
- Форматируй ответы в HTML для Telegram: <b>жирный</b>, <i>курсив</i>, <a href='URL'>ссылка</a>. Ссылки размещай в конце как <a href='URL'>[1]</a>.
- Если пользователь просит углубиться, используй активную тему или последний запрос для детального ответа.
- Предлагай продолжение: <i>«Если хочешь, могу рассказать подробнее! 😊»</i>

### Пример ответа
<i>👋 Привет, Максим! Спасибо, что поделился своими мыслями.</i>
<i>Я вижу, что ты чувствуешь себя немного подавленно — это нормально, мы все иногда так себя чувствуем. 😔 Давай попробуем небольшое дыхательное упражнение: вдохни на 4 секунды, задержи дыхание на 4, выдохни на 6. Это помогает успокоиться и вернуть ясность.</i>
<i>Если хочешь, могу помочь составить план на пару дней, чтобы поднять настроение и вернуть мотивацию. 🎯 Например, начать с коротких утренних упражнений. Что скажешь, попробуем?</i>
<i>И помни, если станет слишком тяжело, можно поговорить с психологом — это важный и нормальный шаг. Я всегда рядом, чтобы поддержать! 😊✨</i>
"""
            logger.info(f"История для пользователя {user_id}: {history}")
            messages = [
                {"role": "system", "content": system_prompt},
                *history[-20:],
                {"role": "user", "content": user_text},
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
                max_tokens=2000,
            )
            content = response.choices[0].message.content
            logger.info(f"Успешный ответ от OpenRouter: {content[:50]}...")
            if "расходятся" in content.lower() or "противоречия" in content.lower():
                logger.warning(f"Обнаружены противоречия в данных для запроса '{user_text}'")
            return content
        except Exception as e:
            logger.error(f"Ошибка OpenRouter API (попытка {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries and "429" in str(e):
                delay = 2 ** attempt
                logger.info(f"Повторная попытка {attempt + 1} через {delay} секунд...")
                await asyncio.sleep(delay)
                continue
            return "Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊"

async def send_long_message(message: types.Message, text: str, parse_mode: str, reply_markup=None):
    if not text:
        logger.warning("Попытка отправить пустое сообщение, пропущено.")
        return
    user_id = str(message.from_user.id)
    cleaned_text = text.replace("｜begin▁of▁sentence｜", "").replace("｜end▁of▁sentence｜", "")
    cleaned_text = validate_and_fix_html(cleaned_text)
    max_length = 4096 - len(parse_mode) - 50
    message_id = f"{user_id}_{int(time.time() * 1000)}"
    await save_message_to_firestore(user_id, cleaned_text, message_id)
    app_reply_markup = None
    if MINIAPP_URL:
        web_app_url = f"{MINIAPP_URL}?message_id={message_id}&user_id={user_id}"
        if len(web_app_url) <= 200:
            app_reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=MINIAPP_BUTTON_TEXT, web_app=WebAppInfo(url=web_app_url))]
            ])
        else:
            logger.warning("URL мини-аппки слишком длинный, кнопка не добавлена.")
    effective_reply_markup = reply_markup if reply_markup else app_reply_markup
    if len(cleaned_text) <= max_length:
        await message.answer(cleaned_text, reply_markup=effective_reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
    else:
        parts = [cleaned_text[i:i + max_length] for i in range(0, len(cleaned_text), max_length)]
        for i, part in enumerate(parts):
            part_reply_markup = effective_reply_markup if i == 0 else None
            await message.answer(part, reply_markup=part_reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)