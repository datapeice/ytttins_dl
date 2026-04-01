import uuid
import re
import logging
import asyncio
import time
import subprocess
from pathlib import Path
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from services.downloader import download_media, get_platform, is_youtube_music
from database.storage import stats
from services.logger import download_logger
from config import DOWNLOADS_DIR
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineQuery, ChosenInlineResult, InputMediaVideo, InputMediaAudio, LabeledPrice, PreCheckoutQuery
from services.metadata import fetch_song_metadata

router = Router()
url_cache = {}

def resolve_user_identity(user: types.User) -> tuple[str, str, str]:
    display_name = user.full_name or user.first_name or "Unknown"
    username = user.username or ""
    stored_name = username or display_name
    handle = f"@{username}" if username else display_name
    return display_name, stored_name, handle

def format_caption(metadata: dict, platform: str, original_url: str = "", is_music: bool = False) -> str:
    """Generate unified caption format for all platforms."""
    uploader = metadata.get('uploader') or 'Unknown'
    url = original_url or metadata.get('webpage_url', '')
    
    # Check for verified status in metadata
    is_verified = metadata.get('verified') or metadata.get('creator_is_verified') or metadata.get('uploader_is_verified') or metadata.get('channel_is_verified')
    
    # Strip leading @
    uploader = str(uploader).lstrip('@')
    # Escape HTML special characters in uploader name
    uploader = str(uploader).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    title = metadata.get('title', 'Media')
    title = str(title).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    if is_verified:
        # Use a combination of a visible emoji and custom tg-emoji if supported
        uploader = f"{uploader} <tg-emoji emoji-id=\"5233582409416448551\">✅</tg-emoji>"

    parts = []
    # Only show uploader if it's not "Unknown", or if it's TikTok (where we want to show it anyway)
    if uploader.lower() != "unknown" or platform == "tiktok":
        parts.append(f"👤 {uploader}")
    
    if is_music:
        parts.append(f"<a href=\"{url}\">{title}</a>")
    else:
        # Video: only "Link" without title/description
        parts.append(f"<a href=\"{url}\">Link</a>")
        
    caption = " | ".join(parts) + "\n" + "Developed by @datapeice"
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
async def cmd_start(message: types.Message):
    display_name, stored_name, handle = resolve_user_identity(message.from_user)
    stats.add_active_user(message.from_user.id)
    
    welcome_text = (
        f"👋 <b>Hello, {display_name}!</b>\n\n"
        "I will help you download video and music from TikTok, YouTube, Instagram, and other services.\n\n"
        "📎 <b>Just send me a link!</b>\n"
        "🔍 Or use me in any chat: <code>@ytttins_dl_bot &lt;link&gt;</code>\n\n"
        "⭐️ <b>Support development:</b> /donate"
    )
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Search Song")],
            [KeyboardButton(text="⭐️ Support")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(welcome_text, reply_markup=kb, parse_mode='HTML')

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
        "We use <b>Telegram Stars</b> — this is the official and safe way to thank the developer.\n\n"
        "💎 Stars can be withdrawn via Fragment to TON, making your contribution extremely valuable!\n\n"
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
    """Thanks the user for donation."""
    payment = message.successful_payment
    amount = payment.total_amount
    
    thanks_text = (
        "💖 <b>Thank you so much for your support!</b>\n\n"
        f"You have successfully donated <b>{amount} ⭐️</b>. "
        "This is incredibly important to us! We will continue improving the bot for you.\n\n"
        "✨ <i>Status updated: Winner in life!</i>"
    )
    
    await message.answer(thanks_text, parse_mode='HTML')

@router.message(Command("song"))
@router.message(lambda m: m.text and (
    m.text.lower().startswith('search ') or 
    m.text.lower().startswith('/song') or
    m.text == "🔍 Search Song"
))
async def handle_search(message: types.Message):
    text_lower = message.text.lower()
    
    if message.text == "🔍 Search Song":
        await message.answer("Please type <code>search </code> followed by the song name.\nExample: <code>search Linkin Park Numb</code>", parse_mode='HTML')
        return

    if text_lower.startswith('search '):
        query = message.text[text_lower.index('search ') + len('search '):].strip()
    elif text_lower.startswith('/song '):
        query = message.text[text_lower.index('/song ') + len('/song '):].strip()
    elif text_lower.startswith('/song'):
        query = message.text[len('/song'):].strip()
    else:
        query = ""

    if not query:
        await message.answer("❌ Please provide a song name.")
        return

    # Start fetching rich metadata in parallel with search/download
    metadata_task = asyncio.create_task(fetch_song_metadata(query))

    reply_kwargs = {}
    if message.chat.type != 'private':
        reply_kwargs['reply_to_message_id'] = message.message_id
        stats.add_active_group(message.chat.id)

    # Whitelist check
    if stats.whitelisted_users and not stats.is_whitelisted(message.from_user.username):
        await message.answer("⛔ Sorry, this bot is private. You are not in the whitelist.", **reply_kwargs)
        return

    is_group = message.chat.type != 'private'

    status_message = None
    async def update_status(text: str):
        pass

    try:
        search_methods = [
            ("yt music", f"ytmusicsearch1:{query}"),
            ("soundcloud", f"scsearch1:{query}"),
            ("youtube", f"ytsearch1:{query} official audio")
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
                await status_message.edit_text("❌ Sorry, something went wrong during download.")

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
            await status_message.edit_text(user_error, parse_mode='Markdown')
        else:
            await message.answer(user_error, parse_mode='Markdown', **reply_kwargs)


@router.message(lambda m: m.text and not m.text.startswith(('/start', '/panel', '/whitelist', '/unwhitelist', 'add @', '/song')) and not m.text.lower().startswith('найти '))
async def handle_url(message: types.Message):
    # Accept any URL-like string
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
    match = re.search(url_pattern, message.text)
    if not match:
        return
        
    target_url = match.group(0)
    
    reply_kwargs = {}
    if message.chat.type != 'private':
        reply_kwargs['reply_to_message_id'] = message.message_id
        stats.add_active_group(message.chat.id)
    
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
        if platform == "unknown":
            if not is_group:
                await message.answer("Sorry, this platform is not supported.", **reply_kwargs)
            return

        if platform == "youtube" and not is_youtube_music(target_url):
            request_id = str(uuid.uuid4())[:8]
            url_cache[request_id] = target_url
            
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"format:audio:{request_id}"),
                InlineKeyboardButton(text="🎥 Video", callback_data=f"format:video:{request_id}")
            )
            await message.answer("Choose download format:", reply_markup=builder.as_markup(), **reply_kwargs)
            return

        is_youtube = platform == "youtube" or 'youtu.be' in target_url or 'youtube.com' in target_url
        if is_group and not is_youtube:
            # Stealth mode for groups (no funny status messages)
            async def update_status(text: str):
                pass
        else:
            status_message = await message.answer("🎬 Starting...", **reply_kwargs)
            async def update_status(text: str):
                try:
                    await status_message.edit_text(text)
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
                    from aiogram.exceptions import TelegramRetryAfter
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
                        **reply_kwargs
                    )
                else:
                    await message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=int(metadata.get('duration', 0)),
                        caption=caption,
                        parse_mode='HTML',
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
                    'parse_mode': 'HTML'
                }
                
                if metadata.get('width') and metadata.get('height'):
                    video_kwargs['width'] = metadata.get('width')
                    video_kwargs['height'] = metadata.get('height')
                
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
                await status_message.edit_text("Sorry, something went wrong during download.")
    
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
            await status_message.edit_text(user_error, parse_mode='Markdown' if '```' in user_error else None)
        else:
            await message.answer(user_error, parse_mode='Markdown' if '```' in user_error else None, **reply_kwargs)

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
            file_path, thumbnail_path, metadata = await download_media(url, is_music, progress_callback=update_status, min_duration=60)

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

            user_id = callback.from_user.id
            if file_path.exists():
                await update_status("📤 Uploading to Telegram...")
                caption = format_caption(metadata, 'youtube', url, is_music=is_music)

                sent = await bot.send_audio(
                    user_id,
                    types.FSInputFile(file_path),
                    thumbnail=types.FSInputFile(thumbnail_path) if thumbnail_path else None,
                    duration=int(metadata.get('duration', 0)),
                    caption=caption,
                    parse_mode='HTML'
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

            user_id = callback.from_user.id
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
                    'parse_mode': 'HTML'
                }
                
                if metadata.get('width') and metadata.get('height'):
                    video_kwargs['width'] = metadata.get('width')
                    video_kwargs['height'] = metadata.get('height')
                
                if thumbnail_path:
                   video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                sent = await bot.send_video(user_id, **video_kwargs)
                
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
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
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

