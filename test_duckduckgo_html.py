import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename="test.log", format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def test_duckduckgo_html(query: str, max_results: int = 7) -> list:
    try:
        async with aiohttp.ClientSession() as session:
            params = {"q": query, "kl": "ru-ru"}
            logger.info(f"Отправляем HTML-запрос: {query}")
            print(f"Отправляем HTML-запрос: {query}")
            async with session.get("https://duckduckgo.com/html/", params=params) as response:
                if response.status == 200:
                    soup = BeautifulSoup(await response.text(), "html.parser")
                    results = soup.find_all("div", class_="result__body")[:max_results]
                    formatted_results = []
                    for r in results:
                        title_elem = r.find("a", class_="result__a")
                        snippet_elem = r.find("div", class_="result__snippet")
                        if title_elem and snippet_elem:
                            formatted_results.append({
                                "title": title_elem.text.strip(),
                                "snippet": snippet_elem.text.strip(),
                                "link": title_elem["href"]
                            })
                    logger.info(f"Получено {len(formatted_results)} результатов для HTML-запроса: {query}")
                    await asyncio.sleep(2)
                    return formatted_results
                logger.error(f"Ошибка HTTP: {response.status}")
                print(f"Ошибка HTTP: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        print(f"Ошибка парсинга: {e}")
        return []

async def main():
    query = "Три дня дождя"
    results = await test_duckduckgo_html(query)
    if not results:
        print("Ничего не найдено или ошибка. Попробуй позже!")
        logger.warning("Ничего не найдено или ошибка")
        return
    for i, result in enumerate(results, 1):
        print(f"Результат {i}:")
        print(f"Заголовок: {result['title']}")
        print(f"Описание: {result['snippet']}")
        print(f"Ссылка: {result['link']}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())