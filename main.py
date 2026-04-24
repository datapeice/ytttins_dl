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

async def handle_landing_page(request):
    """Beautiful landing page for bot.datapeice.me."""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YTTTINS DL Bot</title>
    <meta name="description" content="A powerful Telegram bot for downloading media from YouTube, Instagram, TikTok, and 1800+ other platforms.">
    <meta property="og:title" content="YTTTINS DL Bot">
    <meta property="og:description" content="Download media from YouTube, Instagram, TikTok & more — right in Telegram.">
    <meta property="og:type" content="website">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0a0a0f;
            --surface: #12121a;
            --border: rgba(255,255,255,0.06);
            --text: #e4e4ed;
            --text-muted: #6b6b80;
            --accent: #6c63ff;
            --accent-glow: rgba(108,99,255,0.25);
            --tg-blue: #2AABEE;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }
        /* Animated gradient orbs */
        .orb {
            position: absolute;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.35;
            animation: float 12s ease-in-out infinite;
            pointer-events: none;
        }
        .orb-1 { width: 400px; height: 400px; background: #6c63ff; top: -10%; left: -5%; animation-delay: 0s; }
        .orb-2 { width: 350px; height: 350px; background: #2AABEE; bottom: -10%; right: -5%; animation-delay: -4s; }
        .orb-3 { width: 200px; height: 200px; background: #e040fb; top: 50%; left: 60%; animation-delay: -8s; }
        @keyframes float {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(30px, -20px) scale(1.05); }
            66% { transform: translate(-20px, 15px) scale(0.95); }
        }
        .container {
            position: relative;
            z-index: 1;
            text-align: center;
            padding: 2rem;
            max-width: 520px;
            width: 100%;
        }
        .logo-ring {
            width: 100px; height: 100px;
            margin: 0 auto 2rem;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--accent), var(--tg-blue));
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 0 40px var(--accent-glow), 0 0 80px rgba(42,171,238,0.15);
            animation: pulse-ring 3s ease-in-out infinite;
        }
        @keyframes pulse-ring {
            0%, 100% { box-shadow: 0 0 40px var(--accent-glow), 0 0 80px rgba(42,171,238,0.15); }
            50% { box-shadow: 0 0 60px var(--accent-glow), 0 0 120px rgba(42,171,238,0.25); }
        }
        .logo-ring svg { width: 48px; height: 48px; fill: white; }
        h1 {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .tagline {
            font-size: 1rem;
            color: var(--text-muted);
            font-weight: 400;
            margin-bottom: 2.5rem;
            line-height: 1.6;
        }
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(20px);
        }
        .features {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            text-align: left;
            margin-bottom: 0;
        }
        .feature {
            display: flex;
            align-items: flex-start;
            gap: 0.6rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        .feature-icon {
            font-size: 1.1rem;
            flex-shrink: 0;
            margin-top: 1px;
        }
        .feature strong { color: var(--text); font-weight: 500; }
        .cta-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.6rem;
            background: linear-gradient(135deg, var(--tg-blue), #229ED9);
            color: white;
            text-decoration: none;
            padding: 0.9rem 2.2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 20px rgba(42,171,238,0.3);
            letter-spacing: 0.01em;
        }
        .cta-btn:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 8px 30px rgba(42,171,238,0.45);
        }
        .cta-btn svg { width: 20px; height: 20px; fill: currentColor; }
        .status {
            margin-top: 2rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            color: var(--text-muted);
        }
        .status-dot {
            width: 8px; height: 8px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 8px rgba(34,197,94,0.6);
            animation: blink 2s ease-in-out infinite;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }
        .footer {
            margin-top: 2.5rem;
            font-size: 0.7rem;
            color: var(--text-muted);
            opacity: 0.5;
        }
        @media (max-width: 480px) {
            h1 { font-size: 1.6rem; }
            .features { grid-template-columns: 1fr; }
            .card { padding: 1.5rem; }
        }
    </style>
</head>
<body>
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>

    <div class="container">
        <div class="logo-ring">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>
        </div>

        <h1>YTTTINS DL Bot</h1>
        <p class="tagline">A powerful media downloader running on this server.<br>Send any link — get your file in seconds.</p>

        <div class="card">
            <div class="features">
                <div class="feature">
                    <span class="feature-icon">🎬</span>
                    <div><strong>YouTube</strong><br>Videos & Music</div>
                </div>
                <div class="feature">
                    <span class="feature-icon">📸</span>
                    <div><strong>Instagram</strong><br>Reels & Stories</div>
                </div>
                <div class="feature">
                    <span class="feature-icon">🎵</span>
                    <div><strong>TikTok</strong><br>No watermark</div>
                </div>
                <div class="feature">
                    <span class="feature-icon">🌐</span>
                    <div><strong>1800+ Sites</strong><br>Powered by yt-dlp</div>
                </div>
            </div>
        </div>

        <a href="https://t.me/ytttinsdl_bot" class="cta-btn" target="_blank" rel="noopener">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.03-1.99 1.27-5.62 3.72-.53.36-1.01.54-1.44.53-.47-.01-1.38-.27-2.06-.49-.83-.27-1.49-.42-1.43-.88.03-.24.37-.49 1.02-.74 3.99-1.74 6.65-2.89 7.99-3.44 3.8-1.58 4.59-1.86 5.1-1.87.11 0 .37.03.54.17.14.12.18.28.2.45-.01.06.01.24 0 .38z"/></svg>
            Open in Telegram
        </a>

        <div class="status">
            <span class="status-dot"></span>
            Bot is online and ready
        </div>

        <div class="footer">bot.datapeice.me</div>
    </div>
</body>
</html>
"""
    return web.Response(text=html, content_type='text/html')

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
    app.router.add_get('/', handle_landing_page)
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
