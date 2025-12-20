import uuid
import re
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from services.downloader import download_media, get_platform, is_youtube_music
from database.storage import stats
from services.logger import download_logger

router = Router()
url_cache = {}

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Hello! Send me a link to download video from:\n"
        "- YouTube\n"
        "- YouTube Music (will download as MP3)\n"
        "- TikTok\n"
        "- Instagram\n"
        "Developed by @datapeice"
    )

@router.message(lambda m: m.text and not m.text.startswith(('/start', '/panel', '/whitelist', '/unwhitelist', 'add @')))
async def handle_url(message: types.Message):
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+|youtube\.com|youtu\.be|tiktok\.com|instagram\.com'
    
    if not re.search(url_pattern, message.text):
        await message.answer("Please send a valid URL from YouTube, TikTok, or Instagram.")
        return

    # Whitelist check
    if stats.whitelisted_users and not stats.is_whitelisted(message.from_user.username):
        await message.answer("⛔ Sorry, this bot is private. You are not in the whitelist.")
        return

    try:
        platform = get_platform(message.text)
        if platform == "unknown":
            await message.answer("Sorry, this platform is not supported.")
            return

        if platform == "youtube" and not is_youtube_music(message.text):
            request_id = str(uuid.uuid4())[:8]
            url_cache[request_id] = message.text
            
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

        stats.add_active_user(message.from_user.id)
        stats.add_download(
            content_type='Music' if is_music else 'Video',
            user_id=message.from_user.id,
            username=message.from_user.username or "No username",
            platform=platform,
            url=message.text,
            title=file_path.stem
        )

        user_fullname = message.from_user.full_name
        username = message.from_user.username or "No username"
        user_id = message.from_user.id
        download_logger.info(
            f"User: {user_fullname} (@{username}, ID: {user_id}) | "
            f"Platform: {platform} | "
            f"Type: {'Music' if is_music else 'Video'} | "
            f"URL: {message.text}"
        )

        if file_path.exists():
            await status_message.edit_text("Uploading to Telegram... 📤")
            
            caption = (
                f"🎬 {metadata.get('title')}\n"
                f"👤 {metadata.get('uploader')}\n"
                f"🔗 {metadata.get('webpage_url')}"
            )

            if is_music:
                if thumbnail_path:
                    await message.answer_audio(
                        types.FSInputFile(file_path), 
                        thumbnail=types.FSInputFile(thumbnail_path),
                        duration=metadata.get('duration'),
                        caption=caption
                    )
                else:
                    await message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=metadata.get('duration'),
                        caption=caption
                    )
            else:
                video_kwargs = {
                    'video': types.FSInputFile(file_path),
                    'duration': metadata.get('duration'),
                    'supports_streaming': True,
                    'caption': caption
                }
                
                # if metadata.get('width') and metadata.get('height'):
                #     video_kwargs['width'] = metadata.get('width')
                #     video_kwargs['height'] = metadata.get('height')
                
                # if thumbnail_path:
                #    video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                logging.info(f"Sending video with kwargs: {video_kwargs}")
                await message.answer_video(**video_kwargs)
            
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

        status_message = await callback.message.edit_text("Processing your request... ⏳")
        
        try:
            is_music = True
            file_path, thumbnail_path, metadata = await download_media(url, is_music)

            stats.add_active_user(callback.from_user.id)
            stats.add_download(
                content_type='Music',
                user_id=callback.from_user.id,
                username=callback.from_user.username or "No username",
                platform='youtube',
                url=url,
                title=file_path.stem
            )

            user_fullname = callback.from_user.full_name
            username = callback.from_user.username or "No username"
            user_id = callback.from_user.id
            download_logger.info(
                f"User: {user_fullname} (@{username}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: Audio | "
                f"URL: {url}"
            )

            if file_path.exists():
                await status_message.edit_text("Uploading to Telegram... 📤")
                
                caption = (
                    f"🎬 {metadata.get('title')}\n"
                    f"👤 {metadata.get('uploader')}\n"
                    f"🔗 {metadata.get('webpage_url')}"
                )

                if thumbnail_path:
                    await callback.message.answer_audio(
                        types.FSInputFile(file_path), 
                        thumbnail=types.FSInputFile(thumbnail_path),
                        duration=metadata.get('duration'),
                        caption=caption
                    )
                else:
                    await callback.message.answer_audio(
                        types.FSInputFile(file_path),
                        duration=metadata.get('duration'),
                        caption=caption
                    )
                
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

@router.callback_query(F.data.startswith("dl_res:"))
async def handle_resolution_selection(callback: types.CallbackQuery):
    try:
        await callback.answer()
        _, request_id, height = callback.data.split(":", 2)
        
        url = url_cache.get(request_id)
        if not url:
            await callback.message.edit_text("⚠️ Request expired. Please send the link again.")
            return

        status_message = await callback.message.edit_text(f"Downloading video ({height}p)... ⏳")
        
        try:
            file_path, thumbnail_path, metadata = await download_media(url, is_music=False, video_height=int(height))

            stats.add_active_user(callback.from_user.id)
            stats.add_download(
                content_type='Video',
                user_id=callback.from_user.id,
                username=callback.from_user.username or "No username",
                platform='youtube',
                url=url,
                title=file_path.stem
            )

            user_fullname = callback.from_user.full_name
            username = callback.from_user.username or "No username"
            user_id = callback.from_user.id
            download_logger.info(
                f"User: {user_fullname} (@{username}, ID: {user_id}) | "
                f"Platform: youtube | "
                f"Type: Video ({height}p) | "
                f"URL: {url}"
            )

            if file_path.exists():
                await status_message.edit_text("Uploading to Telegram... 📤")
                
                caption = (
                    f"🎬 {metadata.get('title')}\n"
                    f"👤 {metadata.get('uploader')}\n"
                    f"🔗 {metadata.get('webpage_url')}"
                )

                video_kwargs = {
                    'video': types.FSInputFile(file_path),
                    'duration': metadata.get('duration'),
                    'supports_streaming': True,
                    'caption': caption
                }
                
                # if metadata.get('width') and metadata.get('height'):
                #     video_kwargs['width'] = metadata.get('width')
                #     video_kwargs['height'] = metadata.get('height')
                
                # if thumbnail_path:
                #    video_kwargs['thumbnail'] = types.FSInputFile(thumbnail_path)
                
                logging.info(f"Sending video with kwargs: {video_kwargs}")
                await callback.message.answer_video(**video_kwargs)
                
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
