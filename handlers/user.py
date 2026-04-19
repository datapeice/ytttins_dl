import uuid
from typing import Union
import re
import logging
import asyncio
import time
import random
import subprocess
from pathlib import Path
from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from services.downloader import download_media, get_platform, is_youtube_music, is_playlist, FUNNY_STATUSES
from services.torrent_service import torrent_service
from services import zip_service
from database.storage import stats
from services.logger import download_logger
from config import DOWNLOADS_DIR
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineQuery, ChosenInlineResult, InputMediaVideo, InputMediaAudio, LabeledPrice, PreCheckoutQuery
from services.metadata import fetch_song_metadata

router = Router()
url_cache = {}

def get_random_support_kb():
    if random.randint(1, 15) == 1:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="⭐️ Support Bot ⭐️", callback_data="show_donate_menu"))
        return builder.as_markup()
    return None

async def safe_edit_text(msg, text, max_retries=3, **kwargs):
    """Edit message text with retry logic for Telegram flood control."""
    for attempt in range(max_retries + 1):
        try:
            await msg.edit_text(text, **kwargs)
            return
        except TelegramRetryAfter as e:
            if attempt == max_retries:
                raise
            logging.warning(f"Flood control on edit_text: sleeping for {e.retry_after}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(e.retry_after)

def resolve_user_identity(user: types.User) -> tuple[str, str, str]:
    display_name = user.full_name or user.first_name or "Unknown"
    username = user.username or ""
    stored_name = username or display_name
    handle = f"@{username}" if username else display_name
    return display_name, stored_name, handle

def format_caption(metadata: dict, platform: str, original_url: str = "", is_music: bool = False) -> str:
    """Generate unified caption format for all platforms."""
    url = original_url or metadata.get('webpage_url', '')

    title = metadata.get('title', 'Media')
    title = str(title).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    if is_music:
        caption = f"<a href=\"{url}\">{title}</a>\nDeveloped by @datapeice"
    else:
        caption = f"<a href=\"{url}\">Link</a>"
    return caption

async def probe_media_duration_seconds(media_path: Path) -> int:
    def run_probe() -> int:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(media_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return 0
            duration_str = result.stdout.strip()
            if not duration_str:
                return 0
            return int(float(duration_str))
        except Exception:
            return 0

    return await asyncio.to_thread(run_probe)


@router.message(Command("start"))
async def cmd_start(message: types.Message, bot: Bot):
    me = await bot.get_me()
    display_name, stored_name, handle = resolve_user_identity(message.from_user)
    stats.add_active_user(message.from_user.id)
    
    welcome_text = (
        f"👋 <b>Hello, {display_name}!</b>\n\n"
        "I will help you download video, music and <b>playlists</b> from TikTok, YouTube, Instagram, Reddit and others.\n\n"
        "📎 <b>Just send me a link!</b>\n\n"
        "Download torrent files by sending the .torrent file or magnet link.\n\n"
        "👥 <b>Group Chats:</b>\n"
        "Add me to your group to download media together with friends!\n\n"
        "🔍 <b>Inline Mode:</b>\n"
        "Use me in <i>any</i> chat: <code>@{me.username} &lt;link&gt;</code>\n\n"
        "⭐️ <b>Support development:</b> /donate"
    )
    
    kb_builder = InlineKeyboardBuilder()
    kb_builder.add(InlineKeyboardButton(text="➕ Add to Group", url=f"https://t.me/{me.username}?startgroup=true"))
    
    reply_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Search Song"), KeyboardButton(text="⭐️ Support")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(welcome_text, reply_markup=reply_kb, parse_mode='HTML')
    # Also send the inline button for group adding
    await message.answer("Click below to invite me to your chat:", reply_markup=kb_builder.as_markup())

@router.message(Command("me"))
async def cmd_me(message: types.Message):
    user_id = message.from_user.id
    display_name, stored_name, handle = resolve_user_identity(message.from_user)
    
    profile = stats.get_user_profile(user_id)
    is_premium = bool(profile.get("is_premium") if isinstance(profile, dict) else profile.is_premium)
    daily_limit = 5
    total_downloads = stats.get_user_downloads_count(user_id)

    kb_builder = InlineKeyboardBuilder()

    if is_premium:
        premium_expiry = profile.get("premium_expiry") if isinstance(profile, dict) else profile.premium_expiry
        if premium_expiry:
            expiry_str = premium_expiry.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(premium_expiry, 'strftime') else str(premium_expiry)
            status = f"🌟 <b>Premium Status:</b> Active until <code>{expiry_str}</code>"
        else:
            status = f"🌟 <b>Premium Status:</b> Active (Forever)"
    else:
        status = f"🆓 <b>Premium Status:</b> Inactive"
        if stats.get_app_setting("premium_limits_enabled", "True") == "True":
            daily_downloads = profile.get("daily_premium_site_downloads", 0) if isinstance(profile, dict) else profile.daily_premium_site_downloads
            status += f"\n📊 Premium Site Downloads Today: {daily_downloads}/{daily_limit}"
            status += f"\n⏱ Remaining Premium Videos Today: {max(0, daily_limit - daily_downloads)}"

    kb_builder.add(InlineKeyboardButton(text="⭐️ Support Bot (Donate)", callback_data="show_donate_menu"))

    text = (
        f"👤 <b>User Profile</b>\n\n"
        f"<b>Name:</b> {display_name}\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Total Downloads:</b> {total_downloads}\n\n"
        f"{status}\n\n"
        f"<b>Your Current Limits:</b>\n"
        f"• Default Sites: {'Unlimited parallelism' if is_premium else '2 parallel'}\n"
        f"• Premium/Torrents: 1 parallel\n"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb_builder.as_markup())

@router.message(F.text == "⭐️ Support")
@router.message(Command("donate"))
async def handle_donate(message: types.Message, bot: Bot):
    """Sends the Star donation menu or processes a custom amount."""
    parts = message.text.split() if message.text else []
    if len(parts) > 1 and parts[1].isdigit():
        amount = int(parts[1])
        if amount < 1 or amount > 10000:
            await message.answer("Please specify a valid amount between 1 and 10000 stars.")
            return
            
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title="Custom Support ⭐️",
            description=f"Voluntary donation of {amount} stars for bot development.",
            payload=f"donate_{amount}_{message.from_user.id}",
            currency="XTR",
            prices=[LabeledPrice(label="Custom Support ⭐️", amount=amount)],
            provider_token="" # Empty for stars
        )
        return

    text = (
        "⭐️ <b>Support bot development!</b>\n\n"
        "Your donations help pay for servers and develop new features. "
        "Donate <b>50⭐️ or more</b> to unlock <b>Premium for 30 days!</b>\n\n"
        "We use <b>Telegram Stars</b> — this is the official and safe way to thank the developer.\n\n"
        "Choose an amount below, or type <code>/donate &lt;amount&gt;</code> for a custom amount:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="☕️ 50", callback_data="donate:50"),
        InlineKeyboardButton(text="🥤 100", callback_data="donate:100"),
        InlineKeyboardButton(text="🍔 250", callback_data="donate:250"),
        InlineKeyboardButton(text="🍕 500", callback_data="donate:500"),
        InlineKeyboardButton(text="💎 1000", callback_data="donate:1000")
    )
    builder.adjust(2)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode='HTML')

