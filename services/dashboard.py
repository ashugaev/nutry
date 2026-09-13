"""Read-only Mini App API. Authenticate signed Telegram data before diary access."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

ASSETS = Path(__file__).resolve().parents[1] / "web"
FIELDS = ("calories_kcal", "protein_g", "carbs_g", "fat_g")


def authenticate(raw, token, allowed, now=None):
    try:
        if not raw or len(raw) > 8192:
            raise ValueError
        pairs = parse_qsl(raw, strict_parsing=True)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError
        signature = data.pop("hash")
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        age = (time.time() if now is None else now) - int(data["auth_date"])
        if age < -30 or age > 3600:
            raise ValueError
        user = json.loads(data["user"])
        if type(user["id"]) is not int or user["id"] not in allowed:
            raise ValueError
        if data.get("chat_type", "sender") != "sender":
            raise ValueError
        return user["id"]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise web.HTTPUnauthorized(text="Open this app from your authorized Telegram account") from None


def statistics(store, days=30, now=None):
    today = (now or datetime.now(store.timezone)).astimezone(store.timezone).date()
    start = today - timedelta(days=days - 1)
    # Bounded output and no Notion ids, source messages, or other private metadata.
    with store._connect() as db:
        rows = db.execute(
            "SELECT created_at,dish,calories_kcal,protein_g,carbs_g,fat_g,fiber_g FROM entries "
            "WHERE substr(created_at,1,10) BETWEEN ? AND ? ORDER BY created_at",
            (start.isoformat(), today.isoformat()),
        ).fetchall()
    result = { (start + timedelta(days=i)).isoformat():
              {"date": (start + timedelta(days=i)).isoformat(), "count": 0, "fiber_g": 0, "fiber_missing": 0,
               **{field: 0 for field in FIELDS}, "meals": []} for i in range(days)}
    for stamp, dish, *values in rows:
        day = result[stamp[:10]]
        day["count"] += 1
        for key, value in zip(FIELDS, values):
            day[key] += value
        fiber = values[-1]
        if fiber is None:
            day['fiber_missing'] += 1
        else:
            day['fiber_g'] += fiber
        day["meals"].append({"time": stamp[11:16], "dish": dish, "fiber_g": fiber, **dict(zip(FIELDS, values))})
    return {"today": today.isoformat(), "timezone": str(store.timezone), "days": list(result.values())}


@web.middleware
async def headers(request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    response.headers.update({
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'",
    })
    if isinstance(response, web.HTTPException):
        raise response
    return response


def create_app(settings, store):
    app = web.Application(middlewares=[headers], client_max_size=16384)

    async def stats(request):
        user_id = authenticate(request.headers.get("X-Telegram-Init-Data", ""), settings.telegram_token,
                               settings.allowed_user_ids | {settings.owner_user_id})
        try:
            days = int(request.query.get("days", "30"))
            if not 1 <= days <= 90:
                raise ValueError
        except ValueError:
            raise web.HTTPBadRequest(text="days must be between 1 and 90") from None
        payload = statistics(store, days)
        payload["language"] = store.get_language(user_id)
        return web.json_response(payload)

    async def asset(request):
        name = request.match_info.get("name", "index.html")
        if name not in {"index.html", "app.js", "style.css"}:
            raise web.HTTPNotFound()
        return web.FileResponse(ASSETS / name)

    app.router.add_get("/api/stats", stats)
    app.router.add_get("/", asset)
    app.router.add_get("/{name}", asset)
    return app


async def start_dashboard(settings, store):
    runner = web.AppRunner(create_app(settings, store), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", settings.mini_app_port).start()
    return runner
