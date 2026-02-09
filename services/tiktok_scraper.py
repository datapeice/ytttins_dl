import requests
from parsel import Selector
import uuid
import logging
from pathlib import Path
from typing import List, Tuple, Dict

# Setup logger with prefix
logger = logging.getLogger(__name__)

# Common headers for all requests
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def download_tiktok_images(link: str, output_dir: Path) -> Tuple[List[Path], Dict]:
    """
    Downloads TikTok slideshow images and audio using tikwm.com API.
    Returns (list_of_files, metadata).
    Raises Exception on failure.
    """
    return download_tikwm(link, output_dir)

def download_file(url: str, output_dir: Path, prefix: str) -> Path:
    """Download a single file and convert images to JPEG if needed."""
    response = requests.get(url, headers=DEFAULT_HEADERS, stream=True, timeout=15)
    if response.status_code != 200:
        raise Exception(f"Failed to download file: status {response.status_code}")
    
    content_type = response.headers.get("Content-Type", "")
    
    # Audio files - save as is
    if "audio" in content_type or "mp3" in content_type or "m4a" in content_type:
        ext = "mp3"
        filename = f"{prefix}_{uuid.uuid4().hex[:6]}.{ext}"
        path = output_dir / filename
        
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return path
    
    # Images - always convert to JPEG for Telegram compatibility
    try:
        from PIL import Image
        import io
        
        # Download to memory
        img_data = io.BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            img_data.write(chunk)
        img_data.seek(0)
        
        # Open and convert to JPEG
        img = Image.open(img_data)
        
        # Convert RGBA to RGB (for transparent images)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as JPEG
        filename = f"{prefix}_{uuid.uuid4().hex[:6]}.jpg"
        path = output_dir / filename
        img.save(path, 'JPEG', quality=95)
        
        return path
        
    except Exception as e:
        logger.error(f"[TIKWM] Failed to convert image, saving as-is: {e}")
        # Fallback: save raw file
        ext = "jpg"
        filename = f"{prefix}_{uuid.uuid4().hex[:6]}.{ext}"
        path = output_dir / filename
        
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return path

def download_tikwm(link: str, output_dir: Path) -> Tuple[List[Path], Dict]:
    """tikwm.com API - clean JSON API with reliable audio extraction"""
    import json
    import re
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    # tikwm API endpoint
    api_url = 'https://www.tikwm.com/api/'
    
    params = {
        'url': link,
        'hd': 1
    }
    
    response = requests.get(api_url, params=params, headers=headers, timeout=15)
    
    if response.status_code != 200:
        raise Exception(f"tikwm API returned status {response.status_code}")
    
    data = response.json()
    
    if data.get('code') != 0:
        raise Exception(f"tikwm API error: {data.get('msg', 'Unknown error')}")
    
    result = data.get('data', {})
    
    # Extract images
    image_urls = result.get('images', [])
    
    if not image_urls:
        raise Exception("No images found in tikwm response")
    
    # Extract audio/music URL
    audio_url = result.get('music') or result.get('music_info', {}).get('play')
    
    # Extract metadata
    author = result.get('author', {}).get('unique_id', 'Unknown')
    title = result.get('title', 'TikTok Slideshow')
    
    logger.info(f"[TIKWM] Found {len(image_urls)} images, audio: {bool(audio_url)}")
    
    # Download images
    files = []
    for i, img_url in enumerate(image_urls):
        try:
            files.append(download_file(img_url, output_dir, f"tiktok_img_{i}"))
        except Exception as e:
            logger.warning(f"[TIKWM] Failed to download image {i}: {e}")
    
    if not files:
        raise Exception("All image downloads failed")
    
    # Download audio if available
    if audio_url and audio_url.strip():
        try:
            logger.info(f"[TIKWM] Downloading audio from: {audio_url}")
            audio_file = download_file(audio_url, output_dir, "TikTok_Audio")
            files.append(audio_file)
            logger.info(f"[TIKWM] Audio downloaded successfully")
        except Exception as e:
            logger.warning(f"[TIKWM] Failed to download audio: {e}")
    
    metadata = {
        'title': title,
        'uploader': author,
        'webpage_url': link,
        'duration': result.get('duration', 0),
        'has_audio': audio_url is not None
    }
    
    return files, metadata
