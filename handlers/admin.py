import logging
import yt_dlp
import asyncio
import re
import html
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

def _local_tz():
    """Returns local timezone using zoneinfo for proper DST handling."""
    # Explicit fixed offset override
    if os.environ.get("TZ_OFFSET"):
        return timezone(timedelta(hours=int(os.environ["TZ_OFFSET"])))

    tz_str = os.environ.get("TZ", "Europe/Warsaw")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_str)
    except Exception:
        # Fallback: hardcoded offsets (no DST awareness)
        _TZ_MAP = {
            "europe/moscow":    3,
            "europe/warsaw":    2,
            "europe/kiev":      2,
            "europe/kyiv":      2,
            "europe/berlin":    2,
            "europe/london":    1,
            "america/new_york": -4,
            "us/eastern":       -4,
        }
        offset = _TZ_MAP.get(tz_str.lower(), 2)  # default UTC+2 (Warsaw CEST)
        return timezone(timedelta(hours=offset))

def _fmt_timestamp(dt: datetime) -> str:
    """Convert a naive UTC datetime from DB to local time string."""
    if dt is None:
        return "?"
    # Treat as UTC, convert to local
    utc_dt = dt.replace(tzinfo=timezone.utc)
    local_dt = utc_dt.astimezone(_local_tz())
    return local_dt.strftime('%d-%m %H:%M')
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
    if "youtube.com" in url_lower or "youtu.be" in url_lower or "ytmcustomsearch" in url_lower:
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
    if "soundcloud.com" in url_lower or "scsearch" in url_lower:
        return "SoundCloud"
    if "rutracker.org" in url_lower or "torrent" in url_lower or "magnet:" in url_lower:
        return "Torrent"

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

class DeleteHistoryStates(StatesGroup):
    waiting_for_id = State()

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin:back")]
    ])

