import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = os.getenv("ADMIN_USERNAME")
DATABASE_URL = os.getenv("DATABASE_URL")
COOKIES_CONTENT = os.getenv("COOKIES_CONTENT")
WHITELISTED_ENV = os.getenv("WHITELISTED", "")

# Cobalt API Configuration
COBALT_API_URL = os.getenv("COBALT_API_URL", "http://localhost:9000/")
COBALT_API_KEY = os.getenv("COBALT_API_KEY", "")
USE_COBALT = os.getenv("USE_COBALT", "true").lower() == "true"

# Proxy Configuration (только для Cobalt запросов)
HTTP_PROXY = os.getenv("HTTP_PROXY", "")
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")

BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DOWNLOADS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
