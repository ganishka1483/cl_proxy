import os
import logging
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Response, HTTPException, status
import httpx

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BYBIT_API = "https://api.bybit.com"
KEEP_ALIVE_URL = f"{BYBIT_API}/v5/market/time"

PROXY_SECRET = os.getenv("PROXY_SECRET", "MY_SECRET_KEY")

# Один общий клиент на всё приложение, а не по одному на каждый запрос —
# так пул соединений переиспользуется, а не создаётся/уничтожается заново
http_client: httpx.AsyncClient | None = None

async def keep_alive():
    while True:
        await asyncio.sleep(840)
        try:
            resp = await http_client.get(KEEP_ALIVE_URL)
            logger.info(f"♻️ Keep-Alive ping: {resp.status_code}")
        except Exception as e:
            logger.error(f"Keep-Alive упал: {e}")

@app.on_event("startup")
async def startup_event():
    global http_client
    http_client = httpx.AsyncClient(timeout=15.0)
    asyncio.create_task(keep_alive())
    logger.info("🚀 Прокси запущен")

@app.on_event("shutdown")
async def shutdown_event():
    if http_client:
        await http_client.aclose()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    incoming_secret = request.headers.get("X-Proxy-Secret")
    if incoming_secret != PROXY_SECRET:
        logger.warning(f"⛔ Попытка неавторизованного доступа с IP: {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing secret token"
        )

    forward_params = dict(request.query_params)
    explicit_url = forward_params.pop("url", None)

    if explicit_url:
        parsed = urlparse(explicit_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid 'url' parameter")
        target_url = explicit_url
    else:
        target_url = f"{BYBIT_API}/{path}"

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("accept-encoding", None)

    try:
        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=forward_params
        )

        excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        safe_headers = {k: v for k, v in response.headers.items() if k.lower() not in excluded}

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=safe_headers
        )
    except Exception as e:
        logger.error(f"Ошибка проксирования: {e}")
        raise HTTPException(status_code=500, detail="Proxy Error")
