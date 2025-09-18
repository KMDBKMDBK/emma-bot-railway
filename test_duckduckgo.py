import asyncio
import logging
from ddgs import DDGS

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename="test.log", format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def test_duckduckgo_search(query: str, max_results: int = 7) -> list:
    try:
        ddgs = DDGS()
        logger.info(f"Отправляем запрос: {query}")
        print(f"Отправляем запрос: {query}")
        results = ddgs.text(
            query=query,
            region="ru-ru",
            safesearch="moderate",
            max_results=max_results
        )
        await asyncio.sleep(2)  # Задержка 2 секунды
        formatted_results = [
            {"title": r["title"], "snippet": r["body"], "link": r["href"]}
            for r in results
        ]
        logger.info(f"Получено {len(formatted_results)} результатов для запроса: {query}")
        return formatted_results
    except Exception as e:
        logger.error(f"Ошибка DuckDuckGo: {e}")
        print(f"Ошибка DuckDuckGo: {e}")
        return []

async def main():
    query = "Три дня дождя"
    results = await test_duckduckgo_search(query)
    if not results:
        print("Ничего не найдено или превышен лимит. Попробуй позже или используй прокси!")
        logger.warning("Ничего не найдено или превышен лимит")
        return
    for i, result in enumerate(results, 1):
        print(f"Результат {i}:")
        print(f"Заголовок: {result['title']}")
        print(f"Описание: {result['snippet']}")
        print(f"Ссылка: {result['link']}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())