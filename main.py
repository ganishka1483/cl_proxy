import os
import logging
import asyncio
from fastapi import FastAPI, Request, Response, HTTPException, status
import httpx

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BYBIT_API = "https://api.bybit.com"

# Получаем секретный ключ из переменных окружения
# Если переменная не задана, задается запасное значение для тестов
PROXY_SECRET = os.getenv("PROXY_SECRET", "MY_SECRET_KEY")

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
    # --- Проверка безопасности ---
    incoming_secret = request.headers.get("X-Proxy-Secret")
    if incoming_secret != PROXY_SECRET:
        logger.warning(f"⛔ Попытка неавторизованного доступа с IP: {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing secret token"
        )
    # -----------------------------

    url = f"{BYBIT_API}/{path}"
    body = await request.body()
    
    # Перенаправление запроса к Bybit
    headers = dict(request.headers)
    # Удаляем заголовок host, чтобы httpx подставил правильный host для Bybit
    headers.pop("host", None)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except Exception as e:
            logger.error(f"Ошибка проксирования: {e}")
            raise HTTPException(status_code=500, detail="Proxy Error")
