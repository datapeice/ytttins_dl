import asyncio
import logging
import os
import re
from pathlib import Path
import yt_dlp
import re
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Set, Tuple, Optional
import subprocess
import uuid
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters.command import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, select
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Stats and User Management
# Database Models
Base = declarative_base()

class WhitelistedUser(Base):
    __tablename__ = 'whitelisted_users'
    username = Column(String, primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)

class DownloadStat(Base):
    __tablename__ = 'download_stats'
    content_type = Column(String, primary_key=True) # 'Video' or 'Music'
    count = Column(Integer, default=0)

class ActiveUser(Base):
    __tablename__ = 'active_users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    date = Column(String) # YYYY-MM-DD

class Cookie(Base):
    __tablename__ = 'cookies'
    id = Column(Integer, primary_key=True)
    content = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)

class DownloadHistory(Base):
    __tablename__ = 'download_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    username = Column(String)
    platform = Column(String)
    content_type = Column(String)
    url = Column(String)
    title = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Stats and User Management
class Stats:
    def __init__(self):
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.users_file = self.data_dir / "users.json"
        self.stats_file = self.data_dir / "stats.json"
        
        self.db_url = os.getenv("DATABASE_URL")
        self.db_engine = None
        self.Session = None
        
        if self.db_url:
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
            try:
                self.db_engine = create_engine(self.db_url)
                Base.metadata.create_all(self.db_engine)
                self.Session = sessionmaker(bind=self.db_engine)
                logging.info("Connected to database")
            except Exception as e:
                logging.error(f"Failed to connect to database: {e}")
                self.db_engine = None
        
        # In-memory cache for fast access (sync with DB/File)
        self.downloads_count = defaultdict(int)
        self.active_users: Dict[str, Set[int]] = {}
        self.whitelisted_users = set()
        
        self._load_data()
        
    def _load_data(self):
        """Load data from DB or JSON files"""
        if self.Session:
            try:
                with self.Session() as session:
                    # Load whitelist
                    users = session.query(WhitelistedUser).all()
                    self.whitelisted_users = {u.username for u in users}
                    
                    # Load stats
                    stats = session.query(DownloadStat).all()
                    for stat in stats:
                        self.downloads_count[stat.content_type] = stat.count
                        
                    # Load active users (optional, maybe just for today?)
                    # For now, we don't load full history into memory to avoid OOM
                    # We'll query DB for stats
                    pass
            except Exception as e:
                logging.error(f"Error loading from DB: {e}")
        else:
            # File fallback
            if self.users_file.exists():
                try:
                    with open(self.users_file, 'r') as f:
                        data = json.loads(f.read())
                    self.whitelisted_users = set(data.get('whitelisted_users', []))
                except Exception as e:
                    logging.error(f"Error loading whitelist file: {e}")
                    
            if self.stats_file.exists():
                try:
                    with open(self.stats_file, 'r') as f:
                        data = json.loads(f.read())
                    self.downloads_count = defaultdict(int, data.get('downloads_count', {}))
                    active_users_data = data.get('active_users', {})
                    self.active_users = {
                        date: set(users) 
                        for date, users in active_users_data.items()
                    }
                except Exception as e:
                    logging.error(f"Error loading stats file: {e}")

    def _save_data(self):
        """Save to JSON files (only used in file mode)"""
        if self.Session:
            return

        try:
            with open(self.users_file, 'w') as f:
                json.dump({'whitelisted_users': list(self.whitelisted_users)}, f, indent=4)
                
            with open(self.stats_file, 'w') as f:
                active_users_data = {date: list(users) for date, users in self.active_users.items()}
                json.dump({
                    'downloads_count': dict(self.downloads_count),
                    'active_users': active_users_data
                }, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving data: {e}")

    def add_download(self, content_type: str, user_id: int = None, username: str = None, platform: str = None, url: str = None, title: str = None):
        self.downloads_count[content_type] += 1
        
        if self.Session:
            try:
                with self.Session() as session:
                    # Update stats
                    stat = session.query(DownloadStat).filter_by(content_type=content_type).first()
                    if not stat:
                        stat = DownloadStat(content_type=content_type, count=0)
                        session.add(stat)
                    stat.count += 1
                    
                    # Add history
                    if user_id:
                        history = DownloadHistory(
                            user_id=user_id,
                            username=username,
                            platform=platform,
                            content_type=content_type,
                            url=url,
                            title=title
                        )
                        session.add(history)
                    
                    session.commit()
            except Exception as e:
                logging.error(f"Error saving download stat/history to DB: {e}")
        else:
            self._save_data()
        
    def add_to_whitelist(self, username: str) -> bool:
        if username in self.whitelisted_users:
            return False
        self.whitelisted_users.add(username)
        
        if self.Session:
            try:
                with self.Session() as session:
                    if not session.query(WhitelistedUser).filter_by(username=username).first():
                        session.add(WhitelistedUser(username=username))
                        session.commit()
            except Exception as e:
                logging.error(f"Error adding to whitelist DB: {e}")
        else:
            self._save_data()
        return True
        
    def remove_from_whitelist(self, username: str, full_removal: bool = True) -> bool:
        if username not in self.whitelisted_users:
            return False
        self.whitelisted_users.remove(username)
        
        if self.Session:
            try:
                with self.Session() as session:
                    session.query(WhitelistedUser).filter_by(username=username).delete()
                    session.commit()
            except Exception as e:
                logging.error(f"Error removing from whitelist DB: {e}")
        else:
            self._save_data()
        return True
        
    def is_whitelisted(self, username: str) -> bool:
        return username in self.whitelisted_users
    
    def add_active_user(self, user_id: int):
        today = datetime.now().date().isoformat()
        
        if self.Session:
            try:
                with self.Session() as session:
                    # Check if entry exists for today
                    exists = session.query(ActiveUser).filter_by(user_id=user_id, date=today).first()
                    if not exists:
                        session.add(ActiveUser(user_id=user_id, date=today))
                        session.commit()
            except Exception as e:
                logging.error(f"Error adding active user to DB: {e}")
        else:
            if today not in self.active_users:
                self.active_users[today] = set()
            self.active_users[today].add(user_id)
            self._save_data()
    
    def get_weekly_stats(self):
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        if self.Session:
            try:
                with self.Session() as session:
                    # Get download counts
                    video_stat = session.query(DownloadStat).filter_by(content_type='Video').first()
                    audio_stat = session.query(DownloadStat).filter_by(content_type='Music').first()
                    total_video = video_stat.count if video_stat else 0
                    total_audio = audio_stat.count if audio_stat else 0
                    
                    # Get active users count (distinct user_ids in last 7 days)
                    # Note: date is stored as string YYYY-MM-DD
                    week_ago_str = week_ago.isoformat()
                    active_count = session.query(func.count(func.distinct(ActiveUser.user_id)))\
                        .filter(ActiveUser.date >= week_ago_str).scalar()
                        
                    # Get list of active users for display
                    active_users_query = session.query(func.distinct(ActiveUser.user_id))\
                        .filter(ActiveUser.date >= week_ago_str).all()
                    active_users = {u[0] for u in active_users_query}
                    
                    return {
                        'video_count': total_video,
                        'audio_count': total_audio,
                        'active_users_count': active_count,
                        'active_users': active_users
                    }
            except Exception as e:
                logging.error(f"Error getting stats from DB: {e}")
                return {'video_count': 0, 'audio_count': 0, 'active_users_count': 0, 'active_users': set()}
        else:
            # File fallback
            total_video = self.downloads_count['Video']
            total_audio = self.downloads_count['Music']
            
            active_users = set()
            for date_str, users in list(self.active_users.items()):
                date = datetime.fromisoformat(date_str).date()
                if date >= week_ago:
                    active_users.update(users)
                elif date < week_ago:
                    del self.active_users[date_str]
                    self._save_data()
                    
            return {
                'video_count': total_video,
                'audio_count': total_audio,
                'active_users_count': len(active_users),
                'active_users': active_users
            }

# Initialize stats
stats = Stats()

# Load environment variables
load_dotenv()

# Configure logging
# Ensure logs directory exists
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

# Create logger for user downloads
download_logger = logging.getLogger('download_tracker')
download_logger.setLevel(logging.INFO)
download_handler = logging.FileHandler('logs/downloads.log')
download_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
download_logger.addHandler(download_handler)

# Initialize bot with token from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables. Check your .env file.")

# Admin user ID from environment variables
ADMIN_USER_ID = os.getenv("ADMIN_USERNAME")
if not ADMIN_USER_ID:
    raise ValueError("ADMIN_USERNAME not found in environment variables. Check your .env file.")
    
# Initialize bot with custom timeout
session = AiohttpSession(timeout=300) # 5 minutes timeout
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

# Create downloads directory
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Create data directory
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# URL Cache for callback data (to avoid 64 byte limit)
# {request_id: url}
url_cache: Dict[str, str] = {}

# Write cookies from env var if present

# Write cookies from env var if present
if os.getenv("COOKIES_CONTENT"):
    cookies_path = DATA_DIR / "cookies.txt"
    with open(cookies_path, "w") as f:
        f.write(os.getenv("COOKIES_CONTENT"))
    logging.info("Cookies loaded from environment variable")

# Load cookies from DB if available (overrides env var if DB has newer)
if stats.Session:
    try:
        with stats.Session() as session:
            cookie = session.query(Cookie).order_by(Cookie.updated_at.desc()).first()
            if cookie:
                cookies_path = DATA_DIR / "cookies.txt"
                with open(cookies_path, "w") as f:
                    f.write(cookie.content)
                logging.info("Cookies loaded from database")
    except Exception as e:
        logging.error(f"Error loading cookies from DB: {e}")

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

def get_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    else:
        return "unknown"

def get_video_metadata(file_path: Path) -> Dict[str, int]:
    """Extract video metadata using ffprobe"""
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height,duration", 
            "-of", "json", 
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        
        if not data.get('streams'):
            logging.warning(f"No streams found in metadata for {file_path}")
            return {'width': 0, 'height': 0, 'duration': 0}
            
        stream = data['streams'][0]
        meta = {
            'width': int(stream.get('width', 0)),
            'height': int(stream.get('height', 0)),
            'duration': int(float(stream.get('duration', 0)))
        }
        logging.info(f"Extracted metadata for {file_path}: {meta}")
        return meta
    except Exception as e:
        logging.error(f"Error getting metadata for {file_path}: {e}")
        return {'width': 0, 'height': 0, 'duration': 0}

def resize_thumbnail(input_path: Path) -> Optional[Path]:
    """Resize thumbnail to max 320px width/height and convert to JPG"""
    try:
        output_path = input_path.with_suffix('.jpg')
        # If it's already jpg and we are resizing, we might overwrite or use a temp name.
        # Let's just overwrite for simplicity or use a suffix.
        if output_path == input_path:
            output_path = input_path.parent / f"{input_path.stem}_thumb.jpg"
            
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", "scale='min(320,iw)':-1", # Scale width to min(320, original_width), keep aspect ratio
            "-q:v", "2", # Good quality jpg
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        if output_path.exists():
            return output_path
        return None
    except Exception as e:
        logging.error(f"Error resizing thumbnail {input_path}: {e}")
        return None

async def download_media(url: str, is_music: bool = False, video_height: int = None) -> Tuple[Path, Optional[Path], Dict]:
    output_template = str(DOWNLOADS_DIR / "%(title)s.%(ext)s")
    
    # Check for cookies file
    cookie_file = DATA_DIR / "cookies.txt"
    if not cookie_file.exists():
        cookie_file = "cookies.txt" if os.path.exists("cookies.txt") else None
    
    # Construct format string based on height preference
    if is_music:
        format_str = 'bestaudio/best'
    elif video_height:
        # Try to get specific height, fallback to best
        format_str = f'bestvideo[height<={video_height}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4][vcodec^=avc]/best[ext=mp4]/best'
    else:
        format_str = 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4][vcodec^=avc]/best[ext=mp4]/best'

    ydl_opts = {
        'format': format_str,
        'outtmpl': output_template,
        'restrictfilenames': True,
        'noplaylist': True,
        'extract_audio': is_music,
        'writethumbnail': True,
        'cookiefile': cookie_file,
        'postprocessors': [],
    }
    
    if is_music:
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        })
    else:
        # Convert thumbnail to jpg for better compatibility
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegThumbnailsConvertor',
            'format': 'jpg',
        })
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if is_music:
                filename = str(Path(filename).with_suffix('.mp3'))
            
            # Find thumbnail
            thumbnail_path = None
            base_path = Path(filename)
            # Prioritize jpg
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                thumb_check = base_path.with_suffix(ext)
                if thumb_check.exists():
                    thumbnail_path = thumb_check
                    break
            
            # Resize/Convert thumbnail if found
            if thumbnail_path:
                resized_thumb = resize_thumbnail(thumbnail_path)
                if resized_thumb:
                    # If we created a new file, maybe delete the old one if it wasn't the same
                    if resized_thumb != thumbnail_path:
                        try:
                            thumbnail_path.unlink()
                        except:
                            pass
                    thumbnail_path = resized_thumb
                    
            # Get video metadata
            if is_music:
                metadata = {
                    'width': 0,
                    'height': 0,
                    'duration': int(info.get('duration') or 0)
                }
            else:
                # Use ffprobe for accurate video metadata
                metadata = get_video_metadata(Path(filename))
                # Fallback to yt-dlp info if ffprobe failed
                if metadata['duration'] == 0:
                    metadata['duration'] = int(info.get('duration') or 0)
                if metadata['width'] == 0:
                    metadata['width'] = int(info.get('width') or 0)
                if metadata['height'] == 0:
                    metadata['height'] = int(info.get('height') or 0)
                    
            return Path(filename), thumbnail_path, metadata
    except Exception as e:
        logging.error(f"Error downloading {url}: {str(e)}")
        raise

