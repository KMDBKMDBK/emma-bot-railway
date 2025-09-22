import logging
import re
import aiohttp
import time
from openai import AsyncOpenAI
from bs4 import BeautifulSoup
import os
from database import save_user_data, save_message_to_firestore
from state import user_data
from aiogram import types  # Добавлен импорт для types

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

async def get_unlim_response(user_id: int, user_text: str, history: list, is_code_request=False, search_data=None, use_html=True, max_retries=5):
    logger.info(f"Запрос к OpenRouter для user {user_id}: {user_text[:50]}...")
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
                [InlineKeyboardButton(text=MINIAPP_BUTTON_TEXT, web_app=types.WebAppInfo(url=web_app_url))]
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