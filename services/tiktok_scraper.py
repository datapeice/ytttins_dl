import requests
from parsel import Selector
import uuid
import logging
from pathlib import Path
from typing import List, Tuple, Dict

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
        logging.error(f"Failed to convert image, saving as-is: {e}")
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
    
    logging.info(f"tikwm: Found {len(image_urls)} images, audio: {bool(audio_url)}")
    
    # Download images
    files = []
    for i, img_url in enumerate(image_urls):
        try:
            files.append(download_file(img_url, output_dir, f"tiktok_img_{i}"))
        except Exception as e:
            logging.warning(f"Failed to download image {i}: {e}")
    
    if not files:
        raise Exception("All image downloads failed")
    
    # Download audio if available
    if audio_url and audio_url.strip():
        try:
            logging.info(f"Downloading audio from tikwm: {audio_url}")
            audio_file = download_file(audio_url, output_dir, "TikTok_Audio")
            files.append(audio_file)
            logging.info(f"Audio downloaded successfully from tikwm")
        except Exception as e:
            logging.warning(f"Failed to download audio from tikwm: {e}")
    
    metadata = {
        'title': title,
        'uploader': author,
        'webpage_url': link,
        'duration': result.get('duration', 0),
        'has_audio': audio_url is not None
    }
    
    return files, metadata

def download_snaptik(link: str, output_dir: Path) -> Tuple[List[Path], Dict]:
    """snaptik.app strategy - reliable for both images and audio"""
    import json
    import re
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Origin': 'https://snaptik.app',
        'Referer': 'https://snaptik.app/',
    }
    
    with requests.Session() as s:
        # Get the main page to get tokens
        r = s.get('https://snaptik.app/', headers=headers, timeout=10)
        
        # Extract token if present
        token_match = re.search(r'name="token" value="([^"]+)"', r.text)
        token = token_match.group(1) if token_match else ''
        
        # Post the URL
        post_headers = headers.copy()
        post_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        
        data = {
            'url': link,
            'token': token
        }
        
        response = s.post('https://snaptik.app/abc2.php', headers=post_headers, data=data, timeout=15)
        
        # Parse response
        image_urls = []
        audio_url = None
        author = 'Unknown'
        
        # Try to find download links in response
        # Snaptik returns HTML with download links
        selector = Selector(text=response.text)
        
        # Look for image URLs
        image_urls = selector.xpath('//a[contains(@href, "tikcdn") or contains(@href, "tiktokcdn")]/@href').getall()
        if not image_urls:
            # Alternative: look for img tags
            image_urls = selector.xpath('//img[contains(@src, "tiktok")]/@src').getall()
        
        # Look for audio/music URL
        audio_candidates = selector.xpath('//a[contains(@href, "music") or contains(@href, "sound") or contains(@href, "audio")]/@href').getall()
        for candidate in audio_candidates:
            if 'tikcdn' in candidate or 'tiktokcdn' in candidate:
                audio_url = candidate
                break
        
        # Extract author from original link
        match = re.search(r'@([^/]+)', link)
        if match:
            author = match.group(1)
        
        if not image_urls:
            raise Exception("No images found on snaptik")
        
        # Download files
        files = []
        for i, img_url in enumerate(image_urls):
            try:
                files.append(download_file(img_url, output_dir, f"tiktok_img_{i}"))
            except Exception as e:
                logging.warning(f"Failed to download image {i}: {e}")
        
        if not files:
            raise Exception("All image downloads failed")
        
        # Download audio if available
        if audio_url and audio_url.strip():
            try:
                logging.info(f"Downloading audio from snaptik: {audio_url}")
                audio_file = download_file(audio_url, output_dir, "tiktok_audio")
                files.append(audio_file)
                logging.info(f"Audio downloaded successfully from snaptik")
            except Exception as e:
                logging.warning(f"Failed to download audio from snaptik: {e}")
        
        metadata = {
            'title': 'TikTok Slideshow',
            'uploader': author,
            'webpage_url': link,
            'duration': 0,
            'has_audio': audio_url is not None
        }
        
        return files, metadata

