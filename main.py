import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from config import BOT_TOKEN
from services.logger import setup_logging
from handlers import user, admin

async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not found in environment variables.")

    session = AiohttpSession(timeout=300)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    # Register routers
    dp.include_router(admin.router)
    dp.include_router(user.router)

    logging.info("🚀 Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
