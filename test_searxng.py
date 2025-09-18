import asyncio
import aiohttp
import logging
import certifi
import ssl

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename="test.log",
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def test_searxng_search(query: str, max_results: int = 7, verify_ssl: bool = True) -> list:
    try:
        # Создаем SSL контекст с сертификатами certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where()) if verify_ssl else ssl._create_unverified_context()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; SearXNGClient/1.0; +https://github.com/me)"  # Чтобы не получить 403
        }
        
        async with aiohttp.ClientSession() as session:
            params = {"q": query, "format": "json", "language": "ru-RU"}
            logger.info(f"Отправляем SearXNG-запрос: {query}")
            print(f"Отправляем SearXNG-запрос: {query}")
            
            async with session.get("https://searx.be/search", params=params, headers=headers, ssl=ssl_context) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])[:max_results]
                    formatted_results = [
                        {"title": r["title"], "snippet": r["content"], "link": r["url"]}
                        for r in results
                    ]
                    logger.info(f"Получено {len(formatted_results)} результатов для SearXNG-запроса: {query}")
                    await asyncio.sleep(1)
                    return formatted_results
                else:
                    logger.error(f"Ошибка HTTP: {response.status}")
                    print(f"Ошибка HTTP: {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Ошибка SearXNG: {e}")
        print(f"Ошибка SearXNG: {e}")
        return []

async def main():
    query = "Три дня дождя"

    # Сначала пробуем с проверкой SSL
    results = await test_searxng_search(query, verify_ssl=True)
    if not results:
        print("Ошибка с проверкой SSL или доступом. Попытка без проверки сертификата (небезопасно)...")
        logger.warning("Ошибка с проверкой SSL, повторный запрос без проверки")
        # Попытка без проверки сертификатов
        results = await test_searxng_search(query, verify_ssl=False)

    if not results:
        print("Ничего не найдено или ошибка. Попробуй другой инстанс SearXNG!")
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