def download_v3(link: str, output_dir: Path) -> Tuple[List[Path], Dict]:
    """tiktokio.com strategy - updated for their JSON API"""
    import json
    import re
    
    headers_v3 = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
        'Accept': 'application/json, text/html, */*',
        'HX-Request': 'true',
        'HX-Trigger': 'search-btn',
        'HX-Target': 'tiktok-parse-result',
        'HX-Current-URL': 'https://tiktokio.com/',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://tiktokio.com',
        'Referer': 'https://tiktokio.com/'
    }

    with requests.Session() as s:
        # Get prefix token
        try:
            r = s.get("https://tiktokio.com/", headers=headers_v3, timeout=10)
            selector = Selector(text=r.text)
            prefix = selector.css('input[name="prefix"]::attr(value)').get()
            if not prefix:
                prefix = ""
        except Exception as e:
            logging.warning(f"Failed to get prefix: {e}")
            prefix = ""
        
        data = {'prefix': prefix, 'vid': link}
        response = s.post('https://tiktokio.com/api/v1/tk-htmx', headers=headers_v3, data=data, timeout=15)
        
        # Parse response
        image_urls = []
        audio_url = None
        author = 'Unknown'
        title = 'TikTok Slideshow'
        
        # Try to parse as JSON first
        try:
            json_data = json.loads(response.text)
            
            # Response might be wrapped in HTML or be pure JSON
            if isinstance(json_data, dict):
                # Extract from various possible JSON structures
                if 'images' in json_data:
                    image_urls = json_data['images']
                elif 'image_data' in json_data:
                    image_urls = json_data['image_data'].get('urls', [])
                
                audio_url = json_data.get('music') or json_data.get('audio') or json_data.get('music_info', {}).get('url')
                author = json_data.get('author', {}).get('unique_id') or json_data.get('author_name', 'Unknown')
                title = json_data.get('title') or json_data.get('desc', 'TikTok Slideshow')
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Fallback: parse as HTML
        if not image_urls:
            selector = Selector(text=response.text)
            
            # Try different selectors
            image_urls = selector.css('img.result-image::attr(src)').getall()
            if not image_urls:
                image_urls = selector.xpath('//a[contains(@download, "image")]/@href').getall()
            if not image_urls:
                image_urls = selector.css('div.image-container img::attr(src)').getall()
            if not image_urls:
                # Last resort: find all image links
                all_imgs = selector.xpath('//img/@src').getall()
                image_urls = [url for url in all_imgs if 'tiktok' in url.lower() or url.startswith('http')]
            
            # Extract audio from HTML
            audio_url = selector.xpath('//a[contains(text(), "Download MP3") or contains(@class, "music")]/@href').get()
            if not audio_url:
                audio_url = selector.css('audio source::attr(src)').get()
        
        # Extract author from original link if not found
        if author == 'Unknown':
            match = re.search(r'@([^/]+)', link)
            if match:
                author = match.group(1)
        
        if not image_urls:
            raise Exception(f"No images found on tiktokio. Response preview: {response.text[:500]}")
            
        files = []
        for i, img_url in enumerate(image_urls):
            try:
                files.append(download_file(img_url, output_dir, f"tiktok_img_{i}"))
            except Exception as e:
                logging.warning(f"Failed to download image {i}: {e}")
        
        if not files:
            raise Exception("All image downloads failed")
        
        # Download audio if available
        if audio_url and audio_url.strip():
            try:
                # Fix relative URLs
                if audio_url.startswith('/'):
                    audio_url = 'https://tiktokio.com' + audio_url
                elif not audio_url.startswith('http'):
                    audio_url = 'https://tiktokio.com/' + audio_url
                    
                logging.info(f"Downloading audio from: {audio_url}")
                if audio_url.startswith('http'):
                    audio_file = download_file(audio_url, output_dir, "tiktok_audio")
                    files.append(audio_file)
                    logging.info(f"Audio downloaded successfully")
            except Exception as e:
                logging.warning(f"Failed to download audio: {e}")
            
        metadata = {
            'title': title,
            'uploader': author,
            'webpage_url': link,
            'duration': 0,
            'has_audio': audio_url is not None
        }
        
        return files, metadata