# Command handler for /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Hello! Send me a link to download video from:\n"
        "- YouTube\n"
        "- YouTube Music (will download as MP3)\n"
        "- TikTok\n"
        "- Instagram"
    )

# Handle incoming URLs
@dp.message(lambda m: m.text and not m.text.startswith(('/start', '/panel', '/whitelist', '/unwhitelist', 'add @')))
async def handle_url(message: types.Message):
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+|youtube\.com|youtu\.be|tiktok\.com|instagram\.com'
    
    if not re.search(url_pattern, message.text):
        await message.answer("Please send a valid URL from YouTube, TikTok, or Instagram.")
        return

    try:
        platform = get_platform(message.text)
        if platform == "unknown":
            await message.answer("Sorry, this platform is not supported.")
            return

        if platform == "youtube" and not is_youtube_music(message.text):
            # Generate request ID to avoid callback data limit
            request_id = str(uuid.uuid4())[:8]
            url_cache[request_id] = message.text
            
            # Create inline keyboard for YouTube format selection
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"format:audio:{request_id}"),
                InlineKeyboardButton(text="🎥 Video", callback_data=f"format:video:{request_id}")
            )
            await message.answer("Choose download format:", reply_markup=builder.as_markup())
            return

        status_message = await message.answer("Processing your request... ⏳")
        is_music = is_youtube_music(message.text)
        file_path, thumbnail_path, metadata = await download_media(message.text, is_music)

        # Track statistics
        stats.add_active_user(message.from_user.id)
        stats.add_download(
            content_type='Music' if is_music else 'Video',
            user_id=message.from_user.id,
            username=message.from_user.username or "No username",
            platform=platform,
            url=message.text,
            title=file_path.stem
        )

        # Log the download
        user_fullname = message.from_user.full_name
        username = message.from_user.username or "No username"
        user_id = message.from_user.id
        download_logger.info(
            f"User: {user_fullname} (@{username}, ID: {user_id}) | "
            f"Platform: {platform} | "
            f"Type: {'Music' if is_music else 'Video'} | "
            f"URL: {message.text}"
        )

        # Send the file
        if file_path.exists():
            await status_message.edit_text("Uploading to Telegram... 📤")
            
            if is_music:
                if thumbnail_path:
                    await message.answer_audio(
                        types.FSInputFile(file_path), 
                        thumbnail=types.FSInputFile(thumbnail_path),
                        duration=metadata.get('duration')
                    )
                else:
                    await message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=metadata.get('duration')
                    )
            else:
                video_kwargs = {
                    'video': types.FSInputFile(file_path),
                    'duration': metadata.get('duration'),
                    'width': metadata.get('width'),
                    'height': metadata.get('height'),
                    'supports_streaming': True
                }
                
                # if thumbnail_path:
                #    video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                logging.info(f"Sending video with kwargs: {video_kwargs}")
                await message.answer_video(**video_kwargs)
            
            # Clean up
            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists():
                thumbnail_path.unlink()
            await status_message.delete()
        else:
            await status_message.edit_text("Sorry, something went wrong during download.")
    
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        if 'status_message' in locals():
            await status_message.edit_text(f"Sorry, an error occurred: {str(e)}")
        else:
            await message.answer(f"Sorry, an error occurred: {str(e)}")

