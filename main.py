from fastapi import FastAPI, Request, Response
import httpx
import asyncio
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BYBIT_API = "https://api.bybit.com"

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
    logger.info(f"🚀 Прокси запущен, целевой API: {BYBIT_API}")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    url = f"{BYBIT_API}/{path}"
    body = await request.body()
    
    # Формируем новые заголовки, чтобы точно указать версию API
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "X-API-Version": "v5"  # <-- КЛЮЧЕВОЙ МОМЕНТ: Явно говорим, что хотим v5
    }
    
    # Добавляем оригинальные заголовки, которые не конфликтуют
    for key, value in request.headers.items():
        if key.lower() not in ["host", "content-length", "x-api-version", "user-agent", "accept"]:
            headers[key] = value
    
    logger.info(f"➡️ Прокси: {request.method} {url}")
    
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