def download_v2(link: str, output_dir: Path) -> Tuple[List[Path], Dict]:
    """musicaldown.com strategy"""
    import re
    
    headers_v2 = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://musicaldown.com',
        'Referer': 'https://musicaldown.com/en?ref=more',
    }

    with requests.Session() as s:
        r = s.get("https://musicaldown.com/en", headers=headers_v2, timeout=10)
        selector = Selector(text=r.text)
        
        token_a_name = selector.xpath('//*[@id="link_url"]/@name').get()
        token_b_name = selector.xpath('//*[@id="submit-form"]/div/div[1]/input[2]/@name').get()
        token_b_value = selector.xpath('//*[@id="submit-form"]/div/div[1]/input[2]/@value').get()
        
        if not token_a_name or not token_b_name:
            raise Exception("Could not find tokens on musicaldown")

        data = {
            token_a_name: link,
            token_b_name: token_b_value,
            'verify': '1',
        }

        response = s.post('https://musicaldown.com/download', headers=headers_v2, data=data, timeout=15)
        selector = Selector(text=response.text)
        
        # Extract images
        image_urls = selector.xpath('//div[@class="card-image"]/img/@src').getall()
        if not image_urls:
            image_urls = selector.xpath('//img[contains(@src, "tiktok")]/@src').getall()
        
        # Extract audio - try multiple strategies
        audio_url = None
        
        # Strategy 1: Look for direct download links (exclude social media share buttons)
        audio_links = selector.xpath('//a[contains(@href, ".mp3") or contains(@href, "audio") or contains(@href, "music")]/@href').getall()
        for link_candidate in audio_links:
            # Skip social media and external links
            if any(x in link_candidate.lower() for x in ['facebook.com', 'twitter.com', 'instagram.com', 'share']):
                continue
            audio_url = link_candidate
            logging.info(f"Found audio URL via mp3 link: {audio_url}")
            break
        
        # Strategy 2: Look specifically for musicaldown download links
        if not audio_url:
            # Look for download buttons that are NOT images
            download_links = selector.xpath('//a[contains(@class, "download")]/@href').getall()
            for link_candidate in download_links:
                # Skip if it's an image or social link
                if any(x in link_candidate.lower() for x in ['image', 'facebook', 'twitter', 'share', '.jpg', '.png', '.webp']):
                    continue
                # Prefer links with 'music', 'sound', or 'audio'
                if any(x in link_candidate.lower() for x in ['music', 'sound', 'audio', '.mp3', '.m4a']):
                    audio_url = link_candidate
                    logging.info(f"Found audio URL via download button: {audio_url}")
                    break
        
        # Strategy 3: Look in specific containers (musicaldown structure)
        if not audio_url:
            # Check for audio in result container
            audio_url = selector.xpath('//div[contains(@class, "result")]//a[contains(@href, "download") and not(contains(@href, "image"))]/@href').get()
            if audio_url and 'facebook' not in audio_url.lower():
                logging.info(f"Found audio URL in result container: {audio_url}")
        
        # Extract author
        author = 'Unknown'
        author_text = selector.xpath('//div[contains(@class, "author")]//text()').get()
        if author_text:
            author = author_text.strip()
        else:
            match = re.search(r'@([^/]+)', link)
            if match:
                author = match.group(1)
        
        if not image_urls:
             raise Exception("No images found on musicaldown")
        
        # Log found URLs for debugging
        logging.info(f"Found {len(image_urls)} images, audio_url: {audio_url if audio_url else 'None'}")
             
        files = []
        for i, img_url in enumerate(image_urls):
            try:
                files.append(download_file(img_url, output_dir, f"tiktok_img_{i}"))
            except Exception as e:
                logging.warning(f"Failed to download image {i}: {e}")
        
        if not files:
            raise Exception("All image downloads failed")
        
        # Download audio if available
        if audio_url and audio_url.strip():
            try:
                # Fix relative URLs
                if audio_url.startswith('/'):
                    audio_url = 'https://musicaldown.com' + audio_url
                elif not audio_url.startswith('http'):
                    audio_url = 'https://musicaldown.com/' + audio_url
                    
                logging.info(f"Downloading audio from: {audio_url}")
                audio_file = download_file(audio_url, output_dir, "tiktok_audio")
                files.append(audio_file)
                logging.info(f"Audio downloaded successfully")
            except Exception as e:
                logging.warning(f"Failed to download audio: {e}")
            
        metadata = {
            'title': 'TikTok Slideshow',
            'uploader': author,
            'webpage_url': link,
            'duration': 0,
            'has_audio': audio_url is not None
        }
        
        return files, metadata
