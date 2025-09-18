import logging
import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
UNLIM_API_KEY = os.getenv("UNLIM_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# Настройка клиента Unlim API
client = AsyncOpenAI(
    api_key=UNLIM_API_KEY,
    base_url="https://unlimbot.com/v1"
)

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Хранилище для истории
user_history = {}

def clean_markdown(text):
    """Очищает и форматирует Markdown для Telegram (MarkdownV2)"""
    lines = text.split('\n')
    in_code_block = False
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            cleaned_lines.append(line)
        elif in_code_block:
            cleaned_lines.append(line)
        else:
            for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
                line = line.replace(char, f'\\{char}')
            cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines)[:4000]
    if cleaned_text.count('```') % 2 != 0:
        cleaned_text += '\n```'
    return cleaned_text

async def get_google_cse_info(query: str):
    """
    Выполняет поиск информации по запросу через Google Custom Search JSON API и возвращает только значимые поля.
    :param query: Поисковый запрос пользователя.
    :return: Список словарей с заголовком, описанием и ссылкой или сообщение об ошибке.
    """
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "num": 3
            }
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        logging.error(f"Google CSE ошибка: {data['error']['message']}")
                        return "Извини, что-то пошло не так с поиском. 😔 Попробуй ещё раз!"
                    
                    results = data.get("items", [])
                    if not results:
                        return "Извини, ничего не нашёл по твоему запросу. 😔 Попробуй уточнить или спроси что-то другое!"
                    
                    formatted_results = []
                    for result in results:
                        title = result.get("title", "Без заголовка")
                        snippet = result.get("snippet", "Без описания")
                        link = result.get("link", "Без ссылки")
                        formatted_results.append({
                            "title": title,
                            "snippet": snippet,
                            "link": link
                        })
                    return formatted_results
                else:
                    logging.error(f"Google CSE HTTP ошибка: {response.status}")
                    return "Извини, что-то пошло не так с поиском. 😔 Попробуй позже!"
    except Exception as e:
        logging.error(f"Ошибка Google CSE: {e}")
        return "Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊"

async def get_unlim_response(user_text, history, is_code_request=False, search_data=None):
    try:
        system_prompt = (
            "Ты Эмма, эмпатичный и умный компаньон, как @GPT4AgentsBot. Отвечай СТРОГО ПРАВДИВО, только на основе предоставленных данных или проверенных фактов. "
            "Если предоставлены данные поиска, используй ТОЛЬКО их для ответа, независимо от темы запроса. Форматируй ответ в MarkdownV2, включая заголовки, описания и ссылки (экранируй их как \\[текст\\]\\(ссылка\\)). "
            "Если данных поиска нет, отвечай: 'Извини, я не знаю точного ответа. 😔 Хочешь, уточним или спросим что-то другое?' "
            "Если пользователь просит код, напиши рабочий код в корректном MarkdownV2 с тройными обратными кавычками (```). После кода добавь краткое описание с пунктами (⦁) и предложи помощь. "
            "Для других вопросов давай короткие, точные ответы с эмпатичным тоном и эмодзи 😊✨. Предлагай углубиться: 'Если хочешь, могу рассказать подробнее!' "
            "НИКОГДА не выдумывай факты, библиотеки или методы. Убедись, что MarkdownV2 корректен."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            *history[-10:],
            {"role": "user", "content": user_text}
        ]
        if search_data and isinstance(search_data, list):
            search_content = "Данные поиска:\n"
            for i, result in enumerate(search_data, 1):
                search_content += (
                    f"{i}. Заголовок: {result['title']}\n"
                    f"Описание: {result['snippet']}\n"
                    f"Ссылка: {result['link']}\n\n"
                )
            messages.append({"role": "user", "content": search_content})
        
        response = await client.chat.completions.create(
            model="gpt-5-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=1500 if is_code_request else 200
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка Unlim API: {e}")
        return "Извини, что-то пошло не так. 😔 Попробуй ещё раз или спроси что-то другое! 😊"

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []
    await message.answer("Привет! Я Эмма, твой умный и эмпатичный компаньон, как @GPT4AgentsBot. Могу искать информацию по любому твоему запросу, писать код и помогать с вопросами. Что у тебя на уме? 😊✨")

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()
    logging.info(f"Пользователь {user_id}: Получен текст: {user_text}")
    
    is_code_request = any(keyword in user_text.lower() for keyword in [
        "напиши код", "программа", "код на", "python", "javascript",
        "напиши программу", "код на питоне", "код калькулятора"
    ])
    
    if user_id not in user_history:
        user_history[user_id] = []
    user_history[user_id].append({"role": "user", "content": user_text})
    
    if not is_code_request:
        search_data = await get_google_cse_info(user_text)
        if isinstance(search_data, str):
            response = search_data
        else:
            response = await get_unlim_response(user_text, user_history.get(user_id, []), is_code_request, search_data)
    else:
        response = await get_unlim_response(user_text, user_history.get(user_id, []), is_code_request)
    
    logging.info(f"Пользователь {user_id}: Ответ от API: {response[:100]}...")
    
    cleaned_response = clean_markdown(response)
    try:
        await message.answer(cleaned_response, parse_mode="MarkdownV2")
    except Exception as e:
        logging.error(f"Ошибка отправки в Telegram: {e}")
        await message.answer(response[:4000], parse_mode=None)
    
    user_history[user_id].append({"role": "assistant", "content": response})

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data
    logging.info(f"Пользователь {user_id}: Нажата кнопка: {action}")
    
    response = await get_unlim_response(action, user_history.get(user_id, []), is_code_request=False)
    logging.info(f"Пользователь {user_id}: Ответ от API: {response[:100]}...")
    cleaned_response = clean_markdown(response)
    try:
        await callback.message.answer(cleaned_response, parse_mode="MarkdownV2")
    except Exception as e:
        logging.error(f"Ошибка отправки в Telegram: {e}")
        await callback.message.answer(response[:4000], parse_mode=None)
    
    user_history[user_id].append({"role": "assistant", "content": response})
    await callback.answer()

async def main():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())