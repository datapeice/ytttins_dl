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
from aiogram.types import InlineKeyboardButton
from services.downloader import download_media, get_platform, is_youtube_music
from database.storage import stats
from services.logger import download_logger
from config import DOWNLOADS_DIR
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
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
    uploader = metadata.get('uploader', 'Unknown')
    url = original_url or metadata.get('webpage_url', '')
    
    # Check for verified status in metadata
    is_verified = metadata.get('verified') or metadata.get('creator_is_verified') or metadata.get('uploader_is_verified') or metadata.get('channel_is_verified')
    
    # Strip leading @
    uploader = uploader.lstrip('@')
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
    await message.answer(
        "Hello! Send me a link to download video from:\n"
        "- YouTube / YouTube Music 🎵\n"
        "- TikTok\n"
        "- Instagram\n"
        "- Twitter/X\n"
        "- Reddit\n"
        "- Facebook\n"
        "- Vimeo\n"
        "- Twitch\n"
        "- Pinterest\n"
        "- VK / Dailymotion\n"
        "- And 1800+ other sites!\n\n"
        "🔍 <b>Song search:</b> Start your message with <code>найти</code> followed by the song name to search and download it as MP3.\n"
        "Example: <code>найти Smells Like Teen Spirit</code>\n\n"
        "Developed by @datapeice",
        parse_mode='HTML'
    )

@router.message(Command("song"))
@router.message(lambda m: m.text and (m.text.lower().startswith('найти ') or m.text.lower().startswith('/song')))
async def handle_search(message: types.Message):
    text_lower = message.text.lower()
    if text_lower.startswith('найти '):
        query = message.text[text_lower.index('найти ') + len('найти '):].strip()
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

    if is_group:
        status_message = None
        async def update_status(text: str):
            pass
    else:
        status_message = await message.answer(f"🔍 Searching for: {query}...", **reply_kwargs)
        async def update_status(text: str):
            try:
                await status_message.edit_text(text)
            except Exception:
                pass

    try:
        search_methods = [
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

        # Stealth mode: in groups, skip status messages and use a no-op callback
        if is_group:
            status_message = None
            async def update_status(text: str):
                pass
        else:
            status_message = await message.answer("⏳ Starting...", **reply_kwargs)
            async def update_status(text: str):
                try:
                    await status_message.edit_text(text)
                except Exception:
                    pass

        is_music = is_youtube_music(target_url)
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
async def handle_format_selection(callback: types.CallbackQuery):
    try:
        await callback.answer()
        _, format_type, request_id = callback.data.split(":", 2)
        
        url = url_cache.get(request_id)
        if not url:
            await callback.message.edit_text("⚠️ Request expired. Please send the link again.")
            return

        if format_type == "video":
            builder = InlineKeyboardBuilder()
            resolutions = [("1080p", 1080), ("720p", 720), ("480p", 480), ("360p", 360)]

            for label, height in resolutions:
                builder.add(InlineKeyboardButton(
                    text=label,
                    callback_data=f"dl_res:{request_id}:{height}"
                ))
            builder.adjust(2)
            
            await callback.message.edit_text("Select video quality:", reply_markup=builder.as_markup())
            return

        status_message = await callback.message.edit_text("⏳ Starting...")
        
        async def update_status(text: str):
            try:
                await status_message.edit_text(text)
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
                title=file_path.stem
            )

            user_id = callback.from_user.id
            download_logger.info(
                f"User: {display_name} ({handle}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: Audio | "
                f"URL: {url}"
            )

            if file_path.exists():
                await update_status("📤 Uploading to Telegram...")
                
                caption = format_caption(metadata, 'youtube', url, is_music=is_music)

                if thumbnail_path:
                    await callback.message.answer_audio(
                        types.FSInputFile(file_path), 
                        thumbnail=types.FSInputFile(thumbnail_path),
                        duration=int(metadata.get('duration', 0)),
                        caption=caption,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=int(metadata.get('duration', 0)),
                        caption=caption,
                        parse_mode='HTML'
                    )
                
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                await status_message.delete()
            else:
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
            
            if "No working app info" in error_msg or "tiktok:sound" in error_msg:
                user_error = "❌ TikTok sound/music links are not supported. Please send a video link."
            elif "Unsupported URL" in error_msg:
                user_error = "❌ This URL is not supported."
            else:
                user_error = (
                    f"```error\n{error_msg}\n```\n\n"
                    f"Contact with developer @datapeice"
                )
            
            await status_message.edit_text(user_error, parse_mode='Markdown' if '```' in user_error else None)

    except Exception as e:
        logging.error(f"Error in callback handling: {str(e)}")
        try:
            await callback.message.answer("❌ Sorry, this request has expired. Please try again.")
        except Exception:
            pass