@router.chosen_inline_result()
async def inline_result_chosen(chosen_result: types.ChosenInlineResult, bot: Bot):
    logging.info(f"Chosen inline result: {chosen_result.result_id} with query {chosen_result.query}")
    url = chosen_result.query.strip()
    inline_message_id = chosen_result.inline_message_id
    
    if not inline_message_id:
        logging.warning("No inline_message_id provided. Ensure result has a reply_markup.")
        return

    # Extract clean URL
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    match = re.search(url_pattern, url)
    if not match:
        return
    target_url = match.group(0)
    
    platform = get_platform(target_url)
    
    # YouTube Path: Show selection buttons (match regular bot)
    if platform == "youtube" and not is_youtube_music(target_url):
        request_id = str(uuid.uuid4())[:8]
        url_cache[request_id] = target_url
        
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"format:audio:{request_id}"),
            InlineKeyboardButton(text="🎥 Video", callback_data=f"format:video:{request_id}")
        )
        await bot.edit_message_text(
            text="Choose download format:",
            inline_message_id=inline_message_id,
            reply_markup=builder.as_markup()
        )
        return

    # Other Platforms Path: Start download immediately
    await bot.edit_message_text(
        text="downloading...",
        inline_message_id=inline_message_id
    )
    
    # We call the same internal logic that handle_url uses
    # But since it's an inline message, we'll use a specialized helper or adapt.
    # For now, let's trigger it directly.
    try:
        # Resolve music vs video for autodownload
        is_music = is_youtube_music(target_url) or platform == "soundcloud"
        
        async def update_status(text: str):
            try:
                await bot.edit_message_text(text=text, inline_message_id=inline_message_id)
            except: pass

        file_path, thumbnail_path, metadata = await download_media(target_url, is_music, progress_callback=update_status)
        
        await update_status("📤 uploading...")
        
        display_name, stored_name, handle = resolve_user_identity(chosen_result.from_user)
        stats.add_active_user(chosen_result.from_user.id)
        
        user_id = chosen_result.from_user.id
        caption = format_caption(metadata, platform, target_url, is_music=is_music)

        # Slideshow check
        if isinstance(file_path, list):
             # Slideshows go to PM since we can't edit inline message to media group
             await bot.send_message(user_id, "📤 uploading slideshow to your PM...")
             # ... existing slideshow logic ...
             image_exts = ['.jpg', '.jpeg', '.png', '.webp']
             ordered_files = sorted(file_path, key=lambda p: p.name)
             media_group = [types.InputMediaPhoto(media=types.FSInputFile(p), caption=caption if i == 0 else "", parse_mode='HTML' if i == 0 else None) for i, p in enumerate(ordered_files) if p.suffix.lower() in image_exts][:10]
             if media_group:
                 await bot.send_media_group(user_id, media_group)
             
             for p in file_path:
                 try: p.unlink()
                 except: pass
             await update_status("✅ uploaded to PM!")
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

            # Update the inline message with the media!
            await bot.edit_message_media(media=media, inline_message_id=inline_message_id)
            
            # Delete from PM after sending to inline
            try: await sent.delete()
            except: pass
            
            # Clean up
            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists(): thumbnail_path.unlink()
        else:
            await update_status("❌ Error: Download failed.")

    except Exception as e:
        logging.error(f"Inline chosen download error: {e}")
        try:
             await bot.edit_message_text(text=f"❌ Error: {str(e)[:100]}", inline_message_id=inline_message_id)
        except:
             pass

