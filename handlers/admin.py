import logging
import yt_dlp
import asyncio
import re
import html
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_USER_ID, DATA_DIR
from database.storage import stats
from database.models import Cookie, DownloadHistory

router = Router()

def get_history_platform_label(url: str) -> str:
    if not url:
        return "Link"

    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "instagram.com" in url_lower:
        return "Instagram"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "X"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "Facebook"
    if "twitch.tv" in url_lower:
        return "Twitch"
    if "soundcloud.com" in url_lower:
        return "SoundCloud"

    domain = urlparse(url_lower).netloc
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or "Link"

def format_history_username(username: str) -> str:
    if not username:
        return "Unknown"
    safe_name = username.replace("_", "\\_")
    if re.fullmatch(r"[A-Za-z0-9_]{5,}$", username):
        return f"@{safe_name}"
    return safe_name

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

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
    
    # Получаем версию на VPS
    try:
        local_version = yt_dlp.version.__version__
    except:
        local_version = "Unknown"

    
    whitelisted_list = "\n".join([f"  @{user}" for user in stats.whitelisted_users]) if stats.whitelisted_users else "  No whitelisted users"

    stats_message = (
        "📊 Weekly Statistics:\n\n"
        f"📥 Downloads:\n"
        f"   📹 Videos: {weekly_stats['video_count']}\n"
        f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
        f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n"
        f"🏘 Active Groups: {weekly_stats.get('active_groups_count', 0)}\n\n"
        f"📝 Whitelisted Users:\n"
        f"{whitelisted_list}\n\n"
        f"🔧 yt-dlp Version:\n"
        f"   🏠 VPS (Local): {local_version}\n\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Users List", callback_data="admin:users")],
        [InlineKeyboardButton(text="➕ Add User", callback_data="admin:add_user"),
        InlineKeyboardButton(text="➖ Remove User", callback_data="admin:remove_user")],
        [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
        InlineKeyboardButton(text="📜 History", callback_data="admin:history")],
        [InlineKeyboardButton(text="📨 Broadcast Message", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
        InlineKeyboardButton(text="🔄 Update yt-dlp", callback_data="admin:update_ytdlp")],
        [InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs"),
        InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
    ])
    await message.answer(stats_message, reply_markup=keyboard, parse_mode="HTML")

