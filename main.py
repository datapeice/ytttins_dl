import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from config import BOT_TOKEN, TELEGRAM_API_URL
from services.logger import setup_logging
from handlers import user, admin
from cleanup import delete_old_files

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").rstrip("/")
# Когда используется локальный telegram-bot-api, он вызывает бота через внутреннюю
# Docker-сеть. WEBHOOK_INTERNAL_HOST — адрес бота, доступный локальному серверу.
WEBHOOK_INTERNAL_HOST = os.getenv("WEBHOOK_INTERNAL_HOST", "").rstrip("/")
WEBHOOK_PATH = f"/{BOT_TOKEN}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", 8443))

async def on_startup(bot: Bot):
    from services.cookie_utils import convert_netscape_to_json
    from config import DATA_DIR
    
    cookies_txt = DATA_DIR / "cookies.txt"
    cookies_json = DATA_DIR / "cookies.json"
    convert_netscape_to_json(cookies_txt, cookies_json)

    asyncio.create_task(delete_old_files())
    is_local_api = "telegram-bot-api" in os.getenv("TELEGRAM_API_URL", "")

    if is_local_api and WEBHOOK_INTERNAL_HOST:
        # Локальный сервер вызывает бота через внутреннюю Docker-сеть
        webhook_url = f"{WEBHOOK_INTERNAL_HOST}{WEBHOOK_PATH}"
    elif WEBHOOK_HOST:
        # Реальный Telegram вызывает через внешний домен (nginx)
        webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    else:
        logging.warning("⚠️ WEBHOOK_HOST not set, skipping webhook registration (polling mode)")
        return

    await bot.set_webhook(url=webhook_url)
    logging.info(f"Webhook set to {webhook_url}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("Webhook deleted")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not found in environment variables.")

    session_kwargs = {"timeout": 300}

    if "telegram-bot-api" in TELEGRAM_API_URL or "127.0.0.1" in TELEGRAM_API_URL or "localhost" in TELEGRAM_API_URL:
        # Использование локального сервера Telegram Bot API
        server = TelegramAPIServer.from_base(TELEGRAM_API_URL, is_local=True)
        bot = Bot(token=BOT_TOKEN, session=AiohttpSession(api=server, **session_kwargs))
        logging.info(f"Using local Telegram Bot API Server at {TELEGRAM_API_URL}")
    else:
        bot = Bot(token=BOT_TOKEN, session=AiohttpSession(**session_kwargs))
        logging.info("Using default Telegram Bot API Server")

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register routers
    dp.include_router(admin.router)
    dp.include_router(user.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logging.info(f"🚀 Bot starting webhook server on {WEBAPP_HOST}:{WEBAPP_PORT}...")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == "__main__":
    main()
