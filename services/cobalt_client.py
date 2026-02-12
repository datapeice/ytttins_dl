import logging
import aiohttp
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Callable
from config import COBALT_API_URL, COBALT_API_KEY, HTTP_PROXY, HTTPS_PROXY, DOWNLOADS_DIR


class CobaltClient:
    """
    Клиент для работы с Cobalt API.
    Прокси настраивается только для запросов к Cobalt, не влияет на бота.
    """
    
    def __init__(self):
        self.api_url = COBALT_API_URL.rstrip('/')
        self.api_key = COBALT_API_KEY
        self.proxy = None  # Прокси не используется - Cobalt воркер сам обращается к сайтам
        
        logging.info(f"Cobalt client: using external API at {self.api_url}")
    
    def _mask_proxy(self, proxy_url: str) -> str:
        """Маскирует credentials в proxy URL для логирования"""
        try:
            if '@' in proxy_url:
                protocol, rest = proxy_url.split('://', 1)
                credentials, host = rest.split('@', 1)
                return f"{protocol}://***:***@{host}"
            return proxy_url
        except:
            return "***"
    
    async def _make_request(self, url: str, method: str = "GET", json_data: Dict = None) -> Dict:
        """
        Выполняет HTTP запрос к Cobalt API через прокси (если настроен).
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        if self.api_key:
            headers["Authorization"] = f"Api-Key {self.api_key}"
        
        # Создаем connector с поддержкой прокси
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=300)  # 5 минут для больших файлов
        
        try:
            async with aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout
            ) as session:
                if method == "POST":
                    async with session.post(
                        url, 
                        json=json_data, 
                        headers=headers,
                        proxy=self.proxy  # Прокси только для Cobalt запросов
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            logging.error(f"Cobalt API error {response.status}: {error_text}")
                            raise Exception(f"Cobalt API returned {response.status}: {error_text}")
                else:
                    async with session.get(
                        url, 
                        headers=headers,
                        proxy=self.proxy
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            logging.error(f"Cobalt API error {response.status}: {error_text}")
                            raise Exception(f"Cobalt API returned {response.status}")
        except Exception as e:
            logging.error(f"Request to Cobalt failed: {str(e)}")
            raise
    
    async def download_media(
        self, 
        url: str, 
        quality: str = "1080",
        is_audio: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[Optional[Path], Optional[Path], Dict]:
        """
        Загружает медиа через Cobalt API.
        
        Args:
            url: URL видео/аудио
            quality: Качество видео (max, 2160, 1440, 1080, 720, 480, 360, 240, 144)
            is_audio: True если нужно скачать только аудио
            progress_callback: Callback для обновления прогресса
        
        Returns:
            (file_path, thumbnail_path, metadata)
        """
        logging.info(f"Cobalt: downloading {url} (quality={quality}, audio={is_audio})")
        
        request_data = {
            "url": url,
            "videoQuality": quality,
            "youtubeVideoCodec": "h264",  # Всегда запрашиваем H.264 для Telegram
            "downloadMode": "audio" if is_audio else "auto",
            "alwaysProxy": False  # Получаем прямые ссылки, не туннель
        }
        
        if is_audio:
            request_data["audioFormat"] = "mp3"
            request_data["audioBitrate"] = "320"
        
        try:
            response = await self._make_request(
                f"{self.api_url}/",
                method="POST",
                json_data=request_data
            )
            
            status = response.get("status")
            logging.info(f"Cobalt response status: {status}")
            
            if status == "error":
                error_code = response.get("error", {}).get("code", "unknown")
                error_msg = response.get("error", {}).get("context", "Unknown error")
                logging.error(f"Cobalt error: {error_code} - {error_msg}")
                raise Exception(f"Cobalt error: {error_msg}")
            
            elif status == "redirect":
                # Прямая ссылка на файл
                file_url = response.get("url")
                return await self._download_file(file_url, response, progress_callback)
            
            elif status == "tunnel":
                # Cobalt проксирует файл через /tunnel
                tunnel_url = response.get("url")
                return await self._download_file(tunnel_url, response, progress_callback)
            
            elif status == "picker":
                # Множественные файлы (например, TikTok слайдшоу)
                return await self._handle_picker(response)
            
            elif status == "local-processing":
                # Требуется локальная обработка (merge audio+video)
                logging.warning("Cobalt returned local-processing, needs manual FFmpeg merge")
                raise Exception("Local processing not implemented yet, use fallback")
            
            else:
                raise Exception(f"Unknown Cobalt status: {status}")
        
        except Exception as e:
            logging.error(f"Cobalt download failed: {str(e)}")
            raise
    
    async def _download_file(
        self, 
        file_url: str, 
        metadata: Dict,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[Path, Optional[Path], Dict]:
        """
        Скачивает файл по URL (redirect или tunnel) с поддержкой прогресса.
        """
        import uuid
        
        filename = metadata.get("filename", f"video_{uuid.uuid4().hex[:8]}.mp4")
        # Очистка имени файла от недопустимых символов
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
        
        file_path = DOWNLOADS_DIR / filename
        
        logging.info(f"Downloading file from: {file_url}")
        
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=600)  # 10 минут
        
        try:
            async with aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout
            ) as session:
                async with session.get(file_url, proxy=self.proxy) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to download file: HTTP {response.status}")
                    
                    # Получаем размер файла для прогресса
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    # Скачиваем файл chunked с прогрессом
                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Обновляем прогресс
                            # Keep download status message stable (funny status only)
            
            if not file_path.exists() or file_path.stat().st_size == 0:
                raise Exception("Downloaded file is empty or doesn't exist")
            
            logging.info(f"File downloaded: {file_path} ({file_path.stat().st_size} bytes)")
            
            # Формируем метаданные
            uploader = metadata.get("author") or metadata.get("uploader") or metadata.get("creator") or "Unknown"
            title = metadata.get("title") or filename.rsplit('.', 1)[0]
            result_metadata = {
                "title": title,
                "uploader": uploader,
                "webpage_url": metadata.get("url", ""),
                "duration": 0,
                "width": 0,
                "height": 0,
                "codec": "h264"  # Cobalt отдает H.264
            }
            
            return file_path, None, result_metadata
        
        except Exception as e:
            if file_path.exists():
                file_path.unlink()
            logging.error(f"File download failed: {str(e)}")
            raise
    
    async def _handle_picker(self, response: Dict) -> Tuple[List[Path], Optional[Path], Dict]:
        """
        Обрабатывает picker response (множественные файлы).
        Например, TikTok слайдшоу.
        """
        logging.info("Cobalt returned picker (multiple files)")
        
        picker_items = response.get("picker", [])
        if not picker_items:
            raise Exception("Picker response is empty")
        
        file_paths = []

        def guess_extension(item_url: str, mime: Optional[str]) -> str:
            if item_url:
                path = urlparse(item_url).path
                if "." in path:
                    ext = Path(path).suffix.lower()
                    if ext:
                        return ext
            if mime:
                mime_lower = mime.lower()
                if "jpeg" in mime_lower:
                    return ".jpg"
                if "png" in mime_lower:
                    return ".png"
                if "webp" in mime_lower:
                    return ".webp"
                if "mp3" in mime_lower:
                    return ".mp3"
                if "m4a" in mime_lower:
                    return ".m4a"
                if "aac" in mime_lower:
                    return ".aac"
                if "ogg" in mime_lower:
                    return ".ogg"
                if "mp4" in mime_lower:
                    return ".mp4"
            return ".bin"

        for idx, item in enumerate(picker_items):
            item_url = item.get("url")
            if not item_url:
                continue

            mime = item.get("mime") or item.get("type")
            ext = guess_extension(item_url, mime)
            filename = f"picker_{idx}{ext}"

            try:
                file_path, _, _ = await self._download_file(
                    item_url,
                    {"filename": filename}
                )
                file_paths.append(file_path)
            except Exception as e:
                logging.error(f"Failed to download picker item {idx}: {e}")

        metadata = {
            "title": response.get("title") or "Carousel Media",
            "uploader": response.get("author") or response.get("uploader") or response.get("creator") or "Unknown",
            "webpage_url": response.get("url", ""),
            "count": len(file_paths)
        }
        
        return file_paths, None, metadata


# Singleton instance
cobalt = CobaltClient()
