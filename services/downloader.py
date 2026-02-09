import json
import logging
import subprocess
import os
import asyncio
import uuid
import aiohttp
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Callable, Union
import yt_dlp
from config import DOWNLOADS_DIR, DATA_DIR, COOKIES_CONTENT, COBALT_API_URL, USE_COBALT, HTTP_PROXY, HTTPS_PROXY
from database.storage import stats
from database.models import Cookie
from services.tiktok_scraper import download_tiktok_images

# Setup logger
logger = logging.getLogger(__name__)

# Initialize cookies
if COOKIES_CONTENT:
    cookies_path = DATA_DIR / "cookies.txt"
    with open(cookies_path, "w") as f:
        f.write(COOKIES_CONTENT)
    logger.info("[INIT] Cookies loaded from environment variable")

if stats.Session:
    try:
        with stats.Session() as session:
            cookie = session.query(Cookie).order_by(Cookie.updated_at.desc()).first()
            if cookie:
                cookies_path = DATA_DIR / "cookies.txt"
                with open(cookies_path, "w") as f:
                    f.write(cookie.content)
                logger.info("[INIT] Cookies loaded from database")
    except Exception as e:
        logger.error(f"[INIT] Error loading cookies from DB: {e}")

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

def get_platform(url: str) -> str:
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
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    elif "vimeo.com" in url_lower:
        return "vimeo"
    elif "dailymotion.com" in url_lower:
        return "dailymotion"
    elif "twitch.tv" in url_lower:
        return "twitch"
    else:
        return "unknown"

def get_video_metadata(file_path: Path) -> Dict[str, any]:
    """Extract video metadata using ffprobe"""
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height,duration,codec_name", 
            "-of", "json", 
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        
        if not data.get('streams'):
            logging.warning(f"No streams found in metadata for {file_path}")
            return {'width': 0, 'height': 0, 'duration': 0, 'codec': 'unknown'}
            
        stream = data['streams'][0]
        meta = {
            'width': int(stream.get('width', 0)),
            'height': int(stream.get('height', 0)),
            'duration': int(float(stream.get('duration', 0))),
            'codec': stream.get('codec_name', 'unknown')
        }
        logger.info(f"[YTDLP] Extracted metadata: {meta}")
        return meta
    except Exception as e:
        logger.error(f"[YTDLP] Error getting metadata: {e}")
        return {'width': 0, 'height': 0, 'duration': 0, 'codec': 'unknown'}

def resize_thumbnail(input_path: Path) -> Optional[Path]:
    """Resize thumbnail to max 320px width/height and convert to JPG"""
    try:
        output_path = input_path.with_suffix('.jpg')
        if output_path == input_path:
            output_path = input_path.parent / f"{input_path.stem}_thumb.jpg"
            
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
            "-q:v", "2",
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        if output_path.exists():
            return output_path
        return None
    except Exception as e:
        logger.error(f"[YTDLP] Error resizing thumbnail: {e}")
        return None

def convert_to_h264(input_path: Path) -> Path:
    """Convert video to H.264 codec if needed"""
    try:
        output_path = input_path.parent / f"{input_path.stem}_h264.mp4"
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        logger.info(f"[YTDLP] Converting {input_path.name} to H.264...")
        subprocess.run(cmd, check=True, capture_output=True)
        
        if output_path.exists():
            input_path.unlink()
            return output_path
        return input_path
    except Exception as e:
        logger.error(f"[YTDLP] Error converting to H.264: {e}")
        return input_path

