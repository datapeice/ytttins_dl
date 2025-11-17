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
from typing import Dict, Set
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Stats and User Management
class Stats:
    def __init__(self):
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.users_file = self.data_dir / "users.json"
        self.stats_file = self.data_dir / "stats.json"
        
        # Initialize with empty data
        self.downloads_count = defaultdict(int)  # {type: count}
        self.active_users: Dict[str, Set[int]] = {}  # {date: set(user_ids)}
        self.whitelisted_users = set()
        
        # Load saved data
        self._load_data()
        
    def _load_data(self):
        """Load all data from JSON files"""
        # Load whitelist
        if self.users_file.exists():
            try:
                with open(self.users_file, 'r') as f:
                    data = json.loads(f.read())
                self.whitelisted_users = set(data.get('whitelisted_users', []))
            except Exception as e:
                logging.error(f"Error loading whitelist: {e}")
                
        # Load stats
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.loads(f.read())
                self.downloads_count = defaultdict(int, data.get('downloads_count', {}))
                
                # Convert date strings back to datetime objects for active_users
                active_users_data = data.get('active_users', {})
                self.active_users = {
                    date: set(users) 
                    for date, users in active_users_data.items()
                }
            except Exception as e:
                logging.error(f"Error loading stats: {e}")
                
    def _save_data(self):
        """Save all data to JSON files"""
        # Save whitelist
        try:
            logging.info(f"Saving whitelist to {self.users_file}: {list(self.whitelisted_users)}")
            with open(self.users_file, 'w') as f:
                json.dump({
                    'whitelisted_users': list(self.whitelisted_users)
                }, f, indent=4)
            logging.info(f"Whitelist saved successfully")
        except Exception as e:
            logging.error(f"Error saving whitelist: {e}")
            
        # Save stats
        try:
            with open(self.stats_file, 'w') as f:
                # Convert active_users sets to lists for JSON serialization
                active_users_data = {
                    date: list(users)
                    for date, users in self.active_users.items()
                }
                
                json.dump({
                    'downloads_count': dict(self.downloads_count),
                    'active_users': active_users_data
                }, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving stats: {e}")
                
    def _save_whitelist(self):
        """Save whitelist to JSON file"""
        try:
            with open(self.users_file, 'w') as f:
                json.dump({
                    'whitelisted_users': list(self.whitelisted_users)
                }, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving whitelist: {e}")
        
    def add_download(self, content_type: str):
        self.downloads_count[content_type] += 1
        self._save_data()
        
    def add_to_whitelist(self, username: str) -> bool:
        if username in self.whitelisted_users:
            return False
        self.whitelisted_users.add(username)
        self._save_data()
        return True
        
    def remove_from_whitelist(self, username: str, full_removal: bool = True) -> bool:
        """Remove user from whitelist and optionally from all activity history"""
        if username not in self.whitelisted_users:
            logging.warning(f"User {username} not found in whitelist")
            return False
        
        logging.info(f"Removing user {username} from whitelist")
        self.whitelisted_users.remove(username)
        
        # If full_removal is True, also remove from active_users history
        if full_removal:
            # Remove user from all active_users dates
            for date in list(self.active_users.keys()):
                # This would require storing usernames in active_users instead of IDs
                # For now, we only remove from whitelist
                pass
        
        self._save_data()
        logging.info(f"User {username} removed successfully. Current whitelist: {self.whitelisted_users}")
        return True
        
    def is_whitelisted(self, username: str) -> bool:
        return username in self.whitelisted_users
    
    def add_active_user(self, user_id: int):
        today = datetime.now().date().isoformat()  # Convert to string for JSON serialization
        if today not in self.active_users:
            self.active_users[today] = set()
        self.active_users[today].add(user_id)
        self._save_data()
    
    def get_weekly_stats(self):
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        # Get download counts
        total_video = self.downloads_count['Video']
        total_audio = self.downloads_count['Music']
        
        # Get active users for the last week
        active_users = set()
        for date_str, users in list(self.active_users.items()):
            date = datetime.fromisoformat(date_str).date()
            if date >= week_ago:
                active_users.update(users)
            elif date < week_ago:
                del self.active_users[date_str]  # Cleanup old data
                self._save_data()  # Save after cleanup
                
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# Create logger for user downloads
download_logger = logging.getLogger('download_tracker')
download_logger.setLevel(logging.INFO)
download_handler = logging.FileHandler('downloads.log')
download_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
download_logger.addHandler(download_handler)

# Initialize bot with token from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables. Check your .env file.")
    
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Create downloads directory
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

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

async def download_media(url: str, is_music: bool = False) -> Path:
    output_template = str(DOWNLOADS_DIR / "%(title)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best' if is_music else 'best',
        'outtmpl': output_template,
        'restrictfilenames': True,
        'noplaylist': True,
        'extract_audio': is_music,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }] if is_music else [],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if is_music:
                filename = str(Path(filename).with_suffix('.mp3'))
            return Path(filename)
    except Exception as e:
        logging.error(f"Error downloading {url}: {str(e)}")
        raise

# Admin user ID
ADMIN_USER_ID = "datapeice"  # Admin username

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
@dp.message(lambda m: not m.text.startswith(('/start', '/panel', '/whitelist', '/unwhitelist', 'add @')))
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
            # Create inline keyboard for YouTube format selection
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"format:audio:{message.text}"),
                InlineKeyboardButton(text="🎥 Video", callback_data=f"format:video:{message.text}")
            )
            await message.answer("Choose download format:", reply_markup=builder.as_markup())
            return

        status_message = await message.answer("Processing your request... ⏳")
        is_music = is_youtube_music(message.text)
        file_path = await download_media(message.text, is_music)

        # Track statistics
        stats.add_active_user(message.from_user.id)
        stats.add_download('Music' if is_music else 'Video')

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
                await message.answer_audio(types.FSInputFile(file_path))
            else:
                await message.answer_video(types.FSInputFile(file_path))
            
            # Clean up
            file_path.unlink()
            await status_message.delete()
        else:
            await status_message.edit_text("Sorry, something went wrong during download.")
    
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        await status_message.edit_text(f"Sorry, an error occurred: {str(e)}")

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
@dp.message(Command("panel"))
async def cmd_admin_panel(message: types.Message):
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
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="➕ Add to Whitelist", callback_data="admin:whitelist_add"),
        InlineKeyboardButton(text="➖ Remove from Whitelist", callback_data="admin:whitelist_remove"),
        InlineKeyboardButton(text="🔄 Update yt-dlp", callback_data="admin:update_ytdlp")
    )
    builder.adjust(2, 1)  # 2 buttons in first row, 1 in second
    
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

    await message.answer(stats_message, reply_markup=builder.as_markup())

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
            await callback.answer(f"⚠️ User @{username} is not in the whitelist.", show_alert=True)
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
        
        _, format_type, url = callback.data.split(":", 2)
        await callback.message.delete()
        
        status_message = await callback.message.answer("Processing your request... ⏳")
        
        try:
            is_music = format_type == "audio"
            file_path = await download_media(url, is_music)

            # Track statistics
            stats.add_active_user(callback.from_user.id)
            stats.add_download('Music' if is_music else 'Video')

            # Log the download
            user_fullname = callback.from_user.full_name
            username = callback.from_user.username or "No username"
            user_id = callback.from_user.id
            download_logger.info(
                f"User: {user_fullname} (@{username}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: {'Audio' if is_music else 'Video'} | "
                f"URL: {url}"
            )

            # Send the file
            if file_path.exists():
                await status_message.edit_text("Uploading to Telegram... 📤")
                
                if is_music:
                    await callback.message.answer_audio(types.FSInputFile(file_path))
                else:
                    await callback.message.answer_video(types.FSInputFile(file_path))
                
                # Clean up
                file_path.unlink()
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

# Main function to start the bot
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
