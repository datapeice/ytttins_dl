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
from services import zip_service

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").rstrip("/")
# Когда используется локальный telegram-bot-api, он вызывает бота через внутреннюю
# Docker-сеть. WEBHOOK_INTERNAL_HOST — адрес бота, доступный локальному серверу.
WEBHOOK_INTERNAL_HOST = os.getenv("WEBHOOK_INTERNAL_HOST", "").rstrip("/")
WEBHOOK_PATH = f"/{BOT_TOKEN}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", 8443))

async def check_premium_expiry_worker(bot: Bot):
    """Background worker to check premium expiries."""
    from database.storage import stats
    from database.models import UserProfile
    from datetime import datetime, timedelta
    
    while True:
        try:
            if stats.Session:
                with stats.Session() as session:
                    now = datetime.utcnow()
                    soon = now + timedelta(days=1)
                    
                    # Notified Expiry Soon
                    expiring_soon = session.query(UserProfile).filter(
                        UserProfile.is_premium == 1,
                        UserProfile.premium_expiry.isnot(None),
                        UserProfile.premium_expiry <= soon,
                        UserProfile.premium_expiry > now,
                        UserProfile.notified_expiry_soon == 0
                    ).all()
                    
                    for profile in expiring_soon:
                        profile.notified_expiry_soon = 1
                        # Убеждаемся, что ID положительный (это личный чат, а не группа, у групп ID отрицательные)
                        if profile.user_id > 0:
                            try:
                                await bot.send_message(
                                    profile.user_id,
                                    "⚠️ <b>Warning!</b>\nYour Premium subscription will expire in less than 24 hours.\nUse /donate to extend it and keep enjoying the features without limits!",
                                    parse_mode="HTML"
                                )
                            except Exception as e:
                                logging.warning(f"Failed to notify user {profile.user_id} (perhaps hasn't started bot in PM): {e}")
                    
                    session.commit()
                            
                    # Notified Expired
                    expired = session.query(UserProfile).filter(
                        UserProfile.is_premium == 1,
                        UserProfile.premium_expiry.isnot(None),
                        UserProfile.premium_expiry <= now,
                        UserProfile.notified_expired == 0
                    ).all()
                    
                    for profile in expired:
                        profile.is_premium = 0
                        profile.premium_expiry = None
                        profile.notified_expiry_soon = 0
                        profile.notified_expired = 0
                        
                        if profile.user_id > 0:
                            try:
                                await bot.send_message(
                                    profile.user_id,
                                    "❌ <b>Premium Expired!</b>\nYour Premium subscription has ended. You have been switched back to the regular limits.\nUse /donate to reactivate Premium!",
                                    parse_mode="HTML"
                                )
                            except Exception as e:
                                logging.warning(f"Failed to notify user {profile.user_id} about expired premium: {e}")
                    
                    session.commit()
        except Exception as e:
            logging.error(f"Expiry check error: {e}")
            
        await asyncio.sleep(3600)  # Check every hour

async def on_startup(bot: Bot):
    from services.cookie_utils import convert_netscape_to_json
    from config import DATA_DIR, COOKIES_CONTENT
    
    cookies_txt = DATA_DIR / "cookies.txt"
    cookies_json = DATA_DIR / "cookies.json"
    
    # Write cookies from environment content if provided
    if COOKIES_CONTENT:
        try:
            with open(cookies_txt, 'w', encoding='utf-8') as f:
                f.write(COOKIES_CONTENT)
            logging.info(f"Successfully wrote cookies to {cookies_txt.name} from COOKIES_CONTENT")
        except Exception as e:
            logging.error(f"Failed to write cookies from environment: {e}")
            
    # Convert for Cobalt if txt exists
    if cookies_txt.exists():
        convert_netscape_to_json(cookies_txt, cookies_json)

    asyncio.create_task(delete_old_files())
    asyncio.create_task(zip_cleanup_worker())
    asyncio.create_task(check_premium_expiry_worker(bot))
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

    allowed = bot.dispatcher.resolve_used_update_types() if hasattr(bot, 'dispatcher') else None
    if not allowed and 'dp' in globals(): allowed = dp.resolve_used_update_types()
    await bot.set_webhook(url=webhook_url, allowed_updates=["message", "inline_query", "chosen_inline_result", "callback_query", "pre_checkout_query"])
    logging.info(f"Webhook set to {webhook_url}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("Webhook deleted")

async def zip_cleanup_worker():
    """Background worker to clean up expired ZIP files."""
    while True:
        try:
            zip_service.run_zip_cleanup_task()
        except Exception as e:
            logging.error(f"ZIP cleanup error: {e}")
        await asyncio.sleep(10800) # Run every 3 hours

async def handle_zip_download_page(request):
    """Serves the minimalistic download page for a ZIP file."""
    secure_id = request.match_info.get('secure_id')
    info = zip_service.get_zip_info(secure_id)
    
    if not info:
        return web.Response(text="<h1>404 - Link expired or not found</h1><p>Files are stored for 24 hours only.</p>", content_type='text/html', status=404)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Download Playlist</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .card {{ background: #1e293b; padding: 2.5rem; border-radius: 1rem; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); text-align: center; max-width: 400px; width: 90%; border: 1px solid #334155; }}
            h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; color: #38bdf8; }}
            p {{ color: #94a3b8; font-size: 0.875rem; margin-bottom: 2rem; }}
            .btn {{ display: inline-block; background: #38bdf8; color: #0f172a; text-decoration: none; padding: 0.75rem 2rem; border-radius: 0.5rem; font-weight: 600; transition: all 0.2s; }}
            .btn:hover {{ background: #7dd3fc; transform: translateY(-2px); }}
            .expiry {{ margin-top: 1.5rem; font-size: 0.75rem; color: #475569; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Ready to Download</h1>
            <p>{info['name']}</p>
            <a href="/dl/file/{secure_id}" class="btn">Download ZIP</a>
            <div class="expiry">Link expires in 24 hours</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def handle_zip_file_serve(request):
    """Directly serves the ZIP file."""
    secure_id = request.match_info.get('secure_id')
    info = zip_service.get_zip_info(secure_id)
    
    if not info or not info['path'].exists():
        return web.Response(text="File not found", status=404)
        
    return web.FileResponse(info['path'], headers={
        'Content-Disposition': f'attachment; filename="{info["name"]}"'
    })

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
    
    # Routes
    app.router.add_get('/dl/{secure_id}', handle_zip_download_page)
    app.router.add_get('/dl/file/{secure_id}', handle_zip_file_serve)
    
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
