import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = os.getenv("ADMIN_USERNAME")
DATABASE_URL = os.getenv("DATABASE_URL")
COOKIES_CONTENT = os.getenv("COOKIES_CONTENT")
WHITELISTED_ENV = os.getenv("WHITELISTED", "")
HOME_SERVER_ADDRESS = os.getenv("HOME_SERVER_ADDRESS", "localhost:50057")
TELEGRAM_API_URL = os.getenv("TELEGRAM_API_URL", "https://api.telegram.org")

# Cobalt API Configuration
USE_COBALT = os.getenv("USE_COBALT", "false").lower() == "true"
COBALT_API_URL = os.getenv("COBALT_URL") or os.getenv("COBALT_API_URL", "")
COBALT_API_KEY = os.getenv("COBALT_API_KEY", "")
HTTP_PROXY = os.getenv("HTTP_PROXY", "")
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")
SOCKS_PROXY = os.getenv("SOCKS_PROXY", "") 

# AI extractor auto-fix
AI_AUTOFIX_ENABLED = os.getenv("AI_AUTOFIX_ENABLED", "false").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DOWNLOADS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