async def download_via_cobalt(url: str, progress_callback: Optional[Callable] = None) -> Tuple[Optional[Path], Optional[Path], Dict]:
    """Download media using Cobalt API"""
    try:
        if progress_callback:
            await progress_callback("🔵 Trying Cobalt API...")
        
        logger.info(f"[COBALT] Requesting: {url}")
        
        # Prepare request
        api_url = COBALT_API_URL.rstrip('/') + '/api/json'
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        
        payload = {
            'url': url,
            'vCodec': 'h264',
            'vQuality': '1080',
            'aFormat': 'mp3',
            'filenamePattern': 'basic',
            'isAudioOnly': False
        }
        
        # Setup proxy if configured
        connector = None
        if HTTPS_PROXY or HTTP_PROXY:
            proxy_url = HTTPS_PROXY or HTTP_PROXY
            logger.info(f"[COBALT] Using proxy: {proxy_url[:20]}...")
            connector = aiohttp.TCPConnector()
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Make API request
            kwargs = {'headers': headers, 'json': payload}
            if HTTPS_PROXY or HTTP_PROXY:
                kwargs['proxy'] = HTTPS_PROXY or HTTP_PROXY
            
            async with session.post(api_url, **kwargs) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"[COBALT] API error {resp.status}: {error_text[:200]}")
                    return None, None, {}
                
                data = await resp.json()
                logger.info(f"[COBALT] Response status: {data.get('status')}")
                
                if data.get('status') != 'redirect' and data.get('status') != 'stream':
                    logger.error(f"[COBALT] Unexpected status: {data}")
                    return None, None, {}
                
                download_url = data.get('url')
                if not download_url:
                    logger.error(f"[COBALT] No download URL in response")
                    return None, None, {}
                
                logger.info(f"[COBALT] Downloading from: {download_url[:50]}...")
                
                # Download file
                if progress_callback:
                    await progress_callback("⬇️ Downloading via Cobalt...")
                
                unique_id = uuid.uuid4().hex[:8]
                temp_file = DOWNLOADS_DIR / f"cobalt_{unique_id}.mp4"
                
                download_kwargs = {}
                if HTTPS_PROXY or HTTP_PROXY:
                    download_kwargs['proxy'] = HTTPS_PROXY or HTTP_PROXY
                
                async with session.get(download_url, **download_kwargs) as dl_resp:
                    if dl_resp.status != 200:
                        logger.error(f"[COBALT] Download failed: {dl_resp.status}")
                        return None, None, {}
                    
                    with open(temp_file, 'wb') as f:
                        async for chunk in dl_resp.content.iter_chunked(8192):
                            f.write(chunk)
                
                logger.info(f"[COBALT] Downloaded: {temp_file.name} ({temp_file.stat().st_size} bytes)")
                
                # Extract metadata
                metadata = get_video_metadata(temp_file)
                metadata['title'] = data.get('filename', 'Video')
                metadata['uploader'] = 'Unknown'
                metadata['webpage_url'] = url
                
                return temp_file, None, metadata
                
    except asyncio.TimeoutError:
        logger.error(f"[COBALT] Timeout")
        return None, None, {}
    except Exception as e:
        logger.error(f"[COBALT] Error: {str(e)}")
        return None, None, {}

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    """Download media with optional progress updates. Returns (file_path(s), thumbnail, metadata)"""
    
    platform = get_platform(url)
    
    # Try Cobalt API first (if enabled)
    if USE_COBALT and platform in ['youtube', 'tiktok', 'instagram', 'twitter', 'reddit', 'facebook']:
        try:
            file_path, thumbnail_path, metadata = await download_via_cobalt(url, progress_callback)
            if file_path and file_path.exists():
                logger.info(f"[COBALT] Success!")
                return file_path, thumbnail_path, metadata
            else:
                logger.warning(f"[COBALT] Failed, falling back to yt-dlp")
        except Exception as e:
            logger.warning(f"[COBALT] Exception: {e}, falling back to yt-dlp")
    
    # Fallback to yt-dlp or if Cobalt is disabled
    
    # Handle TikTok slideshow separately - only if /photo/ in URL
    if platform == "tiktok" and "/photo/" in url:
        try:
            if progress_callback:
                await progress_callback("📥 Downloading TikTok slideshow...")
            
            # Try tikwm first for slideshows
            loop = asyncio.get_event_loop()
            files, metadata = await loop.run_in_executor(None, download_tiktok_images, url, DOWNLOADS_DIR)
            
            # If no images found, fall through to normal download
            if files:
                return files, None, metadata
            else:
                logger.warning("[TIKWM] No images found, trying yt-dlp")
        except Exception as e:
            logger.warning(f"[TIKWM] Slideshow download failed: {e}")
            # Fall through to normal download
    
    if progress_callback:
        await progress_callback("🔍 Extracting video info...")
    
    output_template = str(DOWNLOADS_DIR / "%(title)s.%(ext)s")
    
    cookie_file = DATA_DIR / "cookies.txt"
    if not cookie_file.exists():
        cookie_file = "cookies.txt" if os.path.exists("cookies.txt") else None
    
    if is_music:
        format_str = 'bestaudio/best'
    elif video_height:
        # Try to find H.264 video at specific height, fallback to any codec at that height
        # If specific height is not available, fallback to best available
        format_str = f'bestvideo[height<={video_height}][vcodec^=h264]+bestaudio[ext=m4a]/bestvideo[height<={video_height}][vcodec^=avc]+bestaudio[ext=m4a]/best[height<={video_height}][vcodec^=h264]/best[height<={video_height}][vcodec^=avc]/best[height<={video_height}]/best'
    else:
        # Prioritize H.264/AVC for Telegram compatibility
        format_str = 'bestvideo[vcodec^=h264]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/best[vcodec^=h264]/best[vcodec^=avc]/best'

    # Fallback for YouTube Shorts or when specific formats are missing
    if "youtube.com" in url or "youtu.be" in url:
         # Shorts often have limited formats, so we relax the constraints if the strict ones fail
         # But we can't easily retry inside yt-dlp options.
         # Instead, we can make the format string more permissive at the end.
         format_str += '/bestvideo+bestaudio/best'

    ydl_opts = {
        'format': format_str,
        'outtmpl': output_template,
        'restrictfilenames': True,
        'noplaylist': True,
        'extract_audio': is_music,
        'writethumbnail': True,
        'cookiefile': cookie_file,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'nocheckcertificate': True,
        'geo_bypass': True,
        'format_sort': ['res:1080', 'vcodec:h264', 'acodec:aac'],
        'postprocessors': [],
    }
    
    if is_music:
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        })
    else:
        # Only add thumbnail embedding if it's safe or we are sure about the container
        # For TikTok/Shorts, embedding often fails or causes issues with ffmpeg
        # We will skip embedding for now to ensure stability
        pass
        # ydl_opts['postprocessors'].append({
        #     'key': 'FFmpegThumbnailsConvertor',
        #     'format': 'jpg',
        # })
        # ydl_opts['postprocessors'].append({
        #     'key': 'EmbedThumbnail',
        # })
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if progress_callback:
                await progress_callback("⬇️ Downloading media...")
            
            info = ydl.process_ie_result(info, download=True)
            filename = ydl.prepare_filename(info)
            
            if is_music:
                filename = str(Path(filename).with_suffix('.mp3'))
            
            thumbnail_path = None
            base_path = Path(filename)
            for ext in ['.jpg', '.jpeg', '.png', '.webp', '.image']:
                thumb_check = base_path.with_suffix(ext)
                if thumb_check.exists():
                    thumbnail_path = thumb_check
                    logger.info(f"[YTDLP] Found thumbnail: {thumbnail_path.name}")
                    break
            
            if thumbnail_path:
                resized_thumb = resize_thumbnail(thumbnail_path)
                if resized_thumb:
                    logger.info(f"[YTDLP] Thumbnail resized: {resized_thumb.name}")
                    if resized_thumb != thumbnail_path:
                        try:
                            thumbnail_path.unlink()
                        except:
                            pass
                    thumbnail_path = resized_thumb
                else:
                    logger.warning(f"[YTDLP] Failed to resize thumbnail")
            else:
                logger.info("[YTDLP] No thumbnail found")
                    
            if is_music:
                metadata = {
                    'width': 0,
                    'height': 0,
                    'duration': int(info.get('duration') or 0),
                    'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'webpage_url': info.get('webpage_url', url),
                    'codec': 'audio'
                }
            else:
                if progress_callback:
                    await progress_callback("📊 Analyzing video codec...")
                
                metadata = get_video_metadata(Path(filename))
                if metadata['duration'] == 0:
                    metadata['duration'] = int(info.get('duration') or 0)
                if metadata['width'] == 0:
                    metadata['width'] = int(info.get('width') or 0)
                if metadata['height'] == 0:
                    metadata['height'] = int(info.get('height') or 0)
                
                metadata['title'] = info.get('title', 'Unknown')
                metadata['uploader'] = info.get('uploader', 'Unknown')
                metadata['webpage_url'] = info.get('webpage_url', url)
                
                # Convert to H.264 if needed
                codec = metadata.get('codec', '').lower()
                is_mp4 = str(filename).lower().endswith('.mp4')
                
                if codec not in ['h264', 'avc'] or not is_mp4:
                    if progress_callback:
                        await progress_callback(f"🔄 Converting from {codec} to H.264...")
                    
                    logger.info(f"[YTDLP] Video needs conversion: codec={codec}, mp4={is_mp4}")
                    filename_path = Path(filename)
                    filename_path = convert_to_h264(filename_path)
                    filename = str(filename_path)
                    
                    # Update metadata after conversion
                    metadata = get_video_metadata(filename_path)
                    metadata['title'] = info.get('title', 'Unknown')
                    metadata['uploader'] = info.get('uploader', 'Unknown')
                    metadata['webpage_url'] = info.get('webpage_url', url)
                    
            return Path(filename), thumbnail_path, metadata
    except Exception as e:
        logger.error(f"[YTDLP] Download error: {str(e)}")
        raise