@router.callback_query(F.data.startswith("dl_res:"))
async def handle_resolution_selection(callback: types.CallbackQuery):
    try:
        await callback.answer()
        _, request_id, height = callback.data.split(":", 2)
        
        url = url_cache.get(request_id)
        if not url:
            await callback.message.edit_text("⚠️ Request expired. Please send the link again.")
            return

        status_message = await callback.message.edit_text(f"⏳ Downloading video ({height}p)...")
        
        async def update_status(text: str):
            try:
                await status_message.edit_text(text)
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
                title=file_path.stem
            )

            user_id = callback.from_user.id
            download_logger.info(
                f"User: {display_name} ({handle}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: Video ({height}p) | "
                f"URL: {url}"
            )

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
                
                logging.info(f"Sending video with kwargs: {video_kwargs}")
                
                # Measure upload time to Telegram
                upload_start = time.time()
                await callback.message.answer_video(**video_kwargs)
                upload_time = time.time() - upload_start
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                logging.info(f"✅ Video uploaded to Telegram in {upload_time:.1f}s ({file_size_mb:.2f}MB, {file_size_mb/upload_time:.2f}MB/s)")
                
                file_path.unlink()
                if thumbnail_path and thumbnail_path.exists():
                    thumbnail_path.unlink()
                await status_message.delete()
            else:
                await status_message.edit_text("Sorry, something went wrong during download.")

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error in video download: {error_msg}")
            
            if "No working app info" in error_msg or "tiktok:sound" in error_msg:
                user_error = "❌ TikTok sound/music links are not supported. Please send a video link."
            elif "Unsupported URL" in error_msg:
                user_error = "❌ This URL is not supported."
            else:
                user_error = (
                    f"```error\n{error_msg}\n```\n\n"
                    f"Contact with developer @datapeice"
                )
            
            await status_message.edit_text(user_error, parse_mode='Markdown' if '```' in user_error else None)

    except Exception as e:
        logging.error(f"Error in resolution callback: {str(e)}")

@router.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    text = inline_query.query.strip()
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
    match = re.search(url_pattern, text)
    if not match:
        return
        
    url = match.group(0)
    
    article_result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title="📥 Скачать медиа / Download media",
        description=f"Нажмите, чтобы отправить ссылку (фоновая загрузка)",
        input_message_content=InputTextMessageContent(
            message_text=url
        )
    )
    try:
        from yt_dlp import YoutubeDL
        import asyncio
        import random
        
        def get_yt_dlp_url():
            opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'format': 'best',
                'http_headers': {
                    'User-Agent': random.choice([
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0'
                    ])
                }
            }
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.wait_for(asyncio.to_thread(get_yt_dlp_url), timeout=5.0)
        
        if info and info.get('url'):
            direct_url = info['url']
            thumb = info.get('thumbnail', direct_url)
            title = info.get('title', 'Video')
            
            video_result = types.InlineQueryResultVideo(
                id=str(uuid.uuid4()),
                title=f"🎬 Отправить {title}",
                video_url=direct_url,
                mime_type="video/mp4",
                thumbnail_url=thumb,
                description="Прямая отправка видео"
            )
            await inline_query.answer([video_result, article_result], cache_time=1, is_personal=False)
            return

    except Exception as e:
        logging.warning(f"Inline yt_dlp extraction failed: {e}")

    await inline_query.answer([article_result], cache_time=1, is_personal=False)

@router.chosen_inline_result()
async def inline_result_chosen(chosen_result: types.ChosenInlineResult, bot: Bot):
    logging.warning(f"GOT CHOSEN INLINE: {chosen_result.query} from {chosen_result.from_user.id}")
    url = chosen_result.query.strip()
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
    match = re.search(url_pattern, url)
    if not match:
        logging.warning("Chosen inline URL did not match regex")
        return
        
    target_url = match.group(0)
    user_id = chosen_result.from_user.id
    
    try:
        # Send a status message privately
        status_msg = await bot.send_message(user_id, f"📥 Загружаю видео по вашей inline-ссылке...\n{target_url}")
        
        async def update_status(text: str):
            try:
                await status_msg.edit_text(text)
            except:
                pass

        is_music = is_youtube_music(target_url)
        file_path, thumbnail_path, metadata = await download_media(target_url, is_music, progress_callback=update_status)
        
        platform = get_platform(target_url)
        caption = format_caption(metadata, platform, target_url)
        
        if file_path and file_path.exists():
            await update_status("📤 Отправляю готовое видео...")
            
            # Send the actual video
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
                 
            await bot.send_video(user_id, **video_kwargs)
            
            # Cleanup
            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists(): thumbnail_path.unlink()
            await status_msg.delete()
        else:
            await update_status("❌ Ошибка: Файл не скачался.")
    except Exception as e:
        logging.error(f"Chosen inline result download error: {e}")
        try:
            await bot.send_message(user_id, f"❌ Ошибка скачивания: {e}")
        except:
            pass

