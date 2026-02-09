import grpc
import logging
import os
import uuid
import yt_dlp
import asyncio
import random
import aiohttp
import concurrent.futures
from pathlib import Path
from typing import Tuple, Dict, Optional, Callable, Union, List

# Импортируем сгенерированные gRPC файлы
import protos.downloader_pb2 as pb2
import protos.downloader_pb2_grpc as pb2_grpc

from config import DOWNLOADS_DIR, DATA_DIR, COOKIES_CONTENT, HOME_SERVER_ADDRESS, USE_COBALT, COBALT_API_URL, SOCKS_PROXY
from database.storage import stats
from database.models import Cookie
from services.tiktok_scraper import download_tiktok_images

# Import CobaltClient only if USE_COBALT is enabled
if USE_COBALT and COBALT_API_URL:
    try:
        from services.cobalt_client import CobaltClient
        cobalt_client = CobaltClient()
        logging.info(f"✅ Cobalt client initialized: {COBALT_API_URL}")
    except Exception as e:
        logging.error(f"❌ Failed to initialize Cobalt client: {e}")
        cobalt_client = None
else:
    cobalt_client = None
    if not USE_COBALT:
        logging.info("ℹ️ Cobalt disabled (USE_COBALT=false)")
    elif not COBALT_API_URL:
        logging.warning("⚠️ COBALT_API_URL not set")

# === Funny statuses (English) ===
FUNNY_STATUSES = [
    "💻 Hacking the Pentagon...",
    "🛡️ Fending off the FBI...",
    "🍕 Ordering pizza for the server's rats...",
    "🐈 Petting the server cat...",
    "🔥 Warming up the GPU...",
    "👀 Watching the video with the whole server...",
    "🚀 Preparing for takeoff...",
    "🧹 Sweeping up bits...",
    "🤔 Thinking about the meaning of life...",
    "📦 Packing pixels...",
    "📡 Searching for Elon Musk's satellites...",
    "🔌 Plugging the cable in deeper...",
    "☕ Drinking coffee, waiting for download...",
    "🔨 Fixing what isn't broken...",
    "🦖 Running away from dinosaurs...",
    "💿 Wiping the disk with alcohol...",
    "👾 Negotiating with reptilians...",
    "🇵🇱 Searching for Polish alt girls...",
    "🛃 Deporting migrants...",
    "🙏 Praying the server survives...",
    "📜 Signing a contract with Crowley...",
]

# === Работа с Cookies ===
def get_cookies_content() -> str:
    """Получает актуальные cookies из ENV или БД"""
    content = ""
    if COOKIES_CONTENT:
        content = COOKIES_CONTENT
    
    if stats.Session:
        try:
            with stats.Session() as session:
                cookie = session.query(Cookie).order_by(Cookie.updated_at.desc()).first()
                if cookie:
                    content = cookie.content
        except Exception as e:
            logging.error(f"Error loading cookies from DB: {e}")
            
    # Сохраняем локально для yt-dlp (для TikTok)
    if content:
        cookie_path = DATA_DIR / "cookies.txt"
        with open(cookie_path, "w") as f:
            f.write(content)
            
    return content

# Инициализируем куки при старте модуля
get_cookies_content()

# === Вспомогательные функции ===
def get_platform(url: str) -> str:
    """Detect platform from URL."""
    url_lower = url.lower()
    
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "instagram.com" in url_lower:
        return "instagram"
    elif "reddit.com" in url_lower or "redd.it" in url_lower:
        return "reddit"
    elif "twitter.com" in url_lower or "x.com" in url_lower or "t.co" in url_lower:
        return "twitter"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
        return "facebook"
    elif "vimeo.com" in url_lower:
        return "vimeo"
    elif "twitch.tv" in url_lower:
        return "twitch"
    elif "pinterest.com" in url_lower or "pin.it" in url_lower:
        return "pinterest"
    elif "vk.com" in url_lower or "vk.ru" in url_lower:
        return "vk"
    elif "dailymotion.com" in url_lower or "dai.ly" in url_lower:
        return "dailymotion"
    elif "https://" in url_lower or "http://" in url_lower:
        # yt-dlp supports 1800+ sites, try anyway
        return "video"
    else:
        return "unknown"

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

