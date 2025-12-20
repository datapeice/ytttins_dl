import json
import logging
import subprocess
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Callable
import yt_dlp
from config import DOWNLOADS_DIR, DATA_DIR, COOKIES_CONTENT
from database.storage import stats
from database.models import Cookie

# Initialize cookies
if COOKIES_CONTENT:
    cookies_path = DATA_DIR / "cookies.txt"
    with open(cookies_path, "w") as f:
        f.write(COOKIES_CONTENT)
    logging.info("Cookies loaded from environment variable")

if stats.Session:
    try:
        with stats.Session() as session:
            cookie = session.query(Cookie).order_by(Cookie.updated_at.desc()).first()
            if cookie:
                cookies_path = DATA_DIR / "cookies.txt"
                with open(cookies_path, "w") as f:
                    f.write(cookie.content)
                logging.info("Cookies loaded from database")
    except Exception as e:
        logging.error(f"Error loading cookies from DB: {e}")

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

def get_platform(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
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
        logging.info(f"Extracted metadata for {file_path}: {meta}")
        return meta
    except Exception as e:
        logging.error(f"Error getting metadata for {file_path}: {e}")
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
        logging.error(f"Error resizing thumbnail {input_path}: {e}")
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
        
        logging.info(f"Converting {input_path.name} to H.264...")
        subprocess.run(cmd, check=True, capture_output=True)
        
        if output_path.exists():
            input_path.unlink()
            return output_path
        return input_path
    except Exception as e:
        logging.error(f"Error converting video to H.264: {e}")
        return input_path

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None) -> Tuple[Path, Optional[Path], Dict]:
    """Download media with optional progress updates"""
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
        format_str = f'bestvideo[height<={video_height}][vcodec^=h264]+bestaudio[ext=m4a]/bestvideo[height<={video_height}][vcodec^=avc]+bestaudio[ext=m4a]/best[height<={video_height}][vcodec^=h264]/best[height<={video_height}][vcodec^=avc]/best[height<={video_height}]/best'
    else:
        # Prioritize H.264/AVC for Telegram compatibility
        format_str = 'bestvideo[vcodec^=h264]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/best[vcodec^=h264]/best[vcodec^=avc]/best'

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
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                thumb_check = base_path.with_suffix(ext)
                if thumb_check.exists():
                    thumbnail_path = thumb_check
                    break
            
            if thumbnail_path:
                resized_thumb = resize_thumbnail(thumbnail_path)
                if resized_thumb:
                    if resized_thumb != thumbnail_path:
                        try:
                            thumbnail_path.unlink()
                        except:
                            pass
                    thumbnail_path = resized_thumb
                    
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
                if codec not in ['h264', 'avc']:
                    if progress_callback:
                        await progress_callback(f"🔄 Converting from {codec} to H.264...")
                    filename_path = Path(filename)
                    filename_path = convert_to_h264(filename_path)
                    filename = str(filename_path)
                    metadata = get_video_metadata(filename_path)
                    metadata['title'] = info.get('title', 'Unknown')
                    metadata['uploader'] = info.get('uploader', 'Unknown')
                    metadata['webpage_url'] = info.get('webpage_url', url)
                    
            return Path(filename), thumbnail_path, metadata
    except Exception as e:
        logging.error(f"Error downloading {url}: {str(e)}")
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
        logging.error(f"Error downloading TikTok photos {url}: {str(e)}")
        return [], {}