@router.callback_query(F.data == "show_donate_menu")
async def callback_show_donate_menu(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    
    text = (
        "⭐️ <b>Support bot development!</b>\n\n"
        "Your donations help pay for servers and develop new features. "
        "Donate <b>50⭐️ or more</b> to unlock <b>Premium for 30 days!</b>\n\n"
        "We use <b>Telegram Stars</b> — this is the official and safe way to thank the developer.\n\n"
        "Choose an amount below, or type <code>/donate &lt;amount&gt;</code> for a custom amount:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="☕️ 50", callback_data="donate:50"),
        InlineKeyboardButton(text="🥤 100", callback_data="donate:100"),
        InlineKeyboardButton(text="🍔 250", callback_data="donate:250"),
        InlineKeyboardButton(text="🍕 500", callback_data="donate:500"),
        InlineKeyboardButton(text="💎 1000", callback_data="donate:1000")
    )
    builder.adjust(2)
    
    await bot.send_message(callback.from_user.id, text, reply_markup=builder.as_markup(), parse_mode='HTML')

@router.callback_query(F.data.startswith("donate:"))
async def handle_donate_selection(callback: types.CallbackQuery, bot: Bot):
    """Sends the invoice for the selected amounts of stars."""
    amount = int(callback.data.split(":")[1])
    
    # Tier titles
    titles = {
        50: "Cup of coffee ☕️",
        100: "Refreshing drink 🥤",
        250: "Delicious burger 🍔",
        500: "Hot pizza 🍕",
        1000: "Diamond contribution 💎"
    }
    
    title = titles.get(amount, "Developer appreciation")
    
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description=f"Voluntary donation of {amount} stars for bot development.",
        payload=f"donate_{amount}_{callback.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=amount)],
        provider_token="" # Empty for stars
    )
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Confirms checkout."""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    """Thanks the user for donation and gives premium if 50+ stars."""
    payment = message.successful_payment
    amount = payment.total_amount
    
    extra_text = ""
    # Grant premium if donation is at least 50 stars
    if amount >= 50:
        if stats.unlock_premium(message.from_user.id, days=30):
            extra_text = "\n\n⭐ <b>Bonus:</b> You have unlocked Premium for 30 days! Thank you!"
            
    thanks_text = (
        "💖 <b>Thank you so much for your support!</b>\n\n"
        f"You have successfully donated <b>{amount} ⭐️</b>. "
        "This is incredibly important to us! We will continue improving the bot for you.\n\n"
        "✨ <i>Status updated: Winner in life!</i>" + extra_text
    )
    
    await message.answer(thanks_text, parse_mode='HTML')

@router.message(Command("song"))
@router.message(lambda m: m.text and (
    m.text.lower().startswith('search ') or
    m.text.lower().startswith('найти ') or
    m.text.lower().startswith('/song') or
    m.text == "🔍 Search Song"
))
async def handle_search(message: types.Message):
    text_lower = message.text.lower()
    
    if message.text == "🔍 Search Song":
        await message.answer("Please type <code>search </code> followed by the song name.\nExample: <code>search Linkin Park Numb</code>", parse_mode='HTML')
        return

    if text_lower.startswith('search '):
        query = message.text[len('search '):].strip()
    elif text_lower.startswith('найти '):
        query = message.text[len('найти '):].strip()
    elif text_lower.startswith('/song '):
        query = message.text[len('/song '):].strip()
    elif text_lower.startswith('/song'):
        query = message.text[len('/song'):].strip()
    else:
        query = ""

    if not query:
        await message.answer("❌ Please provide a song name.")
        return

    user_id = message.from_user.id
    profile = stats.get_user_profile(user_id)
    is_premium = bool(profile.get("is_premium") if isinstance(profile, dict) else profile.is_premium)
    
    reply_kwargs = {}
    if message.chat.type != 'private':
        reply_kwargs['reply_to_message_id'] = message.message_id
        stats.add_active_group(message.chat.id)
    
    # Whitelist check
    if stats.whitelisted_users and not stats.is_whitelisted(message.from_user.username):
        await message.answer("⛔ Sorry, this bot is private. You are not in the whitelist.", **reply_kwargs)
        return
    
    # Start fetching rich metadata in parallel with search/download
    metadata_task = asyncio.create_task(fetch_song_metadata(query))
    
    # Wait briefly for metadata to refine search accuracy
    refined_query = query
    try:
        # 1.5s is usually enough for iTunes API
        itunes_meta = await asyncio.wait_for(asyncio.shield(metadata_task), timeout=1.5)
        if itunes_meta.get('artist') and itunes_meta.get('title'):
            refined_query = f"{itunes_meta['artist']} - {itunes_meta['title']}"
            logging.info(f"Refined search query: {refined_query}")
    except Exception:
        pass

    is_group = message.chat.type != 'private'

    status_message = None
    if not is_group:
        status_message = await message.answer("🎬 " + random.choice(FUNNY_STATUSES), **reply_kwargs)
    async def update_status(text: str):
        if status_message:
            try:
                await safe_edit_text(status_message, text)
            except Exception:
                pass

    try:
        search_methods = [
            ("youtube", f"ytsearch1:{refined_query} official audio"),
            ("yt music", f"ytmcustomsearch:{refined_query} song")
        ]
        
        file_path, thumbnail_path, metadata = None, None, {}
        successful_platform = "youtube"
        last_error = None
        search_url = search_methods[-1][1]
        
        for platform_name, s_url in search_methods:
            try:
                # Removed detailed platform search status to avoid spamming the user
                file_path, thumbnail_path, metadata = await download_media(s_url, is_music=True, progress_callback=update_status, min_duration=60)
                
                # Check if download was successful
                if file_path and (isinstance(file_path, list) or file_path.exists()):
                    successful_platform = platform_name
                    search_url = s_url  # For later use in metadata/logging
                    break
            except Exception as e:
                last_error = e
                logging.info(f"Search failed on {platform_name}: {e}")
                continue
                
        if not file_path:
            raise last_error or Exception("All search methods failed.")

        display_name, stored_name, handle = resolve_user_identity(message.from_user)
        stats.add_active_user(message.from_user.id)
        video_url = metadata.get('webpage_url', search_url)
        
        if isinstance(file_path, list) and file_path:
            file_path = file_path[0]
            
        if file_path.exists():
            await update_status("📤 Uploading to Telegram...")
            
            # Wait for parallel metadata task to complete
            rich_meta = {}
            try:
                rich_meta = await metadata_task
            except Exception as e:
                logging.warning(f"Metadata task failed: {e}")

            # Enrich metadata before caption formatting
            if rich_meta.get("title"):
                metadata['title'] = rich_meta["title"]
            if rich_meta.get("artist"):
                metadata['uploader'] = rich_meta["artist"]
            
            history_title = metadata.get('title') or file_path.stem
            
            # Record download stats and log
            stats.add_download(
                content_type='Music',
                user_id=message.from_user.id,
                username=stored_name,
                platform=successful_platform,
                url=video_url,
                title=history_title
            )

            download_logger.info(
                f"User: {display_name} ({handle}, ID: {message.from_user.id}) | "
                f"Platform: {successful_platform} | "
                f"Type: Music (search) | "
                f"Query: {query} | "
                f"URL: {video_url} | "
                f"Title: {history_title}"
            )
            
            caption = format_caption(metadata, successful_platform, video_url, is_music=True)
            
            # Override thumbnail with high-res cover if available
            local_cover_path_str = rich_meta.get("local_cover_path")
            if local_cover_path_str and Path(local_cover_path_str).exists():
                thumbnail_path = Path(local_cover_path_str)
                
            audio_kwargs = {
                "audio": types.FSInputFile(file_path),
                "duration": int(metadata.get('duration', 0)),
                "caption": caption,
                "parse_mode": "HTML",
                **reply_kwargs
            }
            
            if thumbnail_path and thumbnail_path.exists():
                audio_kwargs["thumbnail"] = types.FSInputFile(thumbnail_path)
            if rich_meta.get("title"):
                audio_kwargs["title"] = rich_meta["title"]
            if rich_meta.get("artist"):
                audio_kwargs["performer"] = rich_meta["artist"]

            await message.answer_audio(**audio_kwargs)

            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists():
                try:
                    thumbnail_path.unlink()
                except Exception:
                    pass
            # Clean up the alternative cover just in case
            if local_cover_path_str and Path(local_cover_path_str).exists():
                try:
                    Path(local_cover_path_str).unlink()
                except Exception:
                    pass
                    
            if status_message:
                await status_message.delete()
        else:
            if status_message:
                await safe_edit_text(status_message, "❌ Sorry, something went wrong during download.")

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Search error: {error_msg}")
        try:
            if 'file_path' in locals() and file_path:
                if isinstance(file_path, list):
                    for p in file_path:
                        if p.exists(): p.unlink()
                elif file_path.exists():
                    file_path.unlink()
            if 'thumbnail_path' in locals() and thumbnail_path and thumbnail_path.exists():
                thumbnail_path.unlink()
        except Exception:
            pass

        if is_group:
            return

        user_error = (
            f"❌ Could not find or download the song.\n\n"
            f"```error\n{error_msg}\n```\n\n"
            f"Contact with developer @datapeice"
        )
        if status_message:
            await safe_edit_text(status_message, user_error, parse_mode='Markdown')
        else:
            await message.answer(user_error, parse_mode='Markdown', **reply_kwargs)


@router.message(lambda m: m.document and m.document.file_name and m.document.file_name.lower().endswith('.torrent'))
async def handle_torrent(message: types.Message, bot: Bot):
    """Initial entry for torrent files. Asks for confirmation in groups."""
    if stats.whitelisted_users and not stats.is_whitelisted(message.from_user.username):
        if message.chat.type == 'private':
            await message.answer("⛔ Sorry, this bot is private. You are not in the whitelist.")
        return

    if message.chat.type != 'private':
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="📥 Download Media from Torrent", callback_data=f"torrent:dl:{message.document.file_id}"))
        await message.reply(
            "📦 <b>Torrent detected</b>\nDo you want to download media files from this torrent?",
            reply_markup=builder.as_markup(),
            parse_mode='HTML'
        )
        return

    # In private chat, start automatically
    await process_torrent_download(message, message.document.file_id, bot, is_file_id=True)

@router.callback_query(F.data.startswith("torrent:dl:"))
async def handle_torrent_confirm(callback: types.CallbackQuery, bot: Bot):
    """Processes confirmation from group chat."""
    file_id = callback.data.split(":")[2]
    await callback.answer("Starting download...")
    # Edit original message to show progress
    status_msg = await callback.message.edit_text("🎬 Initializing torrent download...")
    await process_torrent_download(callback.message, file_id, bot, status_message=status_msg, is_file_id=True)

async def process_torrent_download(event: Union[types.Message, types.ChosenInlineResult], source: str, bot: Bot, status_message: types.Message = None, is_file_id: bool = False):
    """Core logic to download and upload torrent content."""
    user_id = event.from_user.id
    profile = stats.get_user_profile(user_id)
    is_premium = bool(profile.get("is_premium") if isinstance(profile, dict) else profile.is_premium)

    if not is_premium:
        limits_enabled = stats.get_app_setting("premium_limits_enabled", "True") == "True"
        if limits_enabled:
            daily_downloads = profile.get("daily_premium_site_downloads", 0) if isinstance(profile, dict) else profile.daily_premium_site_downloads
            if daily_downloads >= 5:
                if status_message: await status_message.delete()
                # Use answer method depending on event type
                if isinstance(event, types.Message):
                    await event.answer("❌ You have reached your daily limit of 5 downloads.\n⭐️ Donate 50+ stars (/donate) to unlock Premium and remove limits!")
                return

    display_name, stored_name, handle = resolve_user_identity(event.from_user)
    sem = user_sems.premium_sems[user_id]

    # Don't ask the user to wait via message if the semaphore is available.
    queued_msg = None
    if sem.locked():
        if isinstance(event, types.Message):
            queued_msg = await bot.send_message(event.chat.id, "⏳ Your torrent download is queued due to concurrent limits. Please wait...")

    await sem.acquire()
    
    if queued_msg:
        try:
            await queued_msg.delete()
        except:
            pass
    dest_chat_id = event.chat.id if isinstance(event, types.Message) else user_id
    
    if not status_message:
        status_message = await bot.send_message(dest_chat_id, "🎬 Processing torrent...")
    
    async def update_status(text: str):
        try:
            await safe_edit_text(status_message, f"🎬 {text}")
        except Exception:
            pass

    torrent_path = None
    download_dir = None
    
    try:
        if is_file_id:
            # 1. Download .torrent file to temporary location
            torrent_path = DOWNLOADS_DIR / f"temp_{uuid.uuid4().hex[:8]}.torrent"
            await bot.download(source, destination=str(torrent_path))
            torrent_source = torrent_path
        else:
            torrent_source = source
        
        # 2. Get file info and check for 2GB limit
        await update_status("Analyzing torrent content...")
        torrent_info = await torrent_service.get_torrent_info(torrent_source)
        
        files_info = torrent_info.get('files', [])
        total_size = torrent_info.get('total_size', 0)
        
        MAX_SIZE = 2 * 1024 * 1024 * 1024 # 2GB
        
        if files_info:
            # Check individual files known before download
            for f in files_info:
                if f['size'] > MAX_SIZE:
                    raise Exception(f"File '{f['path']}' is too large ({f['size_str']}). Telegram limit is 2GB.")
                
        # 3. Start download via aria2c
        await update_status("Starting torrent download (this might take a while)...")
        media_files, download_dir = await torrent_service.download_torrent(torrent_source, progress_callback=update_status)
        
        if not media_files:
            # Check if there were ANY files or just none match media extensions
            all_files_count = len(list(download_dir.rglob("*")))
            if all_files_count > 0:
                raise Exception("No media files (video/audio) found in the torrent, only other file types.")
            raise Exception("Download completed but no files were found. Check the torrent health.")
            
        # 4. Upload to Telegram
        await update_status(f"Found {len(media_files)} media files. Uploading to Telegram...")
        
        for i, file_path in enumerate(media_files):
            if not file_path.exists(): continue
            
            # Per-file size check before upload (Telegram bot limit is 2GB)
            file_size = file_path.stat().st_size
            if file_size > MAX_SIZE:
                size_str = f"{file_size / (1024**3):.1f}GB"
                await bot.send_message(dest_chat_id, f"⚠️ Skipping <b>{file_path.name}</b>: File is too large ({size_str}). Telegram limit is 2GB.", parse_mode='HTML')
                continue
                
            ext = file_path.suffix.lower()
            file_num = f"({i+1}/{len(media_files)}) " if len(media_files) > 1 else ""
            caption = f"📦 {file_num}<b>{file_path.name}</b>\n\nDownloaded via Torrent | Developed by @datapeice"
            
            # Retry logic for FloodControl and pause
            for attempt in range(4):
                try:
                    # Video extensions
                    if ext in {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts'}:
                        duration = await probe_media_duration_seconds(file_path)
                        await bot.send_video(
                            dest_chat_id,
                            types.FSInputFile(file_path),
                            caption=caption,
                            duration=duration,
                            supports_streaming=True,
                            parse_mode='HTML'
                        )
                    # Audio extensions
                    elif ext in {'.flac', '.mp3', '.m4a', '.wav', '.ogg', '.opus'}:
                        await bot.send_audio(
                            dest_chat_id,
                            types.FSInputFile(file_path),
                            caption=caption,
                            parse_mode='HTML'
                        )
                    # Fallback for other media as documents
                    else:
                        await bot.send_document(
                            dest_chat_id,
                            types.FSInputFile(file_path),
                            caption=caption,
                            parse_mode='HTML'
                        )
                    break  # Success
                except TelegramRetryAfter as e:
                    sleep_time = e.retry_after + 1
                    logging.warning(f"Torrent upload flood control: sleeping for {sleep_time}s")
                    await asyncio.sleep(sleep_time)
                except Exception as e:
                    logging.error(f"Failed to upload torrent file {file_path.name}: {e}")
                    prompt_msg = f"❌ Failed to upload {file_path.name[:50]}: {str(e)[:50]}..."
                    await bot.send_message(dest_chat_id, prompt_msg)
                    break  # Don't retry on non-flood errors
            
            # Add a small pause between files to prevent sending messages too fast
            if i < len(media_files) - 1:
                await asyncio.sleep(2.5)
                
        await status_message.delete()
        # Extract original tracker URL if possible
        tracker_url = "Torrent"
        if torrent_path:
            tracker_url = torrent_service.extract_tracker_url(torrent_path) or "Torrent"
        elif isinstance(torrent_source, str) and torrent_source.startswith("http"):
            tracker_url = torrent_source
        # Record stat once for the whole torrent
        torrent_name = torrent_info.get('name', 'Torrent')
        stats.add_download('Torrent', user_id, stored_name, 'torrent', 'torrent_file', tracker_url, title=torrent_name)
        download_logger.info(
            f"User: {display_name} ({handle}, ID: {user_id}) | "
            f"Platform: torrent | "
            f"Type: Torrent | "
            f"URL: {tracker_url} | "
            f"Title: {torrent_name}"
        )
        
        # Torrent successfully sent, increment daily limit for free users
        if not is_premium:
            stats.increment_daily_premium(user_id)

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Torrent handling error: {error_msg}")
        await safe_edit_text(status_message, f"❌ Torrent error: {error_msg}")
        
    finally:
        # Cleanup torrent file if it was downloaded from TG
        if torrent_path and torrent_path.exists():
            try: torrent_path.unlink()
            except: pass
        
        # Cleanup torrent directory and all its content
        if download_dir and download_dir.exists():
            try:
                import shutil
                shutil.rmtree(download_dir)
            except Exception as e:
                logging.error(f"Failed to cleanup torrent dir {download_dir}: {e}")

        if 'sem' in locals() and sem:
            sem.release()

from collections import defaultdict
import asyncio

class UserSemaphores:
    def __init__(self):
        self.standard_sems = defaultdict(lambda: asyncio.Semaphore(2))
        self.premium_sems = defaultdict(lambda: asyncio.Semaphore(1))

user_sems = UserSemaphores()

STANDARD_SITES = ["tiktok", "instagram", "facebook", "youtube", "youtu.be"]

def is_premium_site(url: str) -> bool:
    if not url: return False
    url_lower = url.lower()
    return not any(domain in url_lower for domain in STANDARD_SITES)

@router.message(lambda m: m.text and not m.text.startswith(('/start', '/panel', '/whitelist', '/unwhitelist', 'add @', '/song')) and not m.text.lower().startswith('найти ') and not m.text.lower().startswith('search '))
async def handle_url(message: types.Message, bot: Bot):
    # Accept any URL-like string or magnet link
    sem = None
    sem_acquired = False
    url_pattern = r'(?:https?://|www\.|magnet:\?xt=urn:btih:)[^\s<>"]+'
    
    match = re.search(url_pattern, message.text)
    if not match:
        return
        
    target_url = match.group(0)
    user_id = message.from_user.id
    
    reply_kwargs = {}
    if message.chat.type != 'private':
        reply_kwargs['reply_to_message_id'] = message.message_id
        stats.add_active_group(message.chat.id)
    
    # Premium logic check
    profile = stats.get_user_profile(user_id)
    is_premium = bool(profile.get("is_premium") if isinstance(profile, dict) else profile.is_premium)
    is_prem_site = is_premium_site(target_url)
    is_torrent_magnet = target_url.startswith("magnet:") or target_url.endswith(".torrent")
    
    if (is_prem_site or is_torrent_magnet) and not is_premium:
        limits_enabled = stats.get_app_setting("premium_limits_enabled", "True") == "True"
        if limits_enabled:
            daily_downloads = profile.get("daily_premium_site_downloads", 0) if isinstance(profile, dict) else profile.daily_premium_site_downloads
            if daily_downloads >= 5:
                await message.answer("❌ You have reached your daily limit of 5 downloads from premium sites / torrents.\n⭐️ Donate 50+ stars (/donate) to unlock Premium and remove limits!")
                return

    # Semaphore selection
    is_torrent_magnet = target_url.startswith("magnet:") or target_url.endswith(".torrent")
    if is_prem_site or is_torrent_magnet:
        sem = user_sems.premium_sems[user_id]
    elif not is_premium:
        sem = user_sems.standard_sems[user_id]
        
    queued_msg = None
    if sem and sem.locked():
        queued_msg = await message.answer("⏳ Your download is queued due to concurrent limits. Please wait...")

    if sem:
        await sem.acquire()
        sem_acquired = True
    
    if queued_msg:
        try:
            await queued_msg.delete()
        except:
            pass

    # Validate Pornhub URLs - must have viewkey parameter
    if "pornhub.com" in target_url.lower():
        if "viewkey=" not in target_url:
            await message.answer(
                "❌ Invalid Pornhub URL!\n\n"
                "The URL must contain a video ID (viewkey parameter).\n"
                "Example: https://www.pornhub.com/view_video.php?viewkey=xxxxx\n\n"
                "Please copy the full URL from the video page.",
                **reply_kwargs
            )
            return

    # Whitelist check
    if stats.whitelisted_users and not stats.is_whitelisted(message.from_user.username):
        await message.answer("⛔ Sorry, this bot is private. You are not in the whitelist.", **reply_kwargs)
        return

    is_group = message.chat.type != 'private'

    try:
        platform = get_platform(target_url)
        if platform == "torrent":
            await process_torrent_download(message, target_url, bot, is_file_id=False)
            return

        if platform == "unknown":
            if not is_group:
                await message.answer("Sorry, this platform is not supported.", **reply_kwargs)
            return

        if platform == "youtube" and not is_youtube_music(target_url) and "/shorts/" not in target_url.lower():
            if is_playlist(target_url):
                request_id = str(uuid.uuid4())[:8]
                url_cache[request_id] = target_url
                builder = InlineKeyboardBuilder()
                builder.add(
                    InlineKeyboardButton(text="🎵 Tracks separately", callback_data=f"plist:each:{request_id}"),
                    InlineKeyboardButton(text="📦 ZIP Pack", callback_data=f"plist:zip:{request_id}")
                )
                builder.adjust(1)
                await message.answer("📁 YouTube Playlist detected!\nHow would you like to download it?", reply_markup=builder.as_markup(), **reply_kwargs)
                return

            request_id = str(uuid.uuid4())[:8]
            url_cache[request_id] = target_url
            
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"format:audio:{request_id}"),
                InlineKeyboardButton(text="🎥 Video", callback_data=f"format:video:{request_id}")
            )
            await message.answer("Choose download format:", reply_markup=builder.as_markup(), **reply_kwargs)
            return

        if is_youtube_music(target_url) and is_playlist(target_url):
            request_id = str(uuid.uuid4())[:8]
            url_cache[request_id] = target_url
            builder = InlineKeyboardBuilder()
            builder.add(
                    InlineKeyboardButton(text="🎵 Tracks separately", callback_data=f"plist:each:{request_id}"),
                    InlineKeyboardButton(text="📦 ZIP Pack", callback_data=f"plist:zip:{request_id}")
            )
            builder.adjust(1)
            await message.answer("🎹 YouTube Music Album/Playlist detected!\nHow would you like to download it?", reply_markup=builder.as_markup(), **reply_kwargs)
            return

        is_youtube = platform == "youtube" or 'youtu.be' in target_url or 'youtube.com' in target_url
        status_message = None
        if is_group and not is_youtube:
            # Stealth mode for groups (no funny status messages)
            async def update_status(text: str):
                pass
        else:
            status_message = await message.answer("🎬 Starting...", **reply_kwargs)
            async def update_status(text: str):
                try:
                    await safe_edit_text(status_message, text)
                except Exception:
                    pass

        is_music = is_youtube_music(target_url) or platform == "soundcloud"
        file_path, thumbnail_path, metadata = await download_media(target_url, is_music, progress_callback=update_status)

        # Determine title based on file_path type
        if isinstance(file_path, list):
            title = metadata.get('title', 'TikTok Slideshow')
        else:
            title = file_path.stem

        display_name, stored_name, handle = resolve_user_identity(message.from_user)
        stats.add_active_user(message.from_user.id)
        stats.add_download(
            content_type='Music' if is_music else 'Video',
            user_id=message.from_user.id,
            username=stored_name,
            platform=platform,
            url=target_url,
            title=title
        )

        user_id = message.from_user.id
        download_logger.info(
            f"User: {display_name} ({handle}, ID: {user_id}) | "
            f"Platform: {platform} | "
            f"Type: {'Music' if is_music else 'Video'} | "
            f"URL: {target_url}"
        )

        if isinstance(file_path, list):
            await update_status("📤 Uploading slideshow to Telegram...")
            
            # Separate media types
            image_exts = ['.jpg', '.jpeg', '.png', '.webp']
            video_exts = ['.mp4', '.mov', '.webm', '.mkv']
            audio_exts = ['.mp3', '.m4a', '.wav']

            image_files = [f for f in file_path if f.suffix.lower() in image_exts]
            video_files = [f for f in file_path if f.suffix.lower() in video_exts]
            audio_files = [f for f in file_path if f.suffix.lower() in audio_exts]
            
            # Prepare unified caption
            caption = format_caption(metadata, platform, target_url, is_music=is_music)

            media_group = []
            ordered_files = sorted(image_files + video_files, key=lambda p: p.name)
            for i, media_path in enumerate(ordered_files):
                caption_text = caption if i == 0 else ""
                parse_mode = 'HTML' if i == 0 else None
                if media_path.suffix.lower() in image_exts:
                    media_item = types.InputMediaPhoto(
                        media=types.FSInputFile(media_path),
                        caption=caption_text,
                        parse_mode=parse_mode
                    )
                else:
                    media_item = types.InputMediaVideo(
                        media=types.FSInputFile(media_path),
                        caption=caption_text,
                        parse_mode=parse_mode,
                        supports_streaming=True
                    )
                media_group.append(media_item)

            # Split into chunks of 10 (Telegram limit)
            if media_group:
                chunk_size = 10
                for i in range(0, len(media_group), chunk_size):
                    chunk = media_group[i:i + chunk_size]
                    
                    # Retry logic for FloodControl
                    for attempt in range(3):
                        try:
                            await message.answer_media_group(chunk, **reply_kwargs)
                            break
                        except TelegramRetryAfter as e:
                            logging.warning(f"Flood control: sleeping for {e.retry_after}s")
                            await asyncio.sleep(e.retry_after)
                        except Exception as e:
                            logging.error(f"Error sending media group chunk: {e}")
                            break
            
            # Send audio separately if available
            if audio_files:
                for audio_path in audio_files:
                    try:
                        await message.answer_audio(
                            types.FSInputFile(audio_path),
                            **reply_kwargs
                        )
                    except Exception as e:
                        logging.error(f"Failed to send audio: {e}")

            # Cleanup
            for photo_path in file_path:
                try:
                    photo_path.unlink()
                except Exception:
                    pass
            if status_message:
                await status_message.delete()

        elif file_path.exists():
            await update_status("📤 Uploading to Telegram...")
            
            # Use unified caption format
            caption = format_caption(metadata, platform, target_url, is_music=is_music)

            image_exts = ['.jpg', '.jpeg', '.png', '.webp']
            if file_path.suffix.lower() in image_exts:
                await message.answer_photo(
                    types.FSInputFile(file_path),
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=get_random_support_kb(),
                    **reply_kwargs
                )
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                if status_message:
                    await status_message.delete()
                return

            if is_music:
                if thumbnail_path:
                    await message.answer_audio(
                        types.FSInputFile(file_path), 
                        thumbnail=types.FSInputFile(thumbnail_path),
                        duration=int(metadata.get('duration', 0)),
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=get_random_support_kb(),
                        **reply_kwargs
                    )
                else:
                    await message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=int(metadata.get('duration', 0)),
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=get_random_support_kb(),
                        **reply_kwargs
                    )
            else:
                duration_value = int(metadata.get('duration', 0))
                if duration_value <= 0:
                    duration_value = await probe_media_duration_seconds(file_path)

                video_kwargs = {
                    'video': types.FSInputFile(file_path),
                    'duration': duration_value,
                    'supports_streaming': True,
                    'caption': caption,
                    'parse_mode': 'HTML',
                    'reply_markup': get_random_support_kb()
                }
                
                if metadata.get('width') and metadata.get('height'):
                    video_kwargs['width'] = int(metadata.get('width'))
                    video_kwargs['height'] = int(metadata.get('height'))
                
                if thumbnail_path:
                   video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                logging.info(f"Sending video with kwargs: {video_kwargs}")
                
                # Measure upload time to Telegram
                upload_start = time.time()
                await message.answer_video(**video_kwargs, **reply_kwargs)
                upload_time = time.time() - upload_start
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                logging.info(f"✅ Video uploaded to Telegram in {upload_time:.1f}s ({file_size_mb:.2f}MB, {file_size_mb/upload_time:.2f}MB/s)")
            
            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists():
                thumbnail_path.unlink()
            if status_message:
                await status_message.delete()
        else:
            if status_message:
                await safe_edit_text(status_message, "Sorry, something went wrong during download.")
    
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Error: {error_msg}")
        try:
            if "file_path" in locals() and file_path:
                if isinstance(file_path, list):
                    for p in file_path:
                        if p.exists(): p.unlink()
                elif file_path.exists(): file_path.unlink()
            if "thumbnail_path" in locals() and thumbnail_path and thumbnail_path.exists(): thumbnail_path.unlink()
        except Exception:
            pass
        
        # In group chats, silently ignore all errors to avoid noise
        if is_group:
            return

        # User-friendly error messages
        if "Unsupported URL" in error_msg:
            user_error = "❌ This URL is not supported. Please try a different link."
        elif "Private video" in error_msg or "Login required" in error_msg:
            user_error = "❌ This video is private or requires login."
        elif "Sign in to confirm" in error_msg:
            user_error = "⚠️ YouTube requires authentication (cookies). Please contact the bot admin."
        else:
            user_error = (
                f"```error\n{error_msg}\n```\n\n"
                f"Contact with developer @datapeice"
            )
        
        if status_message:
            await safe_edit_text(status_message, user_error, parse_mode='Markdown' if '```' in user_error else None)
        else:
            await message.answer(user_error, parse_mode='Markdown' if '```' in user_error else None, **reply_kwargs)
            
    finally:
        if sem_acquired:
            sem.release()
            
        # Daily limit increment for free users for premium sites/torrents
        if sem_acquired and 'error_msg' not in locals() and not is_premium and (is_prem_site or platform == "torrent"):
            stats.increment_daily_premium(user_id)

@router.callback_query(F.data.startswith("format:"))
async def handle_format_selection(callback: types.CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        _, format_type, request_id = callback.data.split(":", 2)
        
        url = url_cache.get(request_id)
        if not url:
            error_text = "⚠️ Request expired. Please send the link again."
            if callback.inline_message_id:
                await bot.edit_message_text(error_text, inline_message_id=callback.inline_message_id)
            else:
                await callback.message.edit_text(error_text)
            return

        if format_type == "video":
            builder = InlineKeyboardBuilder()
            resolutions = [("1080p", 1080), ("720p", 720), ("480p", 480), ("360p", 360)]
            for label, height in resolutions:
                builder.add(InlineKeyboardButton(text=label, callback_data=f"dl_res:{request_id}:{height}"))
            builder.adjust(2)
            
            prompt_text = "Select video quality:"
            if callback.inline_message_id:
                await bot.edit_message_text(prompt_text, inline_message_id=callback.inline_message_id, reply_markup=builder.as_markup())
            else:
                await callback.message.edit_text(prompt_text, reply_markup=builder.as_markup())
            return

        # Audio Path
        start_text = "⏳ Starting..."
        if callback.inline_message_id:
            await bot.edit_message_text(start_text, inline_message_id=callback.inline_message_id)
        else:
            await callback.message.edit_text(start_text)
        
        async def update_status(text: str):
            try:
                if callback.inline_message_id:
                    await bot.edit_message_text(text, inline_message_id=callback.inline_message_id)
                else:
                    await callback.message.edit_text(text)
            except Exception:
                pass
        
        try:
            is_music = True
            file_path, thumbnail_path, metadata = await download_media(url, is_music, progress_callback=update_status)

            display_name, stored_name, handle = resolve_user_identity(callback.from_user)
            stats.add_active_user(callback.from_user.id)
            stats.add_download(
                content_type='Music',
                user_id=callback.from_user.id,
                username=stored_name,
                platform='youtube',
                url=url,
                title=file_path.stem if not isinstance(file_path, list) else metadata.get('title', 'Media')
            )

            user_id = callback.message.chat.id if callback.message else callback.from_user.id
            if file_path.exists():
                await update_status("📤 Uploading to Telegram...")
                caption = format_caption(metadata, 'youtube', url, is_music=is_music)

                # Prepare reply arguments for groups
                delivery_reply_kwargs = {}
                if callback.message and callback.message.chat.type != 'private':
                    # Use the same reply logic as messages
                    if "reply_to_message_id" in callback.message.text: # Logic check - actually use message_id of original trigger if possible, but callback.message is the bot's own prompt
                         pass # We'll just send to chat for now as callback.message is the bot's message

                sent = await bot.send_audio(
                    chat_id=user_id,
                    audio=types.FSInputFile(file_path),
                    thumbnail=types.FSInputFile(thumbnail_path) if thumbnail_path else None,
                    duration=int(metadata.get('duration', 0)),
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=get_random_support_kb()
                )
                
                if callback.inline_message_id:
                    media = types.InputMediaAudio(media=sent.audio.file_id, caption=caption, parse_mode='HTML')
                    await bot.edit_message_media(media=media, inline_message_id=callback.inline_message_id)
                    # Delete from PM after sending to inline
                    try: await sent.delete()
                    except: pass
                
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                
                if not callback.inline_message_id:
                    try: await callback.message.delete()
                    except: pass
            else:
                await update_status("❌ Error: Download failed.")

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error in audio selection: {error_msg}")
            await update_status(f"❌ Error: {error_msg[:100]}")
            try:
                if 'file_path' in locals() and file_path:
                    if isinstance(file_path, list):
                        for p in file_path:
                            if p.exists(): p.unlink()
                    elif file_path.exists(): file_path.unlink()
                if 'thumbnail_path' in locals() and thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
            except: pass

    except Exception as e:
        logging.error(f"Error in handle_format_selection: {str(e)}")

@router.callback_query(F.data.startswith("dl_res:"))
async def handle_resolution_selection(callback: types.CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        _, request_id, height = callback.data.split(":", 2)
        
        url = url_cache.get(request_id)
        if not url:
            error_text = "⚠️ Request expired. Please send the link again."
            if callback.inline_message_id:
                await bot.edit_message_text(error_text, inline_message_id=callback.inline_message_id)
            else:
                await callback.message.edit_text(error_text)
            return

        start_text = f"⏳ Downloading video ({height}p)..."
        if callback.inline_message_id:
            await bot.edit_message_text(start_text, inline_message_id=callback.inline_message_id)
        else:
            await callback.message.edit_text(start_text)
        
        async def update_status(text: str):
            try:
                if callback.inline_message_id:
                    await bot.edit_message_text(text, inline_message_id=callback.inline_message_id)
                else:
                    await callback.message.edit_text(text)
            except Exception:
                pass
        
        try:
            file_path, thumbnail_path, metadata = await download_media(
                url,
                is_music=False,
                video_height=int(height),
                progress_callback=update_status
            )

            display_name, stored_name, handle = resolve_user_identity(callback.from_user)
            stats.add_active_user(callback.from_user.id)
            stats.add_download(
                content_type='Video',
                user_id=callback.from_user.id,
                username=stored_name,
                platform='youtube',
                url=url,
                title=file_path.stem if not isinstance(file_path, list) else metadata.get('title', 'Media')
            )

            user_id = callback.message.chat.id if callback.message else callback.from_user.id
            if file_path.exists():
                await update_status("📤 Uploading to Telegram...")
                caption = format_caption(metadata, 'youtube', url, is_music=False)

                duration_value = int(metadata.get('duration', 0))
                if duration_value <= 0:
                    duration_value = await probe_media_duration_seconds(file_path)

                video_kwargs = {
                    'video': types.FSInputFile(file_path),
                    'duration': duration_value,
                    'supports_streaming': True,
                    'caption': caption,
                    'parse_mode': 'HTML',
                    'reply_markup': get_random_support_kb()
                }
                
                if metadata.get('width') and metadata.get('height'):
                    video_kwargs['width'] = int(metadata.get('width'))
                    video_kwargs['height'] = int(metadata.get('height'))
                
                if thumbnail_path:
                   video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                sent = await bot.send_video(chat_id=user_id, **video_kwargs)
                
                if callback.inline_message_id:
                    media = types.InputMediaVideo(media=sent.video.file_id, caption=caption, parse_mode='HTML')
                    await bot.edit_message_media(media=media, inline_message_id=callback.inline_message_id)
                    # Delete from PM after sending to inline
                    try: await sent.delete()
                    except: pass
                
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                
                if not callback.inline_message_id:
                    try: await callback.message.delete()
                    except: pass
            else:
                await update_status("❌ Error: Download failed.")

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error in video resolution process: {error_msg}")
            await update_status(f"❌ Error: {error_msg[:100]}")
            try:
                if 'file_path' in locals() and file_path:
                    if isinstance(file_path, list):
                        for p in file_path:
                            if p.exists(): p.unlink()
                    elif file_path.exists(): file_path.unlink()
                if 'thumbnail_path' in locals() and thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
            except: pass

    except Exception as e:
        logging.error(f"Error in handle_resolution_selection: {str(e)}")

@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    text = inline_query.query.strip()
    
    # URL pattern
    url_pattern = r'(?:https?://|www\.|magnet:\?xt=urn:btih:)[^\s<>"]+'
    
    # 1. If empty or not a URL, show "Paste a link"
    match = re.search(url_pattern, text)
    if not text or not match:
        item = InlineQueryResultArticle(
            id="paste_link_hint",
            title="🔗 Paste a link / Отправьте ссылку",
            description="Type or paste a link to download media",
            input_message_content=InputTextMessageContent(
                message_text="You need to provide a link to download media.\nExample: `@bot https://tiktok.com/...`"
            )
        )
        await inline_query.answer(results=[item], cache_time=3600, is_personal=False)
        return
        
    # 2. Recognized URL
    url = match.group(0)
    platform = get_platform(url)
    
    # Store in cache for chosen_result handler
    request_id = str(uuid.uuid4())[:8]
    url_cache[request_id] = url
    
    item = InlineQueryResultArticle(
        id=f"dl:{request_id}",
        title="Download video",
        description=f"Format: {platform} URL",
        input_message_content=InputTextMessageContent(
            message_text=url  # Sending the URL so chosen_result can pick it up
        ),
        reply_markup=InlineKeyboardBuilder().add(
            InlineKeyboardButton(text="⏳", callback_data="none")
        ).as_markup()
    )
    
    await inline_query.answer(results=[item], cache_time=300, is_personal=False)

@router.callback_query(F.data.startswith("plist:"))
async def handle_playlist_selection(callback: types.CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        action, request_id = callback.data.split(":", 2)[1:]
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id if callback.message else user_id
        message_id = callback.message.message_id if callback.message else None
        inline_message_id = callback.inline_message_id
        
        url = url_cache.get(request_id)
        if not url:
            if callback.message:
                await callback.message.edit_text("⚠️ Request expired. Please send the link again.")
            return

        status_msg = await callback.message.edit_text("⏳ Processing playlist, please wait...")
        
        async def update_status(text: str):
            try: await safe_edit_text(status_msg, text)
            except: pass

        is_music = "music.youtube.com" in url or action in ('each', 'zip')
        
        async def on_track_ready(res, i, total):
            if action != 'each': return
            
            file_path, thumbnail_path, metadata = res
            try:
                caption = format_caption(metadata, 'youtube', metadata.get('webpage_url', url), is_music=True)
                audio_kwargs = {
                    "audio": types.FSInputFile(file_path),
                    "duration": int(metadata.get('duration', 0)),
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                if thumbnail_path and thumbnail_path.exists():
                    audio_kwargs["thumbnail"] = types.FSInputFile(thumbnail_path)
                
                await bot.send_audio(chat_id, **audio_kwargs)
                # Small delay to avoid Telegram flood limits
                await asyncio.sleep(1.5)
            except Exception as e:
                logging.error(f"Error sending track {i} (streaming): {e}")

        # Start download
        results = await download_media(
            url, 
            is_music=True, 
            progress_callback=update_status,
            on_track_callback=on_track_ready if action == 'each' else None
        )
        
        if not results or not isinstance(results, list):
            await update_status("❌ Failed to process playlist or it's empty.")
            return

        if action == 'each':
            await status_msg.delete()
            kb = InlineKeyboardBuilder()
            kb.add(InlineKeyboardButton(text="⭐️ Support", callback_data="donate"))
            
            await bot.send_message(
                chat_id, 
                f"✅ All {len(results)} tracks from playlist sent individually!",
                reply_markup=kb.as_markup()
            )
            # Cleanup all tracked files
            for res_item in results:
                file_path, thumb_path, _ = res_item
                # file_path might be a list (slideshow) or a Path
                if isinstance(file_path, list):
                    for p in file_path:
                        if p.exists(): p.unlink()
                elif file_path.exists(): 
                    file_path.unlink()
                    
                if thumb_path and isinstance(thumb_path, Path) and thumb_path.exists(): 
                    thumb_path.unlink()

        elif action == 'zip':
            await update_status("📦 Creating ZIP archive...")
            
            files = [r[0] for r in results]
            # Try to get a decent name for the ZIP
            zip_name = "youtube_playlist"
            if results and results[0][2].get('title'):
                zip_name = f"playlist_{results[0][2].get('title')[:20]}"
            
            secure_id = zip_service.create_playlist_zip(files, zip_name)
            
            # Use the user's domain
            download_url = f"https://bot.datapeice.me/dl/{secure_id}"
            
            kb = InlineKeyboardBuilder()
            kb.add(InlineKeyboardButton(text="⬇️ Download ZIP", url=download_url))
            kb.add(InlineKeyboardButton(text="⭐️ Support Bot", callback_data="show_donate_menu"))
            kb.adjust(1)
            
            await status_msg.delete()
            await bot.send_message(
                user_id,
                f"📦 <b>Playlist ZIP is ready!</b>\n\n"
                f"Contains: <b>{len(files)}</b> tracks\n"
                f"Valid for: <b>24 hours</b>\n\n"
                f"Your private link:\n<code>{download_url}</code>",
                reply_markup=kb.as_markup(),
                parse_mode='HTML'
            )
            
            # Cleanup source files
            for file_path, thumb_path, _ in results:
                if file_path.exists(): file_path.unlink()
                if thumb_path and thumb_path.exists(): thumb_path.unlink()

        # Stats
        display_name, stored_name, handle = resolve_user_identity(callback.from_user)
        stats.add_download(
            content_type='Playlist',
            user_id=user_id,
            username=stored_name,
            platform='youtube',
            url=url,
            title=f"Playlist ({len(results)} items)"
        )

    except Exception as e:
        logging.error(f"Playlist handler error: {e}")
        try: await callback.message.edit_text(f"❌ Error processing playlist: {str(e)}")
        except: pass

@router.chosen_inline_result()
async def handle_inline_result_chosen(chosen_result: types.ChosenInlineResult, bot: Bot):
    inline_message_id = chosen_result.inline_message_id
    try:
        result_id = chosen_result.result_id
        
        if not inline_message_id:
            logging.warning("No inline_message_id provided. Ensure result has a reply_markup.")
            return

        # Extract request_id from result_id (format: "dl:xxxxxxxx")
        request_id = result_id.split(":", 1)[1] if ":" in result_id else result_id
        target_url = url_cache.get(request_id)

        # Fallback: extract URL from query text
        if not target_url:
            url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
            match = re.search(url_pattern, chosen_result.query.strip())
            if not match:
                return
            target_url = match.group(0)

        platform = get_platform(target_url)
        is_music = is_youtube_music(target_url)

        # Torrent / Magnet handling
        if platform == "torrent":
            await update_status("🎬 Torrent detected. Processing... Results will be sent to your PM.")
            await process_torrent_download(chosen_result, target_url, bot, is_file_id=False)
            return

        # YouTube non-shorts non-music: show format selection buttons
        if platform == "youtube" and not is_music and "/shorts/" not in target_url.lower():
            new_request_id = str(uuid.uuid4())[:8]
            url_cache[new_request_id] = target_url
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"format:audio:{new_request_id}"),
                InlineKeyboardButton(text="🎥 Video", callback_data=f"format:video:{new_request_id}")
            )
            await bot.edit_message_text(
                text="Choose download format:",
                inline_message_id=inline_message_id,
                reply_markup=builder.as_markup()
            )
            return

        async def update_status(text: str):
            try:
                await bot.edit_message_text(text=text, inline_message_id=inline_message_id)
            except: pass

        await update_status("⏳ Downloading...")
        file_path, thumbnail_path, metadata = await download_media(target_url, is_music=is_music, progress_callback=update_status)

        await update_status("📤 Uploading...")

        display_name, stored_name, handle = resolve_user_identity(chosen_result.from_user)
        stats.add_active_user(chosen_result.from_user.id)

        user_id = chosen_result.from_user.id
        caption = format_caption(metadata, platform, target_url, is_music=is_music)

        # Slideshow check
        if isinstance(file_path, list):
            await bot.send_message(user_id, "📤 Uploading slideshow to your PM...")
            image_exts = ['.jpg', '.jpeg', '.png', '.webp']
            ordered_files = sorted(file_path, key=lambda p: p.name)
            media_group = [types.InputMediaPhoto(media=types.FSInputFile(p), caption=caption if i == 0 else "", parse_mode='HTML' if i == 0 else None) for i, p in enumerate(ordered_files) if p.suffix.lower() in image_exts][:10]
            if media_group:
                await bot.send_media_group(user_id, media_group)
            for p in file_path:
                try: p.unlink()
                except: pass
            stats.add_download(
                content_type='Music' if is_music else 'Video',
                user_id=user_id,
                username=stored_name,
                platform=platform,
                url=target_url,
                title=metadata.get('title', 'Slideshow') if metadata else 'Slideshow'
            )
            await update_status("✅ Uploaded to PM!")
            return

        if file_path.exists():
            if is_music:
                sent = await bot.send_audio(
                    user_id,
                    types.FSInputFile(file_path),
                    thumbnail=types.FSInputFile(thumbnail_path) if thumbnail_path else None,
                    caption=caption,
                    parse_mode='HTML'
                )
                media = types.InputMediaAudio(media=sent.audio.file_id, caption=caption, parse_mode='HTML')
            else:
                sent = await bot.send_video(
                    user_id,
                    types.FSInputFile(file_path),
                    thumbnail=types.FSInputFile(thumbnail_path) if thumbnail_path else None,
                    caption=caption,
                    parse_mode='HTML'
                )
                media = types.InputMediaVideo(media=sent.video.file_id, caption=caption, parse_mode='HTML')

            # Update the inline message with the media
            await bot.edit_message_media(media=media, inline_message_id=inline_message_id)

            # Delete from PM after sending to inline
            try: await sent.delete()
            except: pass

            # Clean up
            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists(): thumbnail_path.unlink()

            stats.add_download(
                content_type='music' if is_music else 'video',
                user_id=user_id,
                username=stored_name,
                platform=platform,
                url=target_url,
                title=metadata.get('title', 'Unknown') if metadata else 'Unknown'
            )
        else:
            await update_status("❌ Error: Download failed.")

    except Exception as e:
        logging.error(f"Inline chosen download error: {e}")
        try:
            await bot.edit_message_text(text=f"❌ Error: {str(e)[:100]}", inline_message_id=inline_message_id)
        except:
            pass
