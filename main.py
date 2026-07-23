from fastapi import FastAPI, Request, Response
import httpx
import asyncio
import logging

# ⚠️ ВАЖНО: переменная должна называться app
app = FastAPI()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Базовый URL Bybit API
BYBIT_API = "https://api.bybit.com"

# --- Функция Keep-Alive (чтобы Render не засыпал) ---
async def keep_alive():
    """Раз в 14 минут стучим в Bybit, чтобы Render держал инстанс живым"""
    while True:
        await asyncio.sleep(840)  # 840 секунд = 14 минут
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BYBIT_API}/v5/market/time")
                logger.info(f"♻️ Keep-Alive ping: {resp.status_code}")
        except Exception as e:
            logger.error(f"Keep-Alive упал: {e}")

# Запускаем keep-alive в фоновом режиме при старте сервера
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(keep_alive())

# --- Главный прокси-эндпоинт ---
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    """
    Проксирует любой запрос на api.bybit.com
    """
    url = f"{BYBIT_API}/{path}"
    body = await request.body()
    headers = dict(request.headers)
    
    # Убираем заголовки, связанные с хостом
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    logger.info(f"➡️ Прокси: {request.method} {url}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
            
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