# === Основная логика ===

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    logging.info(f"Using yt-dlp version: {yt_dlp.version.__version__}")
    
    # Resolve short URLs to detect slideshows and help yt-dlp
    if "vm.tiktok.com" in url or "vt.tiktok.com" in url or "/t/" in url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True, timeout=5) as resp:
                    url = str(resp.url)
        except Exception as e:
            logging.warning(f"Failed to resolve TikTok URL: {e}")
    
    # Resolve Reddit short URLs (reddit.com/r/.../s/...) to full URLs
    if "reddit.com" in url and "/s/" in url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True, timeout=5) as resp:
                    url = str(resp.url)
                    logging.info(f"Resolved Reddit URL to: {url}")
        except Exception as e:
            logging.warning(f"Failed to resolve Reddit URL: {e}")

    # Strip query parameters (they often confuse extractors or contain tracking)
    if '?' in url:
        url = url.split('?')[0]
    platform = get_platform(url)
    
    # Показываем смешной статус сразу
    if progress_callback:
        funny_status = random.choice(FUNNY_STATUSES)
        await progress_callback(f"🎬 {funny_status}")
    
    # === МЕТОД 1: YT-DLP (основной) ===
    ytdlp_error = None
    try:
        logging.info(f"[YT-DLP] Attempting download: {url}")
        
        # TikTok через специальный метод
        if platform == "tiktok":
            return await _download_local_tiktok(url)
        
        # YouTube/Instagram/музыка через универсальный метод
        return await _download_local_ytdlp(url, is_music)
        
    except Exception as e:
        ytdlp_error = str(e)
        logging.warning(f"[YT-DLP] ❌ Failed: {ytdlp_error}")
    
    # === МЕТОД 1.5: YT-DLP С ПРОКСИ (fallback если есть прокси) ===
    if SOCKS_PROXY and ytdlp_error:
        try:
            logging.info(f"[YT-DLP+PROXY] Attempting with SOCKS proxy")
            
            # TikTok через специальный метод с прокси
            if platform == "tiktok":
                return await _download_local_tiktok(url, use_proxy=True)
            
            # YouTube/Instagram/музыка с прокси
            return await _download_local_ytdlp(url, is_music, use_proxy=True)
            
        except Exception as proxy_error:
            logging.warning(f"[YT-DLP+PROXY] ❌ Failed: {proxy_error}")
            pass  # Silent fallback to Cobalt
    
    # === МЕТОД 2: COBALT API (fallback) ===
    if cobalt_client:
        try:
            logging.info(f"[COBALT] Attempting download: {url}")
            file_path, thumb_path, metadata = await cobalt_client.download_media(
                url=url,
                quality="1080",
                is_audio=is_music,
                progress_callback=progress_callback
            )
            if file_path and file_path.exists():
                logging.info(f"[COBALT] ✅ Success: {file_path.name}")
                return file_path, thumb_path, metadata
            else:
                logging.warning("[COBALT] ⚠️ No file returned")
        except Exception as cobalt_error:
            logging.error(f"[COBALT] ❌ Error: {cobalt_error}")
    
    # === МЕТОД 3: TIKWM (только для TikTok) ===
    if platform == "tiktok":
        try:
            if progress_callback:
                await progress_callback("📥 Trying TikWM API...")
            
            logging.info("[TIKWM] Attempting download...")
            return await _download_tiktok_tikwm(url)
        except Exception as tikwm_error:
            logging.error(f"[TIKWM] ❌ Failed: {tikwm_error}")
    
    # Все методы провалились
    raise Exception(f"All download methods failed. YT-DLP error: {ytdlp_error}")