async def download_tiktok_photos(url: str) -> Tuple[List[Path], Dict]:
    """Download TikTok photo slideshow"""
    
    cookie_file = DATA_DIR / "cookies.txt"
    if not cookie_file.exists():
        cookie_file = "cookies.txt" if os.path.exists("cookies.txt") else None
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': str(DOWNLOADS_DIR / "%(title)s_%(autonumber)s.%(ext)s"),
        'restrictfilenames': True,
        'cookiefile': cookie_file,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
        'extractor_args': {
            'tiktok': {
                'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Check for images in the info dict
            images = info.get('images', [])
            
            if images:
                photo_paths = []
                for idx, img_info in enumerate(images):
                    img_url = img_info.get('url')
                    if img_url:
                        img_filename = DOWNLOADS_DIR / f"{info.get('id', 'tiktok')}_{idx}.jpg"
                        
                        # Download image using yt-dlp's downloader
                        import urllib.request
                        urllib.request.urlretrieve(img_url, img_filename)
                        photo_paths.append(img_filename)
                
                metadata = {
                    'title': info.get('title', 'TikTok Photos'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'webpage_url': info.get('webpage_url', url),
                    'count': len(photo_paths)
                }
                
                return photo_paths, metadata
            else:
                return [], {}
    except Exception as e:
        logger.error(f"[YTDLP] TikTok photos error: {str(e)}")
        return [], {}
