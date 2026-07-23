from fastapi import FastAPI, Request, Response
import httpx
import asyncio
import logging
import os  # <-- Добавляем, чтобы проверить переменные окружения

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверяем, нет ли переменной окружения, которая переопределяет URL
ENV_API_URL = os.getenv("BYBIT_API", None)
if ENV_API_URL:
    logger.warning(f"⚠️ Найдена переменная окружения BYBIT_API: {ENV_API_URL}")
    BYBIT_API = ENV_API_URL
else:
    BYBIT_API = "https://api.bybit.com"

logger.info(f"🚀 Целевой API установлен: {BYBIT_API}")

async def keep_alive():
    while True:
        await asyncio.sleep(840)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BYBIT_API}/v5/market/time")
                logger.info(f"♻️ Keep-Alive ping: {resp.status_code}")
        except Exception as e:
            logger.error(f"Keep-Alive упал: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(keep_alive())
    logger.info(f"✅ Прокси запущен, целевой API: {BYBIT_API}")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    url = f"{BYBIT_API}/{path}"
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    logger.info(f"➡️ Прокси: {request.method} {url}")  # <-- Здесь будет видно реальный URL

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
            logger.info(f"✅ Ответ от Bybit: {resp.status_code} для {url}")
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
    except httpx.TimeoutException:
        logger.error(f"⏰ Таймаут при запросе к {url}")
        return Response(
            content='{"error": "Bybit API timeout"}',
            status_code=504,
            media_type="application/json"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка прокси: {e}")
        return Response(
            content=f'{{"error": "Proxy error: {str(e)}"}}',
            status_code=500,
            media_type="application/json"
        )
