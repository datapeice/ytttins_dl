import logging
import yt_dlp
from datetime import datetime
from pathlib import Path
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_USER_ID, DATA_DIR
from database.storage import stats
from database.models import Cookie, DownloadHistory

router = Router()

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin:back")]
    ])

@router.message(Command("whitelist"))
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

@router.message(Command("unwhitelist"))
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

@router.message(Command("panel"))
async def send_admin_panel(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to access the admin panel.")
        return

    weekly_stats = stats.get_weekly_stats()
    
    try:
        ytdlp_version = yt_dlp.version.__version__
    except:
        ytdlp_version = "Unknown"
    
    whitelisted_list = "\n".join([f"  @{user}" for user in stats.whitelisted_users]) if stats.whitelisted_users else "  No whitelisted users"

    stats_message = (
        "📊 Weekly Statistics:\n\n"
        f"📥 Downloads:\n"
        f"   📹 Videos: {weekly_stats['video_count']}\n"
        f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
        f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n\n"
        f"📝 Whitelisted Users:\n"
        f"{whitelisted_list}\n\n"
        f"🔧 Version: yt-dlp {ytdlp_version}\n\n"
    )

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
    
    if weekly_stats['active_users']:
        user_list = []
        # We need bot instance to get chat info, but we don't have it here easily.
        # We can use message.bot
        bot = message.bot
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

@router.callback_query(F.data.startswith("admin:"))
async def handle_admin_callback(callback: types.CallbackQuery):
    if callback.from_user.username != ADMIN_USER_ID:
        await callback.answer("You don't have permission to use these controls.", show_alert=True)
        return

    action = callback.data.replace("admin:", "", 1)
    
    if action == "add_user":
        await callback.message.answer("Please send the username to add to whitelist in format:\n`/whitelist username`", parse_mode="Markdown")
        await callback.answer()
        
    elif action == "remove_user":
        if not stats.whitelisted_users:
            await callback.message.answer("The whitelist is empty.")
            await callback.answer()
            return
            
        builder = InlineKeyboardBuilder()
        for username in stats.whitelisted_users:
            builder.add(InlineKeyboardButton(
                text=f"❌ @{username}",
                callback_data=f"admin:remove:{username}"
            ))
        builder.add(InlineKeyboardButton(text="🔙 Back", callback_data="admin:back"))
        builder.adjust(1)
        await callback.message.edit_text("Select user to remove from whitelist:", reply_markup=builder.as_markup())
        
    elif action == "users":
        whitelisted_list = "\n".join([f"• @{user}" for user in stats.whitelisted_users]) if stats.whitelisted_users else "No whitelisted users"
        text = f"📝 *Whitelisted Users:*\n\n{whitelisted_list}"
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif action.startswith("remove:"):
        username = action.split(":", 1)[1]
        if stats.remove_from_whitelist(username):
            await callback.message.edit_text(f"✅ User @{username} has been deleted from the whitelist.")
        else:
            await callback.message.answer(f"⚠️ User @{username} is not in the whitelist.")
            await callback.answer(show_alert=True)
    elif action == "update_ytdlp":
        status_msg = await callback.message.answer("```\n🔄 Starting yt-dlp update...\n```", parse_mode="Markdown")
        try:
            import subprocess
            await status_msg.edit_text("```\n🔄 Starting yt-dlp update...\n⏳ Running pip install --upgrade yt-dlp\n```", parse_mode="Markdown")
            
            result = subprocess.run(
                ["pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
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
        
    elif action.startswith("history"):
        page = 0
        if ":" in action:
            try:
                page = int(action.split(":")[1])
            except:
                pass
        
        ITEMS_PER_PAGE = 20
        
        if stats.Session:
            try:
                with stats.Session() as session:
                    total_count = session.query(DownloadHistory).count()
                    history = session.query(DownloadHistory).order_by(DownloadHistory.timestamp.desc()).offset(page * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE).all()
                    
                    if not history:
                        text = "📜 *Download History*\n\nNo downloads recorded yet."
                        keyboard = get_back_keyboard()
                    else:
                        text = f"📜 *Download History (Page {page + 1})*\n\n"
                        for h in history:
                            date_str = h.timestamp.strftime('%d-%m %H:%M')
                            
                            platform = "Link"
                            url = h.url if h.url else ""
                            if "youtube.com" in url or "youtu.be" in url: platform = "YouTube"
                            elif "tiktok.com" in url: platform = "TikTok"
                            elif "instagram.com" in url: platform = "Instagram"
                            elif "twitter.com" in url or "x.com" in url: platform = "X"
                            elif "facebook.com" in url or "fb.watch" in url: platform = "Facebook"
                            elif "twitch.tv" in url: platform = "Twitch"
                            elif "soundcloud.com" in url: platform = "SoundCloud"

                            username = h.username if h.username else "Unknown"
                            text += f"`{date_str}` | @{username} | [{platform}]({url})\n"
                        
                        # Pagination buttons
                        buttons = []
                        if page > 0:
                            buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin:history:{page-1}"))
                        if (page + 1) * ITEMS_PER_PAGE < total_count:
                            buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"admin:history:{page+1}"))
                        
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            buttons,
                            [InlineKeyboardButton(text="🔙 Back", callback_data="admin:back")]
                        ])
            except Exception as e:
                logging.error(f"Error fetching history: {e}")
                text = f"❌ Error fetching history: {str(e)}"
                keyboard = get_back_keyboard()
        else:
            # File fallback (simple implementation without pagination for now, or basic slicing)
            log_file = Path("logs/downloads.log")
            if log_file.exists():
                try:
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                    
                    total_count = len(lines)
                    # Reverse lines to show newest first
                    lines = list(reversed(lines))
                    
                    start_idx = page * ITEMS_PER_PAGE
                    end_idx = start_idx + ITEMS_PER_PAGE
                    page_lines = lines[start_idx:end_idx]
                    
                    if not page_lines:
                        text = "📜 *Download History*\n\nNo downloads recorded yet."
                        keyboard = get_back_keyboard()
                    else:
                        text = f"📜 *Download History (Page {page + 1})*\n\n"
                        for line in page_lines:
                            # Parse log line format: 2025-12-20 23:43:56,519 - User: Ilya Datsiuk (@datapeice, ID: 6299330933) | Platform: youtube | Type: Video (360p) | URL: https://youtu.be/dO-mJjZfwxE
                            try:
                                # Split by " - User: " to separate timestamp
                                parts = line.split(" - User: ", 1)
                                if len(parts) < 2:
                                    raise ValueError("Invalid format")
                                    
                                timestamp_str = parts[0].split(',')[0] # 2025-12-20 23:43:56
                                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                date_str = dt.strftime('%d-%m %H:%M')
                                
                                rest = parts[1] 
                                # Ilya Datsiuk (@datapeice, ID: 6299330933) | Platform: youtube | Type: Video (360p) | URL: https://youtu.be/dO-mJjZfwxE
                                
                                # Extract username
                                import re
                                username_match = re.search(r'\(@([^,]+),', rest)
                                username = username_match.group(1) if username_match else "Unknown"
                                
                                # Extract URL
                                url_match = re.search(r'URL: (https?://\S+)', rest)
                                url = url_match.group(1) if url_match else ""
                                
                                platform = "Link"
                                if "youtube.com" in url or "youtu.be" in url: platform = "YouTube"
                                elif "tiktok.com" in url: platform = "TikTok"
                                elif "instagram.com" in url: platform = "Instagram"
                                elif "twitter.com" in url or "x.com" in url: platform = "X"
                                elif "facebook.com" in url or "fb.watch" in url: platform = "Facebook"
                                elif "twitch.tv" in url: platform = "Twitch"
                                elif "soundcloud.com" in url: platform = "SoundCloud"

                                text += f"`{date_str}` | @{username} | [{platform}]({url})\n"
                            except:
                                text += f"{line.strip()}\n"

                        # Pagination buttons
                        buttons = []
                        if page > 0:
                            buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin:history:{page-1}"))
                        if end_idx < total_count:
                            buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"admin:history:{page+1}"))
                        
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            buttons,
                            [InlineKeyboardButton(text="🔙 Back", callback_data="admin:back")]
                        ])

                except Exception as e:
                    logging.error(f"Error reading history log: {e}")
                    text = "❌ Error reading history log."
                    keyboard = get_back_keyboard()
            else:
                text = "❌ History log not found."
                keyboard = get_back_keyboard()
            
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)

    elif action == "back":
        # Re-render panel
        # We can reuse send_admin_panel logic but we need to edit message
        weekly_stats = stats.get_weekly_stats()
        try:
            ytdlp_version = yt_dlp.version.__version__
        except:
            ytdlp_version = "Unknown"
        
        whitelisted_list = "\n".join([f"  @{user}" for user in stats.whitelisted_users]) if stats.whitelisted_users else "  No whitelisted users"

        stats_message = (
            "📊 Weekly Statistics:\n\n"
            f"📥 Downloads:\n"
            f"   📹 Videos: {weekly_stats['video_count']}\n"
            f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
            f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n\n"
            f"📝 Whitelisted Users:\n"
            f"{whitelisted_list}\n\n"
            f"🔧 Version: yt-dlp {ytdlp_version}\n\n"
        )

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
        
        if weekly_stats['active_users']:
            user_list = []
            bot = callback.bot
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
            # Ignore if message is not modified
            pass

    elif action == "stats":
        # Refresh stats by calling back handler logic
        # We need to manually trigger the 'back' logic which refreshes the main panel
        # Instead of modifying callback.data (which is frozen), we just call the logic for 'back'
        # But since 'back' logic is inside this function, we can just recursively call with modified data?
        # No, we can't modify data. We should extract the panel logic.
        # For now, let's just copy the 'back' logic here or use a hack.
        # Actually, the cleanest way without refactoring everything is to just copy the logic or use a helper.
        # Let's just copy the logic from 'back' block for now to be safe and quick.
        
        weekly_stats = stats.get_weekly_stats()
        try:
            ytdlp_version = yt_dlp.version.__version__
        except:
            ytdlp_version = "Unknown"
        
        whitelisted_list = "\n".join([f"  @{user}" for user in stats.whitelisted_users]) if stats.whitelisted_users else "  No whitelisted users"

        stats_message = (
            "📊 Weekly Statistics:\n\n"
            f"📥 Downloads:\n"
            f"   📹 Videos: {weekly_stats['video_count']}\n"
            f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
            f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n\n"
            f"📝 Whitelisted Users:\n"
            f"{whitelisted_list}\n\n"
            f"🔧 Version: yt-dlp {ytdlp_version}\n\n"
        )

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
        
        if weekly_stats['active_users']:
            user_list = []
            bot = callback.bot
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
            # Ignore if message is not modified
            pass

    elif action == "get_logs":
        # Try multiple log locations
        log_files = [
            Path("logs/bot.log"),
            Path("bot.log")
        ]
        
        found = False
        for log_file in log_files:
            if log_file.exists() and log_file.stat().st_size > 0:
                filename = log_file.stem + ".txt"
                await callback.message.answer_document(types.FSInputFile(log_file, filename=filename), caption=f"📂 {filename}")
                found = True
        
        if not found:
            await callback.message.answer("❌ No log files found.")
        await callback.answer()

    elif action == "close":
        await callback.message.delete()
        
    await callback.answer()

@router.message(F.document)
async def handle_document(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        return

    if message.document.file_name == "cookies.txt":
        try:
            file_id = message.document.file_id
            bot = message.bot
            file = await bot.get_file(file_id)
            file_path = file.file_path
            
            destination = DATA_DIR / "cookies.txt.tmp"
            await bot.download_file(file_path, destination)
            
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

@router.callback_query(F.data.startswith("cookie:"))
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
                if stats.Session:
                    try:
                        with open(tmp_file, 'r') as f:
                            content = f.read()
                        with stats.Session() as session:
                            session.query(Cookie).delete()
                            session.add(Cookie(content=content))
                            session.commit()
                    except Exception as e:
                        logging.error(f"Error saving cookies to DB: {e}")

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

@router.message(lambda message: message.text and message.text.lower().startswith("add @"))
async def handle_whitelist_add(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to manage the whitelist.")
        return

    username = message.text[5:].strip()
    if stats.add_to_whitelist(username):
        await message.answer(f"✅ User @{username} has been added to the whitelist.")
        # We can't easily refresh the panel here without the message object of the panel
    else:
        await message.answer(f"⚠️ User @{username} is already in the whitelist.")