# Admin commands for whitelist management
@dp.message(Command("whitelist"))
async def cmd_whitelist_add(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to manage the whitelist.")
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer("Usage: /whitelist <username> - Add a user to whitelist")
        return
        
    username = args[0].lstrip('@')
    if stats.add_to_whitelist(username):
        await message.answer(f"✅ User @{username} has been added to the whitelist.")
    else:
        await message.answer(f"⚠️ User @{username} is already in the whitelist.")

@dp.message(Command("unwhitelist"))
async def cmd_whitelist_remove(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to manage the whitelist.")
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer("Usage: /unwhitelist <username> - Remove a user from whitelist")
        return
        
    username = args[0].lstrip('@')
    if stats.remove_from_whitelist(username):
        await message.answer(f"✅ User @{username} has been removed from the whitelist.")
    else:
        await message.answer(f"⚠️ User @{username} is not in the whitelist.")

# Admin panel command
def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin:back")]
    ])



@dp.message(Command("panel"))
async def send_admin_panel(message: types.Message):
    # Check if user is admin
    if message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to access the admin panel.")
        return

    # Get weekly statistics
    weekly_stats = stats.get_weekly_stats()
    
    # Get yt-dlp version
    try:
        ytdlp_version = yt_dlp.version.__version__
    except:
        ytdlp_version = "Unknown"
    
    # Format the message
    stats_message = (
        "📊 Weekly Statistics:\n\n"
        f"📥 Downloads:\n"
        f"   📹 Videos: {weekly_stats['video_count']}\n"
        f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
        f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n\n"
        f"📝 Whitelisted Users:\n"
        f"{', '.join(['@' + user for user in stats.whitelisted_users]) if stats.whitelisted_users else 'No whitelisted users'}\n\n"
        f"🔧 Version: yt-dlp {ytdlp_version}\n\n"
    )

    # Create admin control buttons
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Users List", callback_data="admin:users")],
        [InlineKeyboardButton(text="➕ Add User", callback_data="admin:add_user"),
         InlineKeyboardButton(text="➖ Remove User", callback_data="admin:remove_user")],
        [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
         InlineKeyboardButton(text="📜 History", callback_data="admin:history")],
        [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
         InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs")],
        [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
    ])
    
    # Add active users list
    if weekly_stats['active_users']:
        user_list = []
        for user_id in weekly_stats['active_users']:
            try:
                user = await bot.get_chat(user_id)
                username = user.username or "No username"
                user_list.append(f"@{username}")
            except Exception:
                user_list.append(f"User {user_id}")
        
        stats_message += "Active Users List:\n"
        stats_message += "\n".join(user_list)
    else:
        stats_message += "No active users in the last 7 days."

    await message.answer(stats_message, reply_markup=keyboard)

