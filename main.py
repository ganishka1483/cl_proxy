BYBIT_API = "https://api.bybit.com"
KEEP_ALIVE_URL = f"{BYBIT_API}/v5/market/time"

...

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

    forward_params = dict(request.query_params)
    explicit_url = forward_params.pop("url", None)

    if explicit_url:
        # Новый режим: любой сайт через ?url=
        parsed = urlparse(explicit_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid 'url' parameter")
        target_url = explicit_url
    else:
        # Старый режим: путь форвардится на Bybit, как раньше (Worker не трогаем)
        target_url = f"{BYBIT_API}/{path}"

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=forward_params
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except Exception as e:
            logger.error(f"Ошибка проксирования: {e}")
            raise HTTPException(status_code=500, detail="Proxy Error")
