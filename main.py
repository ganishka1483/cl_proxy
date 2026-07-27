import os
import logging
import json
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Response, HTTPException, status
import httpx

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BYBIT_API = "https://api.bybit.com"
PROXY_SECRET = os.getenv("PROXY_SECRET", "MY_SECRET_KEY")

# Общий HTTP-клиент для переиспользования соединений
http_client: httpx.AsyncClient | None = None

@app.on_event("startup")
async def startup_event():
    global http_client
    http_client = httpx.AsyncClient(timeout=15.0)
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

        # Оптимизация: Обрезка JSON только для массовых тиков крона (без конкретного symbol)
        if (
            "v5/market/tickers" in path
            and "symbol" not in forward_params
            and response.status_code == 200
        ):
            try:
                raw_data = response.json()
                if raw_data.get("retCode") == 0:
                    prices = {}
                    for item in raw_data.get("result", {}).get("list", []):
                        symbol = item.get("symbol", "")
                        if symbol.endswith("USDT"):
                            coin = symbol.replace("USDT", "")
                            prices[coin] = float(item.get("lastPrice") or 0)

                    trimmed_body = json.dumps({"retCode": 0, "prices": prices})
                    return Response(
                        content=trimmed_body,
                        status_code=200,
                        headers={"content-type": "application/json"}
                    )
            except Exception as e:
                logger.error(f"Ошибка сжатия JSON: {e}")

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