# Handle admin panel callbacks
@dp.callback_query(F.data.startswith("admin:"))
async def handle_admin_callback(callback: types.CallbackQuery):
    if callback.from_user.username != ADMIN_USER_ID:
        await callback.answer("You don't have permission to use these controls.", show_alert=True)
        return

    # Remove "admin:" prefix
    action = callback.data.replace("admin:", "", 1)
    
    if action == "whitelist_add":
        await callback.message.answer("Please send the username to add to whitelist in format:\n`add @username`")
    elif action == "whitelist_remove":
        if not stats.whitelisted_users:
            await callback.message.answer("The whitelist is empty.")
            await callback.answer()
            return
            
        # Create buttons for each whitelisted user
        builder = InlineKeyboardBuilder()
        for username in stats.whitelisted_users:
            builder.add(InlineKeyboardButton(
                text=f"❌ @{username}",
                callback_data=f"admin:remove:{username}"
            ))
        builder.adjust(1)  # One button per row
        await callback.message.answer("Select user to remove from whitelist:", reply_markup=builder.as_markup())
    elif action.startswith("remove:"):
        username = action.split(":", 1)[1]
        if stats.remove_from_whitelist(username):
            # Edit the message to show deletion confirmation
            await callback.message.edit_text(f"✅ User @{username} has been deleted from the whitelist.")
        else:
            await callback.message.answer(f"⚠️ User @{username} is not in the whitelist.")
            await callback.answer(show_alert=True)
    elif action == "update_ytdlp":
        # Send initial message
        status_msg = await callback.message.answer("```\n🔄 Starting yt-dlp update...\n```", parse_mode="Markdown")
        try:
            import subprocess
            
            # Update status
            await status_msg.edit_text("```\n🔄 Starting yt-dlp update...\n⏳ Running pip install --upgrade yt-dlp\n```", parse_mode="Markdown")
            
            result = subprocess.run(
                ["pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # Get new version
                try:
                    import importlib
                    importlib.reload(yt_dlp.version)
                    new_version = yt_dlp.version.__version__
                except:
                    new_version = "Unknown"
                
                await status_msg.edit_text(
                    f"```\n✅ yt-dlp successfully updated!\n📦 Version: {new_version}\n```",
                    parse_mode="Markdown"
                )
            else:
                error_output = result.stderr[:400] if result.stderr else "Unknown error"
                await status_msg.edit_text(
                    f"```\n❌ Update failed!\n\nError:\n{error_output}\n```",
                    parse_mode="Markdown"
                )
        except Exception as e:
            await status_msg.edit_text(
                f"```\n❌ Update error!\n\nException:\n{str(e)[:400]}\n```",
                parse_mode="Markdown"
            )

    elif action == "update_cookies":
        await callback.message.answer("Please send the `cookies.txt` file now.")
        
    elif action == "history":
        if stats.Session:
            try:
                with stats.Session() as session:
                    history = session.query(DownloadHistory).order_by(DownloadHistory.timestamp.desc()).limit(10).all()
                    if not history:
                        text = "📜 *Download History (Last 10)*\n\nNo downloads recorded yet."
                    else:
                        text = "📜 *Download History (Last 10)*\n\n"
                        for h in history:
                            text += f"👤 {h.username} (ID: {h.user_id})\n"
                            text += f"📹 {h.title}\n"
                            text += f"🔗 {h.url}\n"
                            text += f"📅 {h.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            text += "-------------------\n"
            except Exception as e:
                logging.error(f"Error fetching history: {e}")
                text = "❌ Error fetching history."
        else:
            # Fallback to reading logs/downloads.log for history
            log_file = Path("logs/downloads.log")
            if log_file.exists():
                try:
                    # Read last 10 lines
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                    last_lines = lines[-10:]
                    if not last_lines:
                        text = "📜 *Download History (Last 10)*\n\nNo downloads recorded yet."
                    else:
                        text = "📜 *Download History (Last 10)*\n\n"
                        for line in reversed(last_lines):
                            # Parse log line: "YYYY-MM-DD HH:MM:SS,mmm - User: ... | URL: ..."
                            # This is a bit fragile but better than nothing
                            text += f"{line.strip()}\n"
                            text += "-------------------\n"
                except Exception as e:
                    logging.error(f"Error reading history log: {e}")
                    text = "❌ Error reading history log."
            else:
                text = "❌ History log not found."
            
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif action == "back":
        # Go back to main admin panel
        # Get weekly statistics
        weekly_stats = stats.get_weekly_stats()
        
        # Get yt-dlp version
        try:
            ytdlp_version = yt_dlp.version.__version__
        except:
            ytdlp_version = "Unknown"
        
        # Format the message
        stats_message = (
            "📊 Weekly Statistics:\n\n"
            f"📥 Downloads:\n"
            f"   📹 Videos: {weekly_stats['video_count']}\n"
            f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
            f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n\n"
            f"📝 Whitelisted Users:\n"
            f"{', '.join(['@' + user for user in stats.whitelisted_users]) if stats.whitelisted_users else 'No whitelisted users'}\n\n"
            f"🔧 Version: yt-dlp {ytdlp_version}\n\n"
        )

        # Create admin control buttons
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Users List", callback_data="admin:users")],
            [InlineKeyboardButton(text="➕ Add User", callback_data="admin:add_user"),
             InlineKeyboardButton(text="➖ Remove User", callback_data="admin:remove_user")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
             InlineKeyboardButton(text="📜 History", callback_data="admin:history")],
            [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
             InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs")],
            [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
        ])
        
        # Add active users list
        if weekly_stats['active_users']:
            user_list = []
            for user_id in weekly_stats['active_users']:
                try:
                    user = await bot.get_chat(user_id)
                    username = user.username or "No username"
                    user_list.append(f"@{username}")
                except Exception:
                    user_list.append(f"User {user_id}")
            
            stats_message += "Active Users List:\n"
            stats_message += "\n".join(user_list)
        else:
            stats_message += "No active users in the last 7 days."

        await callback.message.edit_text(stats_message, reply_markup=keyboard)

    elif action == "stats":
        # Refresh stats - just call send_admin_panel again but we need to edit instead of answer
        # Since send_admin_panel uses message.answer, we need to duplicate logic or refactor properly.
        # But user asked to revert, so I will revert to calling send_admin_panel which might create a new message
        # OR I can just copy the logic here to edit.
        
        # Get weekly statistics
        weekly_stats = stats.get_weekly_stats()
        
        # Get yt-dlp version
        try:
            ytdlp_version = yt_dlp.version.__version__
        except:
            ytdlp_version = "Unknown"
        
        # Format the message
        stats_message = (
            "📊 Weekly Statistics:\n\n"
            f"📥 Downloads:\n"
            f"   📹 Videos: {weekly_stats['video_count']}\n"
            f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
            f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n\n"
            f"📝 Whitelisted Users:\n"
            f"{', '.join(['@' + user for user in stats.whitelisted_users]) if stats.whitelisted_users else 'No whitelisted users'}\n\n"
            f"🔧 Version: yt-dlp {ytdlp_version}\n\n"
        )

        # Create admin control buttons
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Users List", callback_data="admin:users")],
            [InlineKeyboardButton(text="➕ Add User", callback_data="admin:add_user"),
             InlineKeyboardButton(text="➖ Remove User", callback_data="admin:remove_user")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
             InlineKeyboardButton(text="📜 History", callback_data="admin:history")],
            [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
             InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs")],
            [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
        ])
        
        # Add active users list
        if weekly_stats['active_users']:
            user_list = []
            for user_id in weekly_stats['active_users']:
                try:
                    user = await bot.get_chat(user_id)
                    username = user.username or "No username"
                    user_list.append(f"@{username}")
                except Exception:
                    user_list.append(f"User {user_id}")
            
            stats_message += "Active Users List:\n"
            stats_message += "\n".join(user_list)
        else:
            stats_message += "No active users in the last 7 days."

        try:
            await callback.message.edit_text(stats_message, reply_markup=keyboard)
        except Exception:
            await callback.answer("Stats are up to date.")

    elif action == "get_logs":
        log_file = Path("logs/bot.log")
        if log_file.exists() and log_file.stat().st_size > 0:
            await callback.message.answer_document(types.FSInputFile(log_file), caption="📂 Bot Logs")
        else:
            await callback.message.answer("❌ Log file is empty or not found.")
        await callback.answer()

    elif action == "close":
        # This action is for the 'Close' button on the admin panel.
        # If there's a pending cookie upload, clean up the temporary file.
        if tmp_file.exists():
            tmp_file.unlink()
        await callback.message.edit_text("Admin panel closed.") # Or delete the message
        
    await callback.answer()

# Handle cookie file upload
@dp.message(F.document)
async def handle_document(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        return

    if message.document.file_name == "cookies.txt":
        try:
            file_id = message.document.file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            
            # Save as temporary file
            destination = DATA_DIR / "cookies.txt.tmp"
            await bot.download_file(file_path, destination)
            
            # Ask for confirmation
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="✅ Confirm", callback_data="cookie:confirm"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="cookie:cancel")
            )
            
            await message.answer(
                "⚠️ **Confirmation Required**\n\n"
                "You are about to overwrite the existing `cookies.txt`. "
                "This action cannot be undone.\n\n"
                "Do you want to proceed?",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logging.error(f"Error uploading cookies: {e}")
            await message.answer(f"❌ Error uploading cookies: {str(e)}")
    else:
        # Ignore other documents or tell user it's wrong file
        pass

# Handle cookie confirmation callbacks
@dp.callback_query(F.data.startswith("cookie:"))
async def handle_cookie_callback(callback: types.CallbackQuery):
    if callback.from_user.username != ADMIN_USER_ID:
        await callback.answer("You don't have permission.", show_alert=True)
        return
        
    action = callback.data.split(":")[1]
    tmp_file = DATA_DIR / "cookies.txt.tmp"
    target_file = DATA_DIR / "cookies.txt"
    
    if action == "confirm":
        if tmp_file.exists():
            try:
                # Save to DB if available
                if stats.Session:
                    try:
                        with open(tmp_file, 'r') as f:
                            content = f.read()
                        with stats.Session() as session:
                            session.query(Cookie).delete() # Keep only latest
                            session.add(Cookie(content=content))
                            session.commit()
                    except Exception as e:
                        logging.error(f"Error saving cookies to DB: {e}")

                # Rename tmp file to actual file (overwrite)
                tmp_file.replace(target_file)
                await callback.message.edit_text("✅ `cookies.txt` has been updated successfully!", parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Error applying cookies: {e}")
                await callback.message.edit_text(f"❌ Error applying cookies: {str(e)}")
        else:
            await callback.message.edit_text("❌ Temporary file not found. Please upload again.")
            
    elif action == "cancel":
        if tmp_file.exists():
            tmp_file.unlink()
        await callback.message.edit_text("❌ Operation cancelled. `cookies.txt` was not modified.", parse_mode="Markdown")
    
    await callback.answer()

# Handle whitelist additions via text
@dp.message(lambda message: message.text and message.text.lower().startswith("add @"))
async def handle_whitelist_add(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to manage the whitelist.")
        return

    username = message.text[5:].strip()  # Remove "add @" prefix
    if stats.add_to_whitelist(username):
        await message.answer(f"✅ User @{username} has been added to the whitelist.")
        # Update the admin panel message with updated whitelist
        await cmd_admin_panel(message)
    else:
        await message.answer(f"⚠️ User @{username} is already in the whitelist.")

# Handle format selection callback
@dp.callback_query(F.data.startswith("format:"))
async def handle_format_selection(callback: types.CallbackQuery):
    try:
        # Answer callback query immediately to prevent timeout
        await callback.answer()
        
        _, format_type, request_id = callback.data.split(":", 2)
        
        # Retrieve URL from cache
        url = url_cache.get(request_id)
        if not url:
            await callback.message.edit_text("⚠️ Request expired. Please send the link again.")
            return

        if format_type == "video":
            # Show resolution options
            builder = InlineKeyboardBuilder()
            resolutions = [("1080p", 1080), ("720p", 720), ("480p", 480), ("360p", 360)]
            
            for label, height in resolutions:
                builder.add(InlineKeyboardButton(
                    text=label, 
                    callback_data=f"dl_res:{request_id}:{height}"
                ))
            builder.adjust(2) # 2 buttons per row
            
            await callback.message.edit_text("Select video quality:", reply_markup=builder.as_markup())
            return

        # Audio download
        status_message = await callback.message.edit_text("Processing your request... ⏳")
        
        try:
            is_music = True
            file_path, thumbnail_path, metadata = await download_media(url, is_music)

            # Track statistics
            stats.add_active_user(callback.from_user.id)
            stats.add_download(
                content_type='Music',
                user_id=callback.from_user.id,
                username=callback.from_user.username or "No username",
                platform='youtube',
                url=url,
                title=file_path.stem
            )

            # Log the download
            user_fullname = callback.from_user.full_name
            username = callback.from_user.username or "No username"
            user_id = callback.from_user.id
            download_logger.info(
                f"User: {user_fullname} (@{username}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: Audio | "
                f"URL: {url}"
            )

            # Send the file
            if file_path.exists():
                await status_message.edit_text("Uploading to Telegram... 📤")
                
                if thumbnail_path:
                    await callback.message.answer_audio(
                        types.FSInputFile(file_path), 
                        thumbnail=types.FSInputFile(thumbnail_path),
                        duration=metadata.get('duration')
                    )
                else:
                    await callback.message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=metadata.get('duration')
                    )
                
                # Clean up
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                await status_message.delete()
            else:
                await status_message.edit_text("Sorry, something went wrong during download.")

        except Exception as e:
            logging.error(f"Error: {str(e)}")
            await status_message.edit_text(f"Sorry, an error occurred: {str(e)}")

    except Exception as e:
        logging.error(f"Error in callback handling: {str(e)}")
        try:
            await callback.message.answer("Sorry, this request has expired. Please try again.")
        except Exception:
            pass

# Handle resolution selection callback
@dp.callback_query(F.data.startswith("dl_res:"))
async def handle_resolution_selection(callback: types.CallbackQuery):
    try:
        await callback.answer()
        
        _, request_id, height = callback.data.split(":", 2)
        
        # Retrieve URL from cache
        url = url_cache.get(request_id)
        if not url:
            await callback.message.edit_text("⚠️ Request expired. Please send the link again.")
            return

        status_message = await callback.message.edit_text(f"Downloading video ({height}p)... ⏳")
        
        try:
            file_path, thumbnail_path, metadata = await download_media(url, is_music=False, video_height=int(height))

            # Track statistics
            stats.add_active_user(callback.from_user.id)
            stats.add_download(
                content_type='Video',
                user_id=callback.from_user.id,
                username=callback.from_user.username or "No username",
                platform='youtube',
                url=url,
                title=file_path.stem
            )

            # Log the download
            user_fullname = callback.from_user.full_name
            username = callback.from_user.username or "No username"
            user_id = callback.from_user.id
            download_logger.info(
                f"User: {user_fullname} (@{username}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: Video ({height}p) | "
                f"URL: {url}"
            )

            # Send the file
            if file_path.exists():
                await status_message.edit_text("Uploading to Telegram... 📤")
                
                video_kwargs = {
                    'video': types.FSInputFile(file_path),
                    'duration': metadata.get('duration'),
                    'width': metadata.get('width'),
                    'height': metadata.get('height'),
                    'supports_streaming': True
                }
                
                # if thumbnail_path:
                #    video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                logging.info(f"Sending video with kwargs: {video_kwargs}")
                await callback.message.answer_video(**video_kwargs)
                
                # Clean up
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                await status_message.delete()
            else:
                await status_message.edit_text("Sorry, something went wrong during download.")

        except Exception as e:
            logging.error(f"Error: {str(e)}")
            await status_message.edit_text(f"Sorry, an error occurred: {str(e)}")

    except Exception as e:
        logging.error(f"Error in resolution callback: {str(e)}")

# Main function to start the bot
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