async def _download_local_ytdlp(url: str, is_music: bool = False, use_proxy: bool = False) -> Tuple[Path, Optional[Path], Dict]:
    """Универсальный метод для YouTube/Instagram/музыки через yt-dlp"""
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOADS_DIR / f"%(title)s_%(id)s_{unique_id}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"
    
    ydl_opts = {
        'outtmpl': output_template,
        'cookiefile': cookie_file if cookie_file.exists() else None,
        'noplaylist': True,
        'quiet': False,
        'verbose': True,
    }
    
    # Reddit-specific configuration to avoid blocks
    if "reddit.com" in url or "redd.it" in url:
        ydl_opts['extractor_args'] = {
            'reddit': {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
            }
        }
    
    # Добавляем прокси, если запрошено и настроено
    if use_proxy and SOCKS_PROXY:
        ydl_opts['proxy'] = SOCKS_PROXY
    
    if is_music:
        # Только аудио
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }]
    else:
        # Видео с H.264 кодеком
        ydl_opts['format'] = 'best[vcodec^=h264]/best[vcodec^=avc]/best'
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        metadata = {
            'title': info.get('title', 'Media'),
            'uploader': info.get('uploader', 'Unknown'),
            'webpage_url': info.get('webpage_url', url),
            'duration': info.get('duration', 0),
            'width': info.get('width', 0),
            'height': info.get('height', 0),
        }
        
        # Находим скачанный файл
        downloaded_files = list(DOWNLOADS_DIR.glob(f"*{unique_id}*"))
        
        if not downloaded_files:
            path = Path(ydl.prepare_filename(info))
            if path.exists():
                downloaded_files = [path]
            else:
                raise ValueError("Download failed: file not found")
        
        file_path = downloaded_files[0]
        logging.info(f"Downloaded: {file_path.name}")
        
        return file_path, None, metadata


async def _download_local_tiktok(url: str, use_proxy: bool = False) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    """Скачивание TikTok на VPS. Поддерживает видео (h264) и фото-слайдшоу."""
    
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOADS_DIR / f"%(title)s_%(id)s_{unique_id}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"
    
    # Check for slideshow (images)
    is_slideshow = "/photo/" in url
    
    ydl_opts_base = {
        'outtmpl': output_template,
        'cookiefile': cookie_file if cookie_file.exists() else None,
        'noplaylist': True,
        'quiet': False, # Enable logging to see what's wrong
        'verbose': True,
        # Remove hardcoded User-Agent to avoid conflicts with cookies or triggering anti-bot
        # 'http_headers': { ... } 
    }
    
    # Добавляем прокси, если запрошено и настроено
    if use_proxy and SOCKS_PROXY:
        ydl_opts_base['proxy'] = SOCKS_PROXY
    
    if is_slideshow:
        # Try custom scraper first for photos (as yt-dlp might fail or be slow)
        try:
             logging.info("Attempting to download slideshow with custom scraper...")
             loop = asyncio.get_event_loop()
             # Run sync scraper in executor
             files, meta = await loop.run_in_executor(None, download_tiktok_images, url, DOWNLOADS_DIR)
             return files, None, meta
        except Exception as e:
             logging.error(f"Custom scraper failed: {e}. Falling back to yt-dlp...")
             ydl_opts = ydl_opts_base.copy()
    else:
        # Strict legacy codec check for videos
        ydl_opts = ydl_opts_base.copy()
        ydl_opts['format'] = 'best[vcodec^=h264]/best[vcodec^=avc]'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        metadata = {
            'title': info.get('title', 'TikTok Media'),
            'uploader': info.get('uploader', 'Unknown'),
            'webpage_url': info.get('webpage_url', url),
            'duration': info.get('duration', 0),
            'width': info.get('width', 0),
            'height': info.get('height', 0),
        }
        
        # Determine downloaded files
        # We search by unique_id to catch all files (images, mp3, mp4)
        downloaded_files = list(DOWNLOADS_DIR.glob(f"*{unique_id}*"))
        
        if not downloaded_files:
            # Fallback to prepare_filename
            path = Path(ydl.prepare_filename(info))
            if path.exists():
                downloaded_files = [path]
            else:
                 raise ValueError("Download failed: file not found")

        if is_slideshow:
            return downloaded_files, None, metadata
        
        # Video handling - проверяем кодек, только H264 разрешён для yt-dlp
        video_files = [f for f in downloaded_files if f.suffix in ['.mp4', '.mov']]
        if video_files:
            path = video_files[0]
            vcodec = info.get('vcodec', 'unknown')
            if vcodec: vcodec = vcodec.lower()
            
            # Только H264/AVC допустимы для локального yt-dlp
            is_h264 = 'avc' in vcodec or 'h264' in vcodec
            if not is_h264 and 'unknown' not in vcodec:
                # Удаляем файл и бросаем исключение для fallback на tikwm
                for f in downloaded_files:
                    if f.exists(): f.unlink()
                raise ValueError(f"Codec {vcodec} not H264, trying tikwm fallback")
            
            return path, None, metadata
            
        return downloaded_files[0], None, metadata


async def _download_remote_grpc(url: str, is_music: bool, video_height: int, progress_callback: Optional[Callable] = None) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    """Отправляет задачу на домашний сервер"""
    
    async with grpc.aio.insecure_channel(HOME_SERVER_ADDRESS) as channel:
        stub = pb2_grpc.DownloaderServiceStub(channel)
        
        cookies = get_cookies_content()
        
        request = pb2.DownloadRequest(
            url=url,
            is_music=is_music,
            video_height=video_height or 0,
            cookies_content=cookies
        )
        
        temp_id = uuid.uuid4().hex
        ext = 'mp3' if is_music else 'mp4'
        temp_media = DOWNLOADS_DIR / f"temp_{temp_id}.{ext}"
        temp_thumb = DOWNLOADS_DIR / f"temp_{temp_id}.jpg"
        
        metadata = {}
        final_path = None
        thumbnail_path = None
        
        media_file = None
        thumb_file = None
        has_thumb = False
        
        # --- ЗАПУСК ФОНОВОЙ ЗАДАЧИ С ШУТКАМИ ---
        status_task = None
        if progress_callback:
            async def funny_status_loop():
                try:
                    while True:
                        msg = random.choice(FUNNY_STATUSES)
                        try:
                            # Обновленный формат сообщения
                            await progress_callback(f"Downloading... It can take more time\n\n⏳ {msg}")
                        except Exception:
                            pass 
                        await asyncio.sleep(3)
                except asyncio.CancelledError:
                    pass

            status_task = asyncio.create_task(funny_status_loop())

        try:
            media_file = open(temp_media, 'wb')
            thumb_file = open(temp_thumb, 'wb')
            
            async for response in stub.DownloadMedia(request):
                if response.HasField('metadata'):
                    meta = response.metadata
                    metadata = {
                        'title': meta.title,
                        'uploader': meta.uploader,
                        'webpage_url': meta.webpage_url,
                        'duration': meta.duration,
                        'width': meta.width,
                        'height': meta.height,
                    }
                    clean_name = "".join(x for x in meta.filename if x.isalnum() or x in "._- ")
                    final_path = DOWNLOADS_DIR / clean_name
                    
                elif response.HasField('thumbnail_chunk'):
                    thumb_file.write(response.thumbnail_chunk)
                    has_thumb = True
                    
                elif response.HasField('file_chunk'):
                    media_file.write(response.file_chunk)
            
            media_file.close()
            thumb_file.close()
            
            if final_path:
                if final_path.exists(): final_path.unlink()
                temp_media.rename(final_path)
            else:
                final_path = temp_media
                
            if has_thumb:
                thumbnail_path = final_path.with_suffix('.jpg')
                if thumbnail_path.exists(): thumbnail_path.unlink()
                temp_thumb.rename(thumbnail_path)
            else:
                temp_thumb.unlink(missing_ok=True)
                
            return final_path, thumbnail_path, metadata

        except Exception as e:
            if media_file and not media_file.closed: media_file.close()
            if thumb_file and not thumb_file.closed: thumb_file.close()
            if temp_media.exists(): temp_media.unlink()
            if temp_thumb.exists(): temp_thumb.unlink()
            raise e
        finally:
            if status_task:
                status_task.cancel()

async def _download_tiktok_tikwm(url: str) -> Tuple[Path, Optional[Path], Dict]:
    """Fallback: download TikTok video using tikwm.com API when yt-dlp fails"""
    import requests
    import subprocess
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    api_url = 'https://www.tikwm.com/api/'
    params = {'url': url, 'hd': 1}
    
    response = requests.get(api_url, params=params, headers=headers, timeout=15)
    
    if response.status_code != 200:
        raise Exception(f"tikwm API returned status {response.status_code}")
    
    data = response.json()
    
    if data.get('code') != 0:
        raise Exception(f"tikwm API error: {data.get('msg', 'Unknown error')}")
    
    result = data.get('data', {})
    
    # Get video URL (prefer HD, but tikwm may not have h264)
    video_url = result.get('hdplay') or result.get('play')
    
    if not video_url:
        raise Exception("No video URL found in tikwm response")
    
    # Get thumbnail URL
    thumbnail_url = result.get('origin_cover') or result.get('cover')
    
    # Extract metadata
    author = result.get('author', {}).get('unique_id', 'Unknown')
    title = result.get('title', 'TikTok Video')
    duration = result.get('duration', 0)
    
    logging.info(f"tikwm: Downloading video from {video_url[:80]}...")
    
    # Download video
    unique_id = uuid.uuid4().hex[:8]
    video_path = DOWNLOADS_DIR / f"tiktok_{unique_id}.mp4"
    
    video_response = requests.get(video_url, headers={'User-Agent': headers['User-Agent']}, stream=True, timeout=30)
    
    if video_response.status_code != 200:
        raise Exception(f"Failed to download video: status {video_response.status_code}")
    
    with open(video_path, 'wb') as f:
        for chunk in video_response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    logging.info(f"tikwm: Video downloaded successfully to {video_path}")
    
    # Download thumbnail if available
    thumbnail_path = None
    if thumbnail_url:
        try:
            thumbnail_path = DOWNLOADS_DIR / f"tiktok_{unique_id}.jpg"
            thumb_response = requests.get(thumbnail_url, headers={'User-Agent': headers['User-Agent']}, timeout=10)
            
            if thumb_response.status_code == 200:
                with open(thumbnail_path, 'wb') as f:
                    f.write(thumb_response.content)
                logging.info(f"tikwm: Thumbnail downloaded to {thumbnail_path}")
            else:
                thumbnail_path = None
        except Exception as e:
            logging.warning(f"tikwm: Failed to download thumbnail: {e}")
            thumbnail_path = None
    
    # Не проверяем кодек - принимаем любой формат (H264 или HEVC)
    # Если Telegram не поддержит HEVC, пользователь увидит ошибку и попробует снова
    
    metadata = {
        'title': title,
        'uploader': author,
        'webpage_url': url,
        'duration': duration,
        'ext': 'mp4'
    }
    
    return video_path, thumbnail_path, metadata

# --- ФУНКЦИИ ДЛЯ АДМИНКИ (ВЕРСИИ) ---

async def get_worker_version() -> str:
    """Запрашивает версию yt-dlp у воркера"""
    try:
        async with grpc.aio.insecure_channel(HOME_SERVER_ADDRESS) as channel:
            stub = pb2_grpc.DownloaderServiceStub(channel)
            response = await stub.GetVersion(pb2.Empty(), timeout=2)
            return response.version
    except Exception as e:
        return "Offline 🔴"

async def update_worker_ytdlp() -> str:
    """Отправляет команду обновления воркеру"""
    try:
        async with grpc.aio.insecure_channel(HOME_SERVER_ADDRESS) as channel:
            stub = pb2_grpc.DownloaderServiceStub(channel)
            response = await stub.UpdateYtdlp(pb2.Empty(), timeout=60)
            if response.success:
                return f"✅ Worker updated to {response.new_version}"
            else:
                return f"❌ Worker update failed: {response.message}"
    except Exception as e:
        return f"❌ Worker connection failed: {str(e)}"