@router.message(Command("whitelist"))
async def cmd_whitelist_add(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
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
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
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
@router.message(Command("addpremium"))
async def cmd_addpremium(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission.")
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer("Usage: `/addpremium <user_id or @username> [days]`\nExample: `/addpremium 123456789 30`\nIf days are not specified, Premium is granted forever.", parse_mode="Markdown")
        return
        
    target = args[0].lstrip('@')
    days = None
    if len(args) > 1 and args[1].isdigit():
        days = int(args[1])
        
    user_id = None
    if target.isdigit():
        user_id = int(target)
    else:
        if stats.Session:
            with stats.Session() as session:
                history = session.query(DownloadHistory).filter(DownloadHistory.username.ilike(f"%{target}%")).first()
                if history:
                    user_id = history.user_id
                    
    if not user_id:
        await message.answer(f"❌ User '{target}' not found in database. Try using their numeric ID.")
        return
        
    try:
        if days is not None:
            stats.unlock_premium(user_id, days=days)
            await message.answer(f"✅ Premium granted to user `{user_id}` for {days} days.", parse_mode="Markdown")
        else:
            from database.models import UserProfile
            with stats.Session() as session:
                profile = session.query(UserProfile).filter_by(user_id=user_id).first()
                if not profile:
                    profile = UserProfile(user_id=user_id)
                    session.add(profile)
                profile.is_premium = 1
                profile.premium_expiry = None
                session.commit()
            await message.answer(f"✅ Premium granted to user `{user_id}` **forever**.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@router.message(Command("removepremium"))
async def cmd_removepremium(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer("Usage: `/removepremium <user_id or @username>`", parse_mode="Markdown")
        return
        
    target = args[0].lstrip('@')
    user_id = None
    if target.isdigit():
        user_id = int(target)
    else:
        if stats.Session:
            with stats.Session() as session:
                history = session.query(DownloadHistory).filter(DownloadHistory.username.ilike(f"%{target}%")).first()
                if history:
                    user_id = history.user_id
                    
    if not user_id:
        await message.answer(f"❌ User '{target}' not found in database.")
        return
        
    try:
        from database.models import UserProfile
        with stats.Session() as session:
            profile = session.query(UserProfile).filter_by(user_id=user_id).first()
            if profile:
                profile.is_premium = 0
                profile.premium_expiry = None
                session.commit()
        await message.answer(f"✅ Premium removed from user `{user_id}`.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")
@router.message(Command("setmodel"))
async def cmd_setmodel(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission.")
        return
        
    args = message.text.split()[1:]
    if not args:
        from config import AI_MODEL
        current_model = stats.get_app_setting("ai_model", AI_MODEL)
        await message.answer(f"Usage: `/setmodel <model_name>`\nCurrent AI Model: `{current_model}`", parse_mode="Markdown")
        return
        
    new_model = args[0]
    stats.set_app_setting("ai_model", new_model)
    await message.answer(f"✅ AI Model successfully updated to: `{new_model}`", parse_mode="Markdown")

@router.message(Command("setlimit"))
async def cmd_setlimit(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission.")
        return
        
    args = message.text.split()[1:]
    current_limit = stats.get_app_setting("premium_daily_limit", "10")
    
    if not args:
        await message.answer(
            f"Usage: `/setlimit <number>`\n"
            f"Current daily premium download limit: `{current_limit}`",
            parse_mode="Markdown"
        )
        return
    
    if not args[0].isdigit() or int(args[0]) < 1:
        await message.answer("❌ Please provide a valid positive number.", parse_mode="Markdown")
        return
        
    new_limit = int(args[0])
    stats.set_app_setting("premium_daily_limit", str(new_limit))
    await message.answer(f"✅ Premium daily download limit set to `{new_limit}` (was `{current_limit}`).", parse_mode="Markdown")

@router.message(Command("listpremium"))
async def cmd_listpremium(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission.")
        return
    
    users = stats.get_all_premium_users()
    if not users:
        await message.answer("⭐ No active premium users.")
        return
    
    text = f"⭐ *Premium Users ({len(users)})*\n\n"
    for u in users:
        expiry = u['premium_expiry'].strftime('%d-%m-%Y %H:%M') if u['premium_expiry'] else 'Permanent'
        ref_info = f" | refs: {u['referral_count']}" if u['referral_count'] else ""
        referred = f" | by: `{u['referred_by']}`" if u['referred_by'] else ""
        text += f"`{u['user_id']}` — expires: {expiry}{ref_info}{referred}\n"
    
    # Telegram message limit is 4096
    if len(text) > 4000:
        text = text[:4000] + "\n\n_...truncated_"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("panel"))
async def send_admin_panel(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to access the admin panel.")
        return

    weekly_stats = stats.get_weekly_stats()
    total_premium_users = stats.get_total_premium_users()
    total_referrals = stats.get_total_referral_users()
    referral_premiums = stats.get_total_referral_premium_users()
    
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
        f"🌟 Premium Users: {total_premium_users}\n"
        f"🔗 Total Referrals: {total_referrals}\n"
        f"🔗 Premium via Referral: {referral_premiums}\n"
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
        [InlineKeyboardButton(text=f"🔄 Toggle Limits: {stats.get_app_setting('premium_limits_enabled', 'True')}", callback_data="admin:toggle_limits")],
        [InlineKeyboardButton(text="📨 Broadcast Message", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
        InlineKeyboardButton(text="🔄 Update yt-dlp", callback_data="admin:update_ytdlp")],
        [InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs"),
        InlineKeyboardButton(text="🗑 Clear Logs", callback_data="admin:clear_logs")],
        [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
    ])
    await message.answer(stats_message, reply_markup=keyboard, parse_mode="HTML")

# Broadcast message handlers - Must be before general admin handler
@router.callback_query(F.data == "admin:broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(ADMIN_USER_ID) and callback.from_user.username != ADMIN_USER_ID:
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
    if str(callback.from_user.id) != str(ADMIN_USER_ID) and callback.from_user.username != ADMIN_USER_ID:
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
async def handle_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) != str(ADMIN_USER_ID) and callback.from_user.username != ADMIN_USER_ID:
        await callback.answer("You don't have permission to use these controls.", show_alert=True)
        return

    action = callback.data.replace("admin:", "", 1)
    
    if action == "toggle_limits":
        new_val = stats.toggle_app_setting("premium_limits_enabled")
        await callback.answer(f"Premium limits toggled to {new_val}")
        
        # update keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Users List", callback_data="admin:users")],
            [InlineKeyboardButton(text="➕ Add User", callback_data="admin:add_user"),
            InlineKeyboardButton(text="➖ Remove User", callback_data="admin:remove_user")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
            InlineKeyboardButton(text="📜 History", callback_data="admin:history")],
            [InlineKeyboardButton(text=f"🔄 Toggle Limits: {new_val}", callback_data="admin:toggle_limits")],
            [InlineKeyboardButton(text="📨 Broadcast Message", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
            InlineKeyboardButton(text="🔄 Update yt-dlp", callback_data="admin:update_ytdlp")],
            [InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs"),
            InlineKeyboardButton(text="🗑 Clear Logs", callback_data="admin:clear_logs")],
            [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
        ])
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    elif action == "add_user":
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
        
    elif action == "delete_history":
        if not stats.Session:
            await callback.answer("❌ This feature is only available in Database Mode.", show_alert=True)
            return
            
        await callback.message.answer(
            "🗑 *Delete History Entry*\n\n"
            "Please send the *ID* of the download you want to delete.\n"
            "You can find IDs next to entries in the history list.\n\n"
            "Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        await state.set_state(DeleteHistoryStates.waiting_for_id)
        try:
            await callback.answer()
        except:
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
                            date_str = _fmt_timestamp(h.timestamp)
                            
                            url = h.url if h.url else ""
                            display_username = format_history_username(h.username)
                            
                            # Use title as label, fallback to platform domain
                            label = h.title if h.title else get_history_platform_label(url)
                            safe_label = str(label).replace('[', '').replace(']', '').replace('(', '').replace(')', '')
                            if len(safe_label) > 40: safe_label = safe_label[:37] + "..."

                            text += f"`{h.id}` | `{date_str}` | {display_username} | [{safe_label}]({url})\n"
                        
                        buttons = []
                        if page > 0:
                            buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin:history:{page-1}"))
                        if (page + 1) * ITEMS_PER_PAGE < total_count:
                            buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"admin:history:{page+1}"))
                        
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            buttons,
                            [InlineKeyboardButton(text="🗑 Delete by ID", callback_data="admin:delete_history")],
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

                                title_match = re.search(r'Title: (.+)', rest)
                                if title_match:
                                    label = title_match.group(1).strip()
                                else:
                                    label = get_history_platform_label(url)
                                
                                display_username = format_history_username(handle_value)
                                safe_label = str(label).replace('[', '').replace(']', '').replace('(', '').replace(')', '')
                                
                                # If label is still generic "Link" or "Unknown", try harder to get the platform from URL
                                if safe_label in ["Link", "Unknown", "Torrent"]:
                                    platform_label = get_history_platform_label(url)
                                    if platform_label != "Link":
                                        if safe_label == "Torrent":
                                            safe_label = f"Torrent ({platform_label})"
                                        else:
                                            safe_label = platform_label

                                if len(safe_label) > 40: safe_label = safe_label[:37] + "..."

                                text += f"`{date_str}` | {display_username} | [{safe_label}]({url})\n"
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
        total_premium_users = stats.get_total_premium_users()
        total_referrals = stats.get_total_referral_users()
        referral_premiums = stats.get_total_referral_premium_users()
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
            f"🌟 Premium Users: {total_premium_users}\n"
            f"🔗 Total Referrals: {total_referrals}\n"
            f"🔗 Premium via Referral: {referral_premiums}\n"
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
            [InlineKeyboardButton(text=f"🔄 Toggle Limits: {stats.get_app_setting('premium_limits_enabled', 'True')}", callback_data="admin:toggle_limits")],
            [InlineKeyboardButton(text="📨 Broadcast Message", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🍪 Update Cookies", callback_data="admin:update_cookies"),
            InlineKeyboardButton(text="🔄 Update yt-dlp", callback_data="admin:update_ytdlp")],
            [InlineKeyboardButton(text="📂 Get Logs", callback_data="admin:get_logs"),
            InlineKeyboardButton(text="🗑 Clear Logs", callback_data="admin:clear_logs")],
            [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")]
        ])
        try:
            await callback.message.edit_text(stats_message, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass

    elif action == "stats":
        # Stats button - do nothing, already showing stats
        pass

    elif action == "get_logs":
        log_files = [Path("logs/bot.log"), Path("bot.log")]
        found = False
        for log_file in log_files:
            if log_file.exists() and log_file.stat().st_size > 0:
                size_kb = log_file.stat().st_size / 1024
                filename = log_file.stem + ".txt"
                await callback.message.answer_document(
                    types.FSInputFile(log_file, filename=filename),
                    caption=f"📂 {filename} ({size_kb:.1f} KB)"
                )
                found = True
        
        if not found:
            await callback.message.answer("❌ No log files found.")
        await callback.answer()

    elif action == "clear_logs":
        # Find log files and show size info with confirmation
        log_files = [Path("logs/bot.log"), Path("bot.log")]
        found_files = [f for f in log_files if f.exists() and f.stat().st_size > 0]

        if not found_files:
            await callback.answer("No log files found.", show_alert=True)
            return

        total_size_kb = sum(f.stat().st_size for f in found_files) / 1024
        names = ", ".join(f.name for f in found_files)

        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, clear", callback_data="admin:clear_logs_confirm"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="admin:back")
            ]
        ])
        await callback.message.edit_text(
            f"⚠️ <b>Are you sure?</b>\n\n"
            f"Files: <code>{names}</code>\n"
            f"Total size: <b>{total_size_kb:.1f} KB</b>\n\n"
            f"This will erase all log data permanently.",
            parse_mode="HTML",
            reply_markup=confirm_keyboard
        )
        await callback.answer()

    elif action == "clear_logs_confirm":
        log_files = [Path("logs/bot.log"), Path("bot.log")]
        cleared = []
        for log_file in log_files:
            if log_file.exists():
                try:
                    log_file.write_text("")  # Truncate without deleting the file
                    cleared.append(log_file.name)
                except Exception as e:
                    logging.error(f"Failed to clear log {log_file}: {e}")

        if cleared:
            await callback.message.edit_text(
                f"✅ Cleared: <code>{'</code>, <code>'.join(cleared)}</code>",
                parse_mode="HTML",
                reply_markup=get_back_keyboard()
            )
        else:
            await callback.answer("Nothing to clear.", show_alert=True)
        await callback.answer()

    elif action == "close":
        await callback.message.delete()
        
    await callback.answer()

# ... (остальной код handle_document и handle_whitelist_add без изменений)
@router.message(F.document.file_name == "cookies.txt")
async def handle_document(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
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
    if str(callback.from_user.id) != str(ADMIN_USER_ID) and callback.from_user.username != ADMIN_USER_ID:
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
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        await message.answer("You don't have permission to manage the whitelist.")
        return

    username = message.text[5:].strip()
    if stats.add_to_whitelist(username):
        await message.answer(f"✅ User @{username} has been added to the whitelist.")
    else:
        await message.answer(f"⚠️ User @{username} is already in the whitelist.")

@router.message(Command("cancel"))
async def cancel_broadcast(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        return
    
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer("❌ Broadcast cancelled.")

@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
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

@router.message(DeleteHistoryStates.waiting_for_id)
async def process_history_delete(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(ADMIN_USER_ID) and message.from_user.username != ADMIN_USER_ID:
        return
    
    id_text = message.text.strip()
    if not id_text.isdigit():
        await message.answer("❌ Invalid ID. Please send a numeric ID.")
        return
    
    history_id = int(id_text)
    
    if stats.remove_history_entry(history_id):
        await message.answer(f"✅ History record #`{history_id}` has been permanently deleted.", parse_mode="Markdown")
        await state.clear()
    else:
        await message.answer(f"❌ Record #`{history_id}` not found or could not be deleted.")
