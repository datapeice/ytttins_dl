import grpc
import logging
import os
import uuid
import yt_dlp
from pathlib import Path
from typing import Tuple, Dict, Optional, Callable

# Импортируем сгенерированные gRPC файлы
import protos.downloader_pb2 as pb2
import protos.downloader_pb2_grpc as pb2_grpc

from config import DOWNLOADS_DIR, DATA_DIR, COOKIES_CONTENT, HOME_SERVER_ADDRESS
from database.storage import stats
from database.models import Cookie

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
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    else:
        return "unknown"

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

# === Основная логика ===

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None) -> Tuple[Path, Optional[Path], Dict]:
    platform = get_platform(url)
    
    # 1. Музыка -> Домашний сервер
    if is_music:
        if progress_callback: await progress_callback("Downloading... it can take more time...")
        return await _download_remote_grpc(url, is_music, video_height)

    # 2. TikTok -> Локально на VPS
    if platform == "tiktok":
        try:
            # Используем стандартное сообщение, как было раньше
            if progress_callback: await progress_callback("⏳ Starting...") 
            return await _download_local_tiktok(url)
        except Exception as e:
            logging.warning(f"Local TikTok failed ({e}), switching to Home Server...")
            # Если не вышло, пробуем через дом
            if progress_callback: await progress_callback("Downloading... it can take more time...")
            # Fallback к remote download

    # 3. YouTube/Instagram/Fallback -> Домашний сервер
    if progress_callback: await progress_callback("Downloading... it can take more time...")
    return await _download_remote_grpc(url, is_music, video_height)


async def _download_local_tiktok(url: str) -> Tuple[Path, Optional[Path], Dict]:
    """Скачивает TikTok локально. Если кодек не h264, выбрасывает исключение."""
    
    output_template = str(DOWNLOADS_DIR / f"%(title)s_%(id)s_{uuid.uuid4().hex[:4]}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"
    
    ydl_opts = {
        'format': 'best[vcodec^=h264]/best[vcodec^=avc]/best', 
        'outtmpl': output_template,
        'cookiefile': cookie_file if cookie_file.exists() else None,
        'noplaylist': True,
        'quiet': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        vcodec = info.get('vcodec', 'unknown').lower()
        path = Path(ydl.prepare_filename(info))
        
        # Проверка кодека: если не AVC/H264, то VPS не сможет его обработать (нет ffmpeg)
        if 'avc' not in vcodec and 'h264' not in vcodec and 'none' not in vcodec:
            if path.exists():
                path.unlink()
            raise ValueError(f"Codec {vcodec} is not supported locally (requires conversion)")
            
        metadata = {
            'title': info.get('title', 'TikTok Video'),
            'uploader': info.get('uploader', 'Unknown'),
            'webpage_url': info.get('webpage_url', url),
            'duration': info.get('duration', 0),
            'width': info.get('width', 0),
            'height': info.get('height', 0),
        }
        
        return path, None, metadata


async def _download_remote_grpc(url: str, is_music: bool, video_height: int) -> Tuple[Path, Optional[Path], Dict]:
    """Отправляет задачу на домашний сервер"""
    
    # Используем переменную из конфига, где должен быть прописан IP и порт 50057
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