# Broadcast message handlers - Must be before general admin handler
@router.callback_query(F.data == "admin:broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.username != ADMIN_USER_ID:
        await callback.answer("You don't have permission.", show_alert=True)
        return
    
    await callback.message.answer(
        "📨 *Broadcast Message*\n\n"
        "Send me the message you want to broadcast to all users who have downloaded at least one video.\n"
        "You can send text, photo with caption, or video with caption.\n\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown"
    )
    await state.set_state(BroadcastStates.waiting_for_message)
    try:
        await callback.answer()
    except Exception:
        pass  # Ignore timeout errors

@router.callback_query(F.data.startswith("broadcast:"))
async def handle_broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.username != ADMIN_USER_ID:
        await callback.answer("You don't have permission.", show_alert=True)
        return
    
    action = callback.data.split(":")[1]
    
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Broadcast cancelled.")
        try:
            await callback.answer()
        except Exception:
            pass
        return
    
    if action == "confirm":
        data = await state.get_data()
        message_id = data.get("message_id")
        user_ids = data.get("user_ids", [])
        
        if not user_ids:
            await callback.message.edit_text("❌ No users to broadcast to.")
            await state.clear()
            await callback.answer()
            return
        
        # Get the original message
        chat_id = callback.message.chat.id
        bot = callback.message.bot
        
        status_msg = await callback.message.edit_text(
            f"📤 Broadcasting to {len(user_ids)} users...\n"
            f"Progress: 0/{len(user_ids)}"
        )
        
        success_count = 0
        fail_count = 0
        
        for i, user_id in enumerate(user_ids):
            try:
                # Forward or copy the message
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=chat_id,
                    message_id=message_id
                )
                success_count += 1
            except Exception as e:
                logging.warning(f"Failed to send broadcast to user {user_id}: {e}")
                fail_count += 1
            
            # Update progress every 10 users
            if (i + 1) % 10 == 0 or (i + 1) == len(user_ids):
                try:
                    await status_msg.edit_text(
                        f"📤 Broadcasting to {len(user_ids)} users...\n"
                        f"Progress: {i + 1}/{len(user_ids)}\n"
                        f"✅ Sent: {success_count}\n"
                        f"❌ Failed: {fail_count}"
                    )
                except:
                    pass
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.05)
        
        await status_msg.edit_text(
            f"✅ *Broadcast Complete!*\n\n"
            f"📊 Total users: {len(user_ids)}\n"
            f"✅ Sent: {success_count}\n"
            f"❌ Failed: {fail_count}",
            parse_mode="Markdown"
        )
        
        await state.clear()
        try:
            await callback.answer()
        except Exception:
            pass

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
        status_msg = await callback.message.answer("```\n🔄 Starting GLOBAL yt-dlp update...\n```", parse_mode="Markdown")
        
        report = []
        
        # Обновляем VPS
        try:
            await status_msg.edit_text("```\nUpdating VPS (Local)...\n```", parse_mode="Markdown")
            import subprocess
            import importlib
            
            result = subprocess.run(
                ["pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                importlib.reload(yt_dlp.version)
                new_ver = yt_dlp.version.__version__
                report.append(f"✅ VPS: Updated to {new_ver}")
            else:
                report.append(f"❌ VPS: Failed ({result.stderr[:50]}...)")
        except Exception as e:
            report.append(f"❌ VPS: Error ({str(e)})")

        final_text = "\n".join(report)
        await status_msg.edit_text(
            f"```\n🏁 Update Finished:\n\n{final_text}\n```",
            parse_mode="Markdown"
        )

    elif action == "update_cookies":
        await callback.message.answer("Please send the `cookies.txt` file now.")
    
    elif action == "broadcast":
        # Let the separate handler deal with this
        pass
        
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
                            
                            url = h.url if h.url else ""
                            platform = get_history_platform_label(url)
                            display_username = format_history_username(h.username)

                            text += f"`{date_str}` | {display_username} | [{platform}]({url})\n"
                        
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
            # File fallback
            log_file = Path("logs/downloads.log")
            if log_file.exists():
                try:
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                    
                    total_count = len(lines)
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
                            try:
                                parts = line.split(" - User: ", 1)
                                if len(parts) < 2: continue
                                    
                                timestamp_str = parts[0].split(',')[0]
                                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                date_str = dt.strftime('%d-%m %H:%M')
                                
                                rest = parts[1]
                                handle_match = re.search(r'\(([^,]+), ID:', rest)
                                handle_value = handle_match.group(1) if handle_match else "Unknown"
                                if handle_value.startswith("@"):
                                    handle_value = handle_value[1:]

                                url_match = re.search(r'URL: (https?://\S+)', rest)
                                url = url_match.group(1) if url_match else ""

                                platform = get_history_platform_label(url)
                                display_username = format_history_username(handle_value)

                                text += f"`{date_str}` | {display_username} | [{platform}]({url})\n"
                            except:
                                pass

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
        weekly_stats = stats.get_weekly_stats()
        try:
            local_version = yt_dlp.version.__version__
        except:
            local_version = "Unknown"
        
        whitelisted_list = "\n".join([f"  @{user}" for user in stats.whitelisted_users]) if stats.whitelisted_users else "  No whitelisted users"

        stats_message = (
            "📊 Weekly Statistics:\n\n"
            f"📥 Downloads:\n"
            f"   📹 Videos: {weekly_stats['video_count']}\n"
            f"   🎵 Music: {weekly_stats['audio_count']}\n\n"
            f"👥 Active Users (last 7 days): {weekly_stats['active_users_count']}\n"
            f"🏘 Active Groups: {weekly_stats.get('active_groups_count', 0)}\n\n"
            f"📝 Whitelisted Users:\n"
            f"{whitelisted_list}\n\n"
            f"🔧 yt-dlp Version:\n"
            f"   🏠 VPS (Local): {local_version}\n\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Users List", callback_data="admin:users")],
            [InlineKeyboardButton(text="➕ Add User", callback_data="admin:add_user"),
            InlineKeyboardButton(text="➖ Remove User", callback_data="admin:remove_user")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
            InlineKeyboardButton(text="📜 History", callback_data="admin:history")],
            [InlineKeyboardButton(text="📨 Broadcast Message", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
            InlineKeyboardButton(text="🔄 Update yt-dlp", callback_data="admin:update_ytdlp")],
            [InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs"),
            InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
        ])
        try:
            await callback.message.edit_text(stats_message, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass

    elif action == "stats":
        # Stats button - do nothing, already showing stats
        pass

    elif action == "get_logs":
        # ... (оставляем логику логов как есть)
        log_files = [Path("logs/bot.log"), Path("bot.log")]
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

# ... (остальной код handle_document и handle_whitelist_add без изменений)
@router.message(F.document)
async def handle_document(message: types.Message):
    if message.from_user.username != ADMIN_USER_ID:
        return

    if message.document.file_name == "cookies.txt":
        try:
            file_id = message.document.file_id
            bot = message.bot
            
            destination = DATA_DIR / "cookies.txt.tmp"
            # Use download() instead of get_file() + download_file() to handle local API properly
            await bot.download(file=file_id, destination=destination)
            
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
    else:
        await message.answer(f"⚠️ User @{username} is already in the whitelist.")

@router.message(Command("cancel"))
async def cancel_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.username != ADMIN_USER_ID:
        return
    
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer("❌ Broadcast cancelled.")

@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.username != ADMIN_USER_ID:
        return
    
    # Get all unique user IDs who have downloaded
    user_ids = set()
    group_ids = set()
    
    if stats.Session:
        try:
            with stats.Session() as session:
                results = session.query(DownloadHistory.user_id).distinct().all()
                user_ids = {user_id for (user_id,) in results if user_id}
                
                from database.models import ActiveGroup
                group_results = session.query(ActiveGroup.chat_id).distinct().all()
                group_ids = {group_id for (group_id,) in group_results if group_id}
        except Exception as e:
            logging.error(f"Error fetching users/groups from DB: {e}")
    else:
        # Fallback to local storage - active_users is Dict[date, Set[user_id]]
        for date, users in stats.active_users.items():
            user_ids.update(users)
        group_ids.update(stats.active_groups)
    
    all_targets = user_ids.union(group_ids)
    
    if not all_targets:
        await message.answer("❌ No users or groups found to broadcast to.")
        await state.clear()
        return
    
    # Confirm broadcast
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Send to all", callback_data="broadcast:confirm"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="broadcast:cancel")
        ]
    ])
    
    await state.update_data(
        message_id=message.message_id,
        user_ids=list(all_targets)
    )
    
    await message.answer(
        f"📊 Ready to broadcast to *{len(user_ids)} users* and *{len(group_ids)} groups* (Total: {len(all_targets)}).\n\n"
        f"Confirm to proceed:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )