import logging
import time
import os
import uuid
import yt_dlp
import asyncio
import random
import aiohttp
import requests
import concurrent.futures
import subprocess
from pathlib import Path
from typing import Tuple, Dict, Optional, Callable, Union, List

from config import DOWNLOADS_DIR, DATA_DIR, COOKIES_CONTENT, USE_COBALT, COBALT_API_URL, SOCKS_PROXY
from database.storage import stats
from database.models import Cookie
from services.tiktok_scraper import download_tiktok_images, fetch_tiktok_metadata
from services.ai_extractor_agent import get_plugin_dirs, run_ai_extractor_autofix, should_attempt_ai_autofix

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
]

def generate_video_thumbnail(video_path: Path, output_path: Path) -> bool:
    """Generate a high-quality thumbnail from video using ffmpeg."""
    try:
        logging.info(f"Generating thumbnail for {video_path.name}")
        # Take a frame from 1 second in to avoid black start
        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:01",
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", "format=yuv420p,scale=w=320:h=320:force_original_aspect_ratio=decrease",
            "-q:v", "2",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logging.warning(f"ffmpeg thumbnail generation failed: {result.stderr}")
            return False
        return True
    except Exception as e:
        logging.error(f"Error generating thumbnail: {e}")
        return False

    return 0, 0

def probe_video_dimensions(video_path: Path) -> Tuple[int, int]:
    """Probe video dimensions using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            dims = result.stdout.strip().split('x')
            if len(dims) == 2:
                return int(dims[0]), int(dims[1])
    except Exception:
        pass
    return 0, 0

def probe_video_codec(video_path: Path) -> str:
    """Probe video codec using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().lower()
    except Exception:
        pass
    return ""

def convert_video_to_h264(input_path: Path) -> Path:
    """Convert video to H.264 using ffmpeg with fast settings."""
    output_path = input_path.parent / f"{input_path.stem}_h264.mp4"
    try:
        logging.info(f"Transcoding {input_path.name} to H.264 (iPhone compatibility)")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Minimal CPU usage (high speed)
            "-crf", "23",            # Standard quality
            "-c:a", "copy",          # Keep audio as is
            "-movflags", "+faststart",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and output_path.exists():
            input_path.unlink()  # Delete original VP9 file
            return output_path
    except Exception as e:
        logging.error(f"Failed to transcode video: {e}")
    
    if output_path.exists():
        output_path.unlink()
    return input_path  # Return original if failed

# TLS fingerprints для curl-cffi (имитация браузеров)
# Список реально доступных targets в curl_cffi 0.5.10 (формат из --list-impersonate-targets)
IMPERSONATE_TARGETS = [
    'chrome-110',      # Chrome 110
    'chrome-107',      # Chrome 107
    'chrome-104',      # Chrome 104
    'chrome-101',      # Chrome 101
    'chrome-100',      # Chrome 100
    'chrome-99',       # Chrome 99
    'edge-101',        # Edge 101
    'edge-99',         # Edge 99
    'safari-15.5',     # Safari 15.5
    'safari-15.3',     # Safari 15.3
]

try:
    from yt_dlp.networking.impersonate import ImpersonateTarget
except Exception:
    ImpersonateTarget = None


def build_impersonate_target(value: str):
    if not ImpersonateTarget:
        return value
    for method_name in ("from_str", "parse", "from_string"):
        method = getattr(ImpersonateTarget, method_name, None)
        if method:
            try:
                return method(value)
            except Exception:
                continue
    try:
        return ImpersonateTarget(value)
    except Exception:
        return value

cobalt_client = None

# Import CobaltClient only if USE_COBALT is enabled
if USE_COBALT and COBALT_API_URL:
    try:
        from services.cobalt_client import CobaltClient
        cobalt_client = CobaltClient()
        logging.info(f"✅ Cobalt client initialized: {COBALT_API_URL}")
    except Exception as e:
        logging.error(f"❌ Failed to initialize Cobalt client: {e}")
        cobalt_client = None

# Diagnostic: Check curl_cffi availability
try:
    import curl_cffi
    logging.info(f"✅ curl_cffi {curl_cffi.__version__} available for TLS impersonation")
except ImportError:
    logging.warning(f"⚠️ curl_cffi not installed - TLS impersonation disabled")
except Exception as e:
    logging.error(f"❌ curl_cffi error: {e}")
else:
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
    elif "soundcloud.com" in url_lower:
        return "soundcloud"
    elif "dailymotion.com" in url_lower or "dai.ly" in url_lower:
        return "dailymotion"
    elif "pornhub.com" in url_lower:
        return "pornhub"
    elif "spotify.com" in url_lower:
        return "spotify"
    elif "://t.me" in url_lower or "://telegram.me" in url_lower:
        return "unknown"
    elif "https://" in url_lower or "http://" in url_lower:
        # Check if it's a torrent file
        if url_lower.split("?")[0].endswith(".torrent") or "/magnet/" in url_lower:
             return "torrent"
        # Check if it's a direct media file first
        if any(url_lower.split("?")[0].endswith(ext) for ext in ('.mp4', '.mov', '.webm', '.m4v', '.m3u8', '.ts')):
             return "video"
        # yt-dlp supports 1800+ sites, try generic video classification
        return "video"
    elif url_lower.startswith("magnet:"):
        return "torrent"
    else:
        return "unknown"

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

def is_playlist(url: str) -> bool:
    """Detect if the URL is a playlist or album."""
    url_lower = url.lower()
    
    # YouTube / Music playlists
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        # If it's a single video with a list context, treat as single video
        if "watch?v=" in url_lower and "list=" in url_lower:
            return False
        if "youtu.be/" in url_lower and "list=" in url_lower:
            return False
        if "list=" in url_lower or "playlist" in url_lower:
            return True
            
    # YouTube Music albums (often playlists)
    if "music.youtube.com" in url_lower and "browse/VLPL" in url:
        return True
    return False

def unshorten_reddit_url(url: str, proxy_url: Optional[str]) -> str:
    if "/comments/" in url:
        return url
    if "reddit.com" not in url or "/s/" not in url:
        return url

    proxies = None
    if proxy_url:
        proxy_value = proxy_url.replace("socks5h", "socks5")
        proxies = {"http": proxy_value, "https": proxy_value}

    headers = {"User-Agent": USER_AGENTS[0]}

    try:
        response = requests.head(url, proxies=proxies, headers=headers, allow_redirects=True, timeout=10)
        final_url = response.url
        if final_url and ("/s/" in final_url):
            response = requests.get(url, proxies=proxies, headers=headers, allow_redirects=True, timeout=10)
            final_url = response.url
        if final_url and "?" in final_url:
            final_url = final_url.split("?")[0]
        return final_url or url
    except Exception as e:
        logging.warning(f"Failed to unshorten Reddit URL: {e}")
        return url


def resolve_facebook_share_url(url: str) -> str:
    """Resolve facebook.com/share/r/... or fb.watch/... to canonical facebook.com/reel/ID URL."""
    import re
    # Already a direct/canonical URL
    if re.search(r'facebook\.com/(reel|watch|video|videos)/[0-9]+', url):
        return url
    # Try to follow redirects to get the canonical URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # Use session for cookies if available
    session = requests.Session()
    cookie_file = DATA_DIR / "cookies.txt"
    if cookie_file.exists():
        try:
            from http.cookiejar import MozillaCookieJar
            cj = MozillaCookieJar(str(cookie_file))
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cj)
        except Exception:
            pass

    try:
        resp = session.head(url, headers=headers, allow_redirects=True, timeout=10)
        resolved = resp.url
        # Strip query params (tracking noise)
        if '?' in resolved:
            resolved = resolved.split('?')[0]
        if resolved and 'facebook.com' in resolved and resolved != url:
            logging.info(f"✅ Resolved Facebook URL: {url} → {resolved}")
            return resolved
    except Exception as e:
        logging.warning(f"Failed to resolve Facebook share URL: {e}")
    return url


def _download_reddit_direct(url: str, proxy_url: Optional[str] = None) -> Optional[Union[Path, List[Path]]]:
    """
    Fallback: fetch Reddit post JSON API, extract v.redd.it HLS/DASH video URL,
    download video+audio separately and merge with ffmpeg.
    Returns Path to merged mp4, or None on failure.
    """
    import re, subprocess, tempfile

    # Normalize URL: ensure it ends with .json and use old.reddit.com to avoid JS pages
    post_url = url.rstrip('/')
    if '?' in post_url:
        post_url = post_url.split('?')[0]
    json_url = post_url + '/.json'

    proxies = None
    if proxy_url:
        pv = proxy_url.replace('socks5h', 'socks5')
        proxies = {'http': pv, 'https': pv}

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; RedditBot/1.0; +https://github.com/ytttins)',
        'Accept': 'application/json',
    }

    try:
        resp = requests.get(json_url, headers=headers, proxies=proxies, timeout=15)
        if resp.status_code == 429:
            logging.warning("[REDDIT-DIRECT] Rate limited on JSON API")
            return None
        if resp.status_code != 200:
            logging.warning(f"[REDDIT-DIRECT] JSON API returned {resp.status_code}")
            return None
        data = resp.json()
    except Exception as e:
        logging.warning(f"[REDDIT-DIRECT] Failed to fetch JSON: {e}")
        return None

        # Try crosspost
        if not video_url:
            xposts = post.get('crosspost_parent_list') or []
            if xposts:
                xpost = xposts[0]
                xmedia = xpost.get('media') or xpost.get('secure_media') or {}
                reddit_video = xmedia.get('reddit_video', {})
                video_url = reddit_video.get('fallback_url') or reddit_video.get('hls_url')

        # === IMAGE / GALLERY SUPPORT ===
        if not video_url:
            image_urls = []
            
            # Case 1: Gallery
            if post.get('is_gallery') and 'media_metadata' in post:
                metadata = post['media_metadata']
                gallery_data = post.get('gallery_data', {}).get('items', [])
                
                # Use gallery order if available
                item_ids = [item['media_id'] for item in gallery_data] if gallery_data else metadata.keys()
                
                for mid in item_ids:
                    if mid in metadata:
                        media_item = metadata[mid]
                        # Try to get highest resolution version
                        s = media_item.get('s', {})
                        img_url = s.get('u') or s.get('gif')
                        if img_url:
                            image_urls.append(img_url.replace('&amp;', '&'))
            
            # Case 2: Single Image or Preview
            elif not post.get('is_video'):
                url_candidate = post.get('url', '')
                if any(url_candidate.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    image_urls.append(url_candidate)
                elif 'preview' in post:
                    # Try to get the highest res source from preview images
                    try:
                        p_images = post['preview'].get('images', [])
                        if p_images:
                            source = p_images[0].get('source', {})
                            p_url = source.get('url')
                            if p_url:
                                image_urls.append(p_url.replace('&amp;', '&'))
                    except: pass
                
                # Last resort: thumbnail if it's a valid link
                if not image_urls and post.get('thumbnail', '').startswith('http'):
                    image_urls.append(post['thumbnail'])
                
            if image_urls:
                logging.info(f"[REDDIT-DIRECT] Found gallery/images: {len(image_urls)} items")
                downloaded_images = []
                unique_id = uuid.uuid4().hex[:8]
                
                for i, img_url in enumerate(image_urls):
                    try:
                        ext = '.jpg'
                        if '.png' in img_url.lower(): ext = '.png'
                        elif '.webp' in img_url.lower(): ext = '.webp'
                        elif '.gif' in img_url.lower(): ext = '.gif'
                        
                        img_path = DOWNLOADS_DIR / f"reddit_{unique_id}_{i}{ext}"
                        ir = requests.get(img_url, headers=headers, proxies=proxies, timeout=30)
                        if ir.status_code == 200:
                            with open(img_path, 'wb') as f:
                                f.write(ir.content)
                            downloaded_images.append(img_path)
                    except Exception as img_err:
                        logging.error(f"[REDDIT-DIRECT] Image {i} download error: {img_err}")
                
                if downloaded_images:
                    return downloaded_images if len(downloaded_images) > 1 else downloaded_images[0]
                    
            logging.warning("[REDDIT-DIRECT] No video or image content found in post JSON")
            return None

        # Strip quality param to get best quality
        video_url = video_url.split('?')[0]
        # Derive audio URL: replace DASH_XXX with DASH_audio
        audio_url = re.sub(r'DASH_\d+(\.mp4)?$', 'DASH_audio.mp4', video_url)

        unique_id = uuid.uuid4().hex[:8]
        video_tmp = DOWNLOADS_DIR / f"reddit_v_{unique_id}.mp4"
        audio_tmp = DOWNLOADS_DIR / f"reddit_a_{unique_id}.mp4"
        output_path = DOWNLOADS_DIR / f"reddit_{unique_id}.mp4"

        dl_headers = {
            'User-Agent': headers['User-Agent'],
            'Referer': 'https://www.reddit.com/',
        }

        # Download video stream
        logging.info(f"[REDDIT-DIRECT] Downloading video: {video_url}")
        vr = requests.get(video_url, headers=dl_headers, proxies=proxies, stream=True, timeout=60)
        if vr.status_code != 200:
            logging.warning(f"[REDDIT-DIRECT] Video stream returned {vr.status_code}")
            return None
        with open(video_tmp, 'wb') as f:
            for chunk in vr.iter_content(8192):
                f.write(chunk)

        # Try to download audio stream (may not exist for old posts)
        has_audio = False
        try:
            ar = requests.get(audio_url, headers=dl_headers, proxies=proxies, stream=True, timeout=30)
            if ar.status_code == 200:
                with open(audio_tmp, 'wb') as f:
                    for chunk in ar.iter_content(8192):
                        f.write(chunk)
                has_audio = True
                logging.info("[REDDIT-DIRECT] Audio stream downloaded")
        except Exception:
            pass

        # Merge with ffmpeg
        if has_audio:
            cmd = [
                'ffmpeg', '-y',
                '-i', str(video_tmp),
                '-i', str(audio_tmp),
                '-c:v', 'copy', '-c:a', 'aac',
                '-movflags', '+faststart',
                str(output_path)
            ]
        else:
            cmd = [
                'ffmpeg', '-y',
                '-i', str(video_tmp),
                '-c', 'copy',
                str(output_path)
            ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)
        # Cleanup temp files
        for tmp in (video_tmp, audio_tmp):
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

        if result.returncode != 0:
            logging.error(f"[REDDIT-DIRECT] ffmpeg failed: {result.stderr.decode()[:300]}")
            return None

        logging.info(f"[REDDIT-DIRECT] ✅ Downloaded and merged: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"[REDDIT-DIRECT] Unexpected error: {e}")
        return None

def _download_facebook_direct(url: str, proxy_url: Optional[str] = None) -> Optional[Path]:
    """
    Fallback: scrape Facebook page HTML to extract video CDN URLs.
    Works when yt-dlp extractor is broken (Cannot parse data bug).
    """
    import re, subprocess

    proxies = None
    if proxy_url:
        pv = proxy_url.replace('socks5h', 'socks5')
        proxies = {'http': pv, 'https': pv}

    # Load Netscape cookies if available
    session = requests.Session()
    cookie_file = DATA_DIR / "cookies.txt"
    if cookie_file.exists():
        try:
            from http.cookiejar import MozillaCookieJar
            cj = MozillaCookieJar(str(cookie_file))
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cj)
            logging.info(f"[FB-DIRECT] Loaded cookies from {cookie_file.name}")
        except Exception as ce:
            logging.warning(f"[FB-DIRECT] Failed to load cookies: {ce}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Dest': 'document',
    }

    # Also try mbasic/mobile FB which is simpler HTML
    urls_to_try = [url]
    # Convert to mbasic if not already
    if 'mbasic.facebook' not in url:
        mbasic = url.replace('www.facebook.com', 'mbasic.facebook.com').replace('m.facebook.com', 'mbasic.facebook.com')
        urls_to_try.append(mbasic)

    video_url = None
    for try_url in urls_to_try:
        try:
            resp = session.get(try_url, headers=headers, proxies=proxies, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                logging.warning(f"[FB-DIRECT] HTTP {resp.status_code} for {try_url}")
                continue
            html = resp.text

            # Patterns that appear in Facebook's page source (HD first, then SD)
            patterns = [
                r'"browser_native_hd_url"\s*:\s*"([^"]+)"',
                r'"browser_native_sd_url"\s*:\s*"([^"]+)"',
                r'"playable_url_quality_hd"\s*:\s*"([^"]+)"',
                r'"playable_url"\s*:\s*"([^"]+)"',
                r'"playable_url_quality_standard"\s*:\s*"([^"]+)"',
                r'"hd_src_no_ratelimit"\s*:\s*"([^"]+)"',
                r'"sd_src_no_ratelimit"\s*:\s*"([^"]+)"',
                r'hd_src\s*:\s*"([^"]+\.mp4[^"]*?)"',
                r'sd_src\s*:\s*"([^"]+\.mp4[^"]*?)"',
                r'"video_url"\s*:\s*"([^"]+)"',
                r'"scrubber_video_url"\s*:\s*"([^"]+)"',
                r'\[\{"url"\s*:\s*"([^"]+\.mp4[^"]*?)"',  # Common in GraphQL arrays
            ]

            for pattern in patterns:
                m = re.search(pattern, html)
                if m:
                    candidate = m.group(1).replace('\\/', '/').replace('\\u0025', '%').replace('\\u0026', '&')
                    if 'fbcdn.net' in candidate or 'fbext' in candidate or '.mp4' in candidate:
                        video_url = candidate
                        logging.info(f"[FB-DIRECT] Found video URL via pattern: {pattern[:40]}")
                        break
            if video_url:
                break
        except Exception as e:
            logging.warning(f"[FB-DIRECT] Error fetching {try_url}: {e}")
            continue

    if not video_url:
        # Final attempt: extract video ID and try a canonical page
        # Search for long sequence of digits at end of URL or after a slash
        video_id_match = re.search(r'(?:/videos/|/reel/|/pcb\.[0-9]+/|v=)([0-9]{12,})', url)
        if not video_id_match:
             video_id_match = re.search(r'/([0-9]{12,})', url)
             
        if video_id_match:
            video_id = video_id_match.group(1)
            can_url = f"https://www.facebook.com/video.php?v={video_id}"
            logging.info(f"[FB-DIRECT] No patterns matched in original page. Trying canonical: {can_url}")
            try:
                resp = session.get(can_url, headers=headers, proxies=proxies, timeout=15, allow_redirects=True)
                if resp.status_code == 200:
                    html = resp.text
                    for pattern in patterns:
                        m = re.search(pattern, html)
                        if m:
                            candidate = m.group(1).replace('\\/', '/').replace('\\u0025', '%').replace('\\u0026', '&')
                            if 'fbcdn.net' in candidate or 'fbext' in candidate or '.mp4' in candidate:
                                video_url = candidate
                                logging.info(f"[FB-DIRECT] Found video URL in canonical page via pattern: {pattern[:40]}")
                                break
            except Exception as e:
                logging.warning(f"[FB-DIRECT] Error fetching canonical {can_url}: {e}")

    if not video_url:
        logging.warning("[FB-DIRECT] No video URL found in page HTML")
        return None

    # Download the video
    unique_id = uuid.uuid4().hex[:8]
    output_path = DOWNLOADS_DIR / f"facebook_{unique_id}.mp4"
    try:
        dl_headers = dict(headers)
        dl_headers['Accept'] = 'video/mp4,video/*;q=0.9,*/*;q=0.8'
        # Use simple requests with proxies for the actual file download to avoid potential session issues with binary streams
        vr = requests.get(video_url, headers=dl_headers, proxies=proxies, stream=True, timeout=120)
        if vr.status_code != 200:
            logging.warning(f"[FB-DIRECT] Video download returned HTTP {vr.status_code}")
            return None
        with open(output_path, 'wb') as f:
            for chunk in vr.iter_content(8192):
                f.write(chunk)
        logging.info(f"[FB-DIRECT] ✅ Downloaded: {output_path} ({output_path.stat().st_size // 1024} KB)")
        return output_path
    except Exception as e:
        logging.error(f"[FB-DIRECT] Download error: {e}")
        if output_path.exists():
            output_path.unlink()
        return None


def _download_generic_stream(url: str, proxy_url: Optional[str] = None) -> Optional[Path]:
    """
    Scrape any HTML page for video stream patterns (DASH, HLS, direct MP4) 
    that might be hidden in JS or data attributes.
    """
    import re, requests
    from urllib.parse import urljoin
    
    proxies = None
    if proxy_url:
        pv = proxy_url.replace('socks5h', 'socks5')
        proxies = {'http': pv, 'https': pv}

    user_agent = random.choice(USER_AGENTS)
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': url
    }

    try:
        if not url.startswith('http'):
            return None
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text

        # Patterns for video streams, prioritized by likely quality/directness
        patterns = [
            r'"file"\s*:\s*"([^"]+\.(?:mp4|m3u8|webm)[^"]*)"',
            r'"src"\s*:\s*"([^"]+\.(?:mp4|m3u8|webm)[^"]*)"',
            r'"video_url"\s*:\s*"([^"]+)"',
            r'"playable_url"\s*:\s*"([^"]+)"',
            r'"hls_url"\s*:\s*"([^"]+)"',
            r'source\s+src\s*=\s*"([^"]+)"',
            r'data-video-src\s*=\s*"([^"]+)"',
            r'data-src\s*=\s*"([^"]+\.mp4[^"]*)"',
        ]

        found_urls = []
        for pattern in patterns:
            matches = re.finditer(pattern, html)
            for match in matches:
                candidate = match.group(1).replace('\\/', '/').replace('\\u0025', '%').replace('\\u0026', '&')
                if candidate.startswith('//'):
                    candidate = 'https:' + candidate
                elif candidate.startswith('/'):
                    candidate = urljoin(url, candidate)
                elif not candidate.startswith('http'):
                    continue
                
                # Filter out ads or obvious garbage
                low_cand = candidate.lower()
                if any(x in low_cand for x in ['ads', 'pixel', 'tracking', '/ad/']):
                    continue
                
                if candidate not in found_urls:
                    found_urls.append(candidate)

        if not found_urls:
            # Fallback scan for any mp4/m3u8 link
            ext_matches = re.findall(r'https?://[^"\s>]+(?:\.mp4|\.m3u8)[^"\s>]*', html)
            for cand in ext_matches:
                 if 'ads' not in cand.lower() and cand not in found_urls:
                     found_urls.append(cand)

        if not found_urls:
            return None

        # Prefer higher quality (avoid 240p/144p if better exists)
        # Clean candidates from trailing commas/bracket artifacts often found in JS
        cleaned_urls = []
        for cand in found_urls:
            # Remove trailing part after a comma if it looks like JS array [480p] etc.
            # but keep it if it's part of query string. 
            # Usually adult sites have "url","[quality]"
            c = cand.rstrip(',').rstrip(']').strip()
            if ',' in c and not any(x in c.split(',')[-1] for x in ['mp4','m3u8','?','=']):
                c = c.split(',')[0].strip('"').strip("'")
            if c not in cleaned_urls:
                cleaned_urls.append(c)

        video_url = cleaned_urls[0]
        for cand in cleaned_urls:
            low_cand = cand.lower()
            if any(q in low_cand for q in ['1080p', '720p', '480p', 'hd']):
                video_url = cand
                if '1080p' in low_cand or '720p' in low_cand: 
                    break # Stop at first high-quality link

        logging.info(f"[GENERIC-STREAM] Best stream found: {video_url[:100]}")

        unique_id = uuid.uuid4().hex[:8]
        output_path = DOWNLOADS_DIR / f"generic_{unique_id}.mp4"
        
        # HLS Download
        if '.m3u8' in video_url.lower():
            logging.info(f"[GENERIC-STREAM] Starting HLS download via ffmpeg...")
            cmd = [
                'ffmpeg', '-y', '-i', video_url,
                '-headers', f'User-Agent: {user_agent}\r\nReferer: {url}\r\n',
                '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
                str(output_path)
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=600)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
                return output_path
            return None

        # Direct MP4 Download
        logging.info(f"[GENERIC-STREAM] Downloading binary stream...")
        vr = requests.get(video_url, headers=headers, proxies=proxies, stream=True, timeout=300)
        if vr.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in vr.iter_content(65536):
                    f.write(chunk)
            if output_path.exists() and output_path.stat().st_size > 1000:
                return output_path

    except Exception as e:
        logging.error(f"[GENERIC-STREAM] Critical failure: {e}")
    
    return None


def _run_ytdlp_extract(ydl_opts: Dict, url: str) -> Tuple[Dict, str]:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        prepared_name = ydl.prepare_filename(info)
    return info, prepared_name

def _select_best_downloaded_file(files: List[Path]) -> Path:
    if not files:
        raise ValueError("Download failed: file not found")

    video_exts = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi", ".flv", ".ts", ".unknown_video"}
    candidates = [f for f in files if f.suffix.lower() in video_exts]
    if not candidates:
        candidates = files

    def size_or_zero(path: Path) -> int:
        try:
            return path.stat().st_size
        except Exception:
            return 0

    return max(candidates, key=size_or_zero)

def _cleanup_extra_files(files: List[Path], keep: Path) -> None:
    for path in files:
        if path == keep:
            continue
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

# === Основная логика ===

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None, min_duration: int = 0, **kwargs) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    # Clean URL from trailing slashes/backslashes and whitespace
    url = url.strip().rstrip('\\/')
    logging.info(f"Using yt-dlp version: {yt_dlp.version.__version__}")

    status_task = None
    if progress_callback:
        current_funny = random.choice(FUNNY_STATUSES)

        async def wrapped_callback(text: str = ""):
            display_text = f"🎬 {current_funny}"
            try:
                await progress_callback(display_text)
            except Exception:
                pass

        async def status_cycler():
            nonlocal current_funny
            while True:
                try:
                    await asyncio.sleep(6)
                    current_funny = random.choice(FUNNY_STATUSES)
                    await wrapped_callback()
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(6)

        status_task = asyncio.create_task(status_cycler())
        # Show first status immediately
        await wrapped_callback()



    async def maybe_add_instagram_audio(files: List[Path]) -> List[Path]:
        if not cobalt_client:
            return files
        try:
            audio_path, _, _ = await cobalt_client.download_media(
                url=url,
                quality="1080",
                is_audio=True,
                progress_callback=wrapped_callback if progress_callback else None
            )
            if audio_path:
                if isinstance(audio_path, list):
                    return files + audio_path
                return files + [audio_path]
        except Exception as audio_error:
            logging.error(f"[COBALT] ❌ Error (Instagram audio): {audio_error}")
        return files
    
    async def wrapped_callback(current):
        if progress_callback:
            await progress_callback(current)

    # Resolve Threads normalization: threads.com -> threads.net
    if "threads.com" in url:
        url = url.replace("threads.com", "threads.net")
        logging.info(f"Normalized Threads URL to: {url}")

    # Resolve music searches normalization: scsearch -> ytsearch
    if url.startswith("scsearch"):
        url = url.replace("scsearch", "ytmcustomsearch:ytsearch", 1)
        logging.info(f"Replaced SoundCloud search with YT Music search: {url}")

    # Resolve ytmusicsearch scheme issue
    if url.startswith("ytmusicsearch"):
        # Convert ytmusicsearch1:query to ytmcustomsearch:ytsearch1:query
        # or simply ytmcustomsearch:query and let it use default_search
        url = url.replace("ytmusicsearch", "ytmcustomsearch:ytsearch", 1)
        logging.info(f"Fixed YT Music search scheme: {url}")

    # Resolve short URLs to detect slideshows and help yt-dlp
    if "vm.tiktok.com" in url or "vt.tiktok.com" in url or "/t/" in url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True, timeout=5) as resp:
                    url = str(resp.url)
        except Exception as e:
            logging.warning(f"Failed to resolve TikTok URL: {e}")
    
    # Resolve Reddit short URLs (reddit.com/r/.../s/...) to full URLs using proxy
    if "reddit.com" in url and "/s/" in url:
        try:
            resolved_url = await asyncio.to_thread(unshorten_reddit_url, url, SOCKS_PROXY)
            if resolved_url != url:
                logging.info(f"✅ Resolved Reddit URL to: {resolved_url}")
            url = resolved_url
        except Exception as e:
            logging.warning(f"Failed to resolve Reddit short URL via proxy: {e}")

    # Resolve Facebook share URLs to canonical /reel/ID format before passing to yt-dlp
    if ("facebook.com/share" in url or "fb.watch" in url) and "facebook.com/reel" not in url:
        try:
            resolved_fb = await asyncio.to_thread(resolve_facebook_share_url, url)
            if resolved_fb != url:
                url = resolved_fb
            else:
                logging.warning("[FB] Could not resolve share URL; yt-dlp will try anyway")
        except Exception as e:
            logging.warning(f"Failed to resolve Facebook share URL: {e}")

    platform = get_platform(url)

    # Strip query parameters (they often confuse extractors or contain tracking)
    # Exclude platforms that need query params: youtube, pornhub (viewkey)
    if '?' in url and platform not in ("youtube", "pornhub"):
        url = url.split('?')[0]
    
    # Check for playlists first
    if is_playlist(url) and (platform == "youtube" or is_youtube_music(url)):
        on_track = kwargs.get('on_track_callback')
        logging.info(f"Downloading playlist: {url}")
        return await _download_playlist_ytdlp(url, is_music=is_music, progress_callback=wrapped_callback if progress_callback else None, on_track_callback=on_track)
    
    # === МЕТОД 1: YT-DLP (основной) ===
    ytdlp_error = None
    try:
        logging.info(f"[YT-DLP] Attempting download: {url}")
        
        # TikTok через специальный метод
        if platform == "tiktok":
            # Start fetching metadata/verification in parallel with download
            enrich_task = asyncio.create_task(asyncio.to_thread(fetch_tiktok_metadata, url))
            
            # Always use tiktok_local first
            res = await _download_local_tiktok(url, progress_callback=wrapped_callback if progress_callback else None)
            
            # Enrich metadata with verification for TikTok ALWAYS
            if res and len(res) == 3:
                files, thumb, meta = res
                
                # Post-process for thumbnails and dimensions if needed
                if isinstance(files, Path) and files.exists():
                    video_file = files
                    # Always generate thumbnail if missing
                    if not thumb or not thumb.exists():
                        new_thumb = DOWNLOADS_DIR / f"{video_file.stem}_thumb.jpg"
                        if generate_video_thumbnail(video_file, new_thumb):
                            thumb = new_thumb
                            res = (video_file, thumb, meta)
                    
                    # Ensure dimensions are present
                    if not meta.get('width') or not meta.get('height'):
                        w, h = probe_video_dimensions(video_file)
                        if w > 0:
                            meta['width'] = w
                            meta['height'] = h

                # Await the enrichment task that was running in parallel
                try:
                    enrich_meta = await enrich_task
                    if enrich_meta.get('verified'):
                        meta['verified'] = True
                        logging.info(f"✅ Verified status enriched for {url} (parallel)")
                    if enrich_meta.get('uploader') and (not meta.get('uploader') or meta.get('uploader') == 'Unknown'):
                        meta['uploader'] = enrich_meta['uploader']
                except Exception as e:
                    logging.warning(f"Failed to enrich verification for TikTok: {e}")
                
            return res
        
        # Spotify через song.link + yt-dlp (reliable) или spotdl (fallback)
        if platform == "spotify":
            try:
                # Try to resolve to YT Music first for higher reliability
                resolved_url = await _resolve_spotify_via_songlink(url)
                if resolved_url:
                    logging.info(f"[SPOTIFY] Resolved {url} to {resolved_url}")
                    return await _download_local_ytdlp(resolved_url, is_music=True, progress_callback=wrapped_callback if progress_callback else None)
                
                logging.info(f"[SPOTIFY] Attempting spotdl: {url}")
                return await _download_spotify_spotdl(url, progress_callback=wrapped_callback if progress_callback else None)
            except Exception as spot_err:
                logging.error(f"[SPOTIFY] ❌ Failed: {spot_err}")
                # Fallback continues to search mode in yt-dlp
        
        # YouTube/Instagram/музыка через универсальный метод
        return await _download_local_ytdlp(url, is_music, video_height=video_height, min_duration=min_duration, progress_callback=wrapped_callback if progress_callback else None)
        
    except Exception as e:
        ytdlp_error = str(e)
        logging.warning(f"[YT-DLP] ❌ Failed: {ytdlp_error}")
        
        # If Instagram photo-only post, go straight to Cobalt fallback
        if platform == "instagram" and cobalt_client and ytdlp_error and "There is no video in this post" in ytdlp_error:
            try:
                logging.info(f"[COBALT] Instagram fallback after photo-only error: {url}")
                file_path, thumb_path, metadata = await cobalt_client.download_media(
                    url=url,
                    quality="1080",
                    is_audio=is_music,
                    progress_callback=wrapped_callback if progress_callback else None
                )
                if file_path:
                    if isinstance(file_path, list):
                        logging.info(f"[COBALT] ✅ Success: {len(file_path)} files")
                        file_path = await maybe_add_instagram_audio(file_path)
                        return file_path, thumb_path, metadata
                    if file_path.exists():
                        logging.info(f"[COBALT] ✅ Success: {file_path.name}")
                        return file_path, thumb_path, metadata
                logging.warning("[COBALT] ⚠️ No file returned")
            except Exception as cobalt_error:
                logging.error(f"[COBALT] ❌ Error (Instagram-photo fallback): {cobalt_error}")

        # === МЕТОД 1.5: YT-DLP С ПРОКСИ (fallback если есть прокси) ===
        if SOCKS_PROXY and ytdlp_error:
            try:
                logging.info(f"[YT-DLP+PROXY] Attempting with SOCKS proxy")
                
                # TikTok через специальный метод с прокси
                if platform == "tiktok":
                    return await _download_local_tiktok(url, use_proxy=True, progress_callback=wrapped_callback if progress_callback else None)
                
                # YouTube/Instagram/музыка с прокси
                return await _download_local_ytdlp(url, is_music, video_height=video_height, use_proxy=True, progress_callback=wrapped_callback if progress_callback else None)
                
            except Exception as proxy_error:
                logging.warning(f"[YT-DLP+PROXY] ❌ Failed: {proxy_error}")
                # Silent fallback to method 2 (Cobalt)
        
        # === МЕТОД 2: COBALT API (fallback) ===
        if cobalt_client:
            try:
                logging.info(f"[COBALT] Attempting download: {url}")
                file_path, thumb_path, metadata = await cobalt_client.download_media(
                    url=url,
                    quality="1080",
                    is_audio=is_music,
                    progress_callback=wrapped_callback if progress_callback else None
                )
                if file_path:
                    if isinstance(file_path, list):
                        logging.info(f"[COBALT] ✅ Success: {len(file_path)} files")
                        return file_path, thumb_path, metadata
                    if file_path.exists():
                        logging.info(f"[COBALT] ✅ Success: {file_path.name}")
                        return file_path, thumb_path, metadata
                else:
                    logging.warning("[COBALT] ⚠️ No file returned")
            except Exception as cobalt_error:
                logging.error(f"[COBALT] ❌ Error: {cobalt_error}")
        
        # === МЕТОД 3: TIKWM (только для TikTok) ===
        if platform == "tiktok":
            try:
                logging.info("[TIKWM] Attempting download...")
                return await _download_tiktok_tikwm(url)
            except Exception as tikwm_error:
                logging.error(f"[TIKWM] ❌ Failed: {tikwm_error}")

        # === МЕТОД 4: REDDIT DIRECT (fallback for Reddit 429/auth errors) ===
        if platform == "reddit":
            try:
                logging.info(f"[REDDIT-DIRECT] Trying direct JSON API download: {url}")
                reddit_file = await asyncio.to_thread(_download_reddit_direct, url, SOCKS_PROXY)
                if reddit_file and reddit_file.exists():
                    logging.info(f"[REDDIT-DIRECT] ✅ Success: {reddit_file.name}")
                    # Generate thumbnail + probe dimensions
                    w, h = probe_video_dimensions(reddit_file)
                    thumb_path = DOWNLOADS_DIR / f"{reddit_file.stem}_thumb.jpg"
                    if not generate_video_thumbnail(reddit_file, thumb_path):
                        thumb_path = None
                    meta = {
                        'title': None,
                        'uploader': None,
                        'webpage_url': url,
                        'duration': 0,
                        'width': w,
                        'height': h,
                        'verified': False,
                    }
                    return reddit_file, thumb_path, meta
            except Exception as reddit_direct_error:
                logging.error(f"[REDDIT-DIRECT] ❌ Failed: {reddit_direct_error}")

        # === МЕТОД 5: FACEBOOK DIRECT SCRAPE ===
        if platform == "facebook":
            try:
                logging.info(f"[FB-DIRECT] Trying HTML scrape fallback: {url}")
                fb_file = await asyncio.to_thread(_download_facebook_direct, url, SOCKS_PROXY)
                if fb_file and fb_file.exists():
                    logging.info(f"[FB-DIRECT] ✅ Success: {fb_file.name}")
                    w, h = probe_video_dimensions(fb_file)
                    fb_thumb = DOWNLOADS_DIR / f"{fb_file.stem}_thumb.jpg"
                    if not generate_video_thumbnail(fb_file, fb_thumb):
                        fb_thumb = None
                    return fb_file, fb_thumb, {
                        'title': None, 'uploader': None,
                        'webpage_url': url, 'duration': 0,
                        'width': int(w), 'height': int(h), 'verified': False,
                    }
            except Exception as fb_err:
                logging.error(f"[FB-DIRECT] ❌ Failed: {fb_err}")

        # === МЕТОД 6: GENERIC VIDEO STREAM SCRAPE (Last resort) ===
        if platform == "video" or ytdlp_error:
            try:
                logging.info(f"[GENERIC-STREAM] Trying manual stream extraction: {url}")
                stream_file = await asyncio.to_thread(_download_generic_stream, url, SOCKS_PROXY)
                if stream_file and stream_file.exists():
                    logging.info(f"[GENERIC-STREAM] ✅ Success: {stream_file.name}")
                    w, h = probe_video_dimensions(stream_file)
                    gen_thumb = DOWNLOADS_DIR / f"{stream_file.stem}_thumb.jpg"
                    if not generate_video_thumbnail(stream_file, gen_thumb):
                        gen_thumb = None
                    return stream_file, gen_thumb, {
                        'title': 'Downloaded Video', 'uploader': None,
                        'webpage_url': url, 'duration': 0,
                        'width': int(w), 'height': int(h), 'verified': False,
                    }
            except Exception as gen_err:
                logging.error(f"[GENERIC-STREAM] ❌ Failed: {gen_err}")

        ai_autofix_attempted = False
        ai_autofix_result = None

        if should_attempt_ai_autofix(url, str(ytdlp_error)):
            ai_autofix_attempted = True
            try:
                if progress_callback:
                    await wrapped_callback("🤖 AI bot is autonomously applying extractor patches now. A retry will follow automatically if successful.")
                logging.info(f"[AI-AUTOFIX] Attempting Groq-based extractor fix for: {url}")
                ai_autofix_result = await asyncio.to_thread(run_ai_extractor_autofix, url, str(ytdlp_error))
                if ai_autofix_result and ai_autofix_result.get("success"):
                    if progress_callback:
                        await wrapped_callback("🤖 Autonomous extractor patch applied. Retrying download...")
                    logging.info(f"[AI-AUTOFIX] ✅ Module applied: {ai_autofix_result.get('filename')}")
                    return await _download_local_ytdlp(
                        url,
                        is_music,
                        video_height=video_height,
                        min_duration=min_duration,
                        progress_callback=wrapped_callback if progress_callback else None,
                    )
            except Exception as ai_err:
                logging.error(f"[AI-AUTOFIX] ❌ Unexpected failure: {ai_err}")

        # Все методы провалились
        error_msg = str(ytdlp_error) if ytdlp_error else "Unknown error"
        if "blocked in your area" in error_msg or "Viewing restrictions" in error_msg:
            raise Exception(f"Video is blocked in the server's region. Try using a proxy or a different link. (Error: {error_msg})")
        elif "login required" in error_msg.lower() and platform == "instagram":
            raise Exception("Instagram requires new cookies. Please contact the administrator to update cookies.txt.")

        if ai_autofix_attempted:
            ai_reason = (ai_autofix_result or {}).get("reason", "autofix_not_applied")
            raise Exception(
                f"All download methods failed. YT-DLP error: {ytdlp_error}\n"
                f"AI-AUTOFIX-ATTEMPTED: AI bot attempted extractor recovery, but this request still failed "
                f"(reason: {ai_reason})."
            )

        raise Exception(f"All download methods failed. YT-DLP error: {ytdlp_error}")
    finally:
        if status_task:
            status_task.cancel()

async def _download_local_ytdlp(url: str, is_music: bool = False, video_height: int = None, use_proxy: bool = False, min_duration: int = 0, progress_callback: Callable = None, skip_cleanup: bool = False, attempt: int = 1) -> Tuple[Path, Optional[Path], Dict]:
    """Универсальный метод для YouTube/Instagram/музыки через yt-dlp с retry на 403"""
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOADS_DIR / f"%(title).50s_%(id)s_{unique_id}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"

    is_reddit = "reddit.com" in url or "redd.it" in url

    ytm_custom_query = None
    if url.startswith("ytmcustomsearch:"):
        ytm_custom_query = url.replace("ytmcustomsearch:", "", 1)
        url = ytm_custom_query
        
    is_youtube = "youtube.com" in url or "youtu.be" in url or ytm_custom_query is not None
    is_instagram = "instagram.com" in url
    user_agent = USER_AGENTS[0]
    use_impersonate = True
    
    try:
        impersonate_target = IMPERSONATE_TARGETS[0]
        is_facebook = "facebook.com" in url or "fb.watch" in url
        if is_facebook:
            impersonate_target = 'chrome-99'
        
        ydl_opts = {
            'outtmpl': output_template,
            'cookiefile': str(cookie_file) if cookie_file.exists() and cookie_file.is_file() and cookie_file.stat().st_size > 0 else None,
            'noplaylist': True,
            'quiet': False,
            'verbose': True,
            'legacy_server_connect': True,
            'socket_timeout': 60,
            'retries': 5,
            'fragment_retries': 5,
            'low_speed_limit': 0,
            'low_speed_time': 300,
            'playlist_items': '1' if is_youtube else '1-5',
            'max_filesize': 2048 * 1024 * 1024,
            'exec_before_download': [],
            'extractor_args': {
                'reddit': {'impersonate': True}
            },
            'js_runtimes': {
                'node': {'path': '/usr/local/bin/node'}
            },
            'remote_components': ['ejs:github'],
            'plugin_dirs': get_plugin_dirs(),
            'postprocessor_args': {
                'ffmpeg': ['-movflags', '+faststart']
            },
            'fixup': 'detect_or_warn',
            'concurrent_fragment_downloads': 1, # Avoid thread safety issues with curl_cffi
            'hls_prefer_native': True,          # Use native downloader for HLS where possible
        }
        if ytm_custom_query:
            ydl_opts['default_search'] = 'https://music.youtube.com/search?q='

        if min_duration > 0:
            def duration_filter(info_dict, *, incomplete):
                duration = info_dict.get('duration')
                if duration and duration < min_duration:
                    return f'Duration {duration}s is shorter than {min_duration}s'
                return None
            ydl_opts['match_filter'] = duration_filter
        
        ydl_opts['progress_hooks'] = []
        browser_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Chromium";v="120", "Google Chrome";v="120", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': user_agent,
        }
        if is_facebook:
            browser_headers['Sec-Ch-Ua'] = '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"'
            browser_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'
        ydl_opts['http_headers'] = browser_headers
        
        if use_impersonate:
            try:
                target_obj = build_impersonate_target(impersonate_target)
                if ImpersonateTarget and isinstance(target_obj, ImpersonateTarget):
                    ydl_opts['impersonate'] = target_obj
                    logging.info(f"🔒 Attempting TLS impersonation: {impersonate_target}")
                else:
                    use_impersonate = False
            except Exception as imp_err:
                logging.error(f"❌ Failed to set impersonate: {imp_err}")
                use_impersonate = False
        
        if is_instagram:
            ydl_opts['noplaylist'] = False
            ydl_opts['extractor_args']['instagram'] = {'include_videos': True, 'include_pictures': True}
            # Strongly prefer H.264/AVC for Instagram to avoid VP9 compatibility/resource issues
            ydl_opts['format_sort'] = ['vcodec:h264', 'res', 'fps']
        
        ydl_opts['proxy'] = SOCKS_PROXY if use_proxy and SOCKS_PROXY else ''
        
        if is_music:
            ydl_opts['format'] = 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}]
        elif is_instagram:
            # Prefer AVC/H.264 entries, then fallback to anything best
            ydl_opts['format'] = 'bestvideo[vcodec^=avc]+bestaudio/bestvideo[vcodec^=h264]+bestaudio/best[vcodec^=avc]/best[vcodec^=h264]/bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
        else:
            ydl_opts['merge_output_format'] = 'mp4'
            # Also prefer H.264 for general videos to ensure compatibility
            ydl_opts['format_sort'] = ['vcodec:h264', 'res', 'fps']
            if video_height:
                ydl_opts['format'] = f"bestvideo[vcodec^=avc][height<={video_height}]+bestaudio/bestvideo[vcodec^=h264][height<={video_height}]+bestaudio/best[vcodec^=avc][height<={video_height}]/best[vcodec^=h264][height<={video_height}]/bestvideo[height<={video_height}]+bestaudio/best[height<={video_height}]"
            else:
                ydl_opts['format'] = 'bestvideo[vcodec^=avc]+bestaudio/bestvideo[vcodec^=h264]+bestaudio/best[vcodec^=avc]/best[vcodec^=h264]/bestvideo+bestaudio/best'
        
        info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)

        metadata = {
            'title': None if info.get('title') in ('Unknown', 'None') else info.get('title', 'Media'),
            'uploader': None if info.get('uploader') in ('Unknown', 'None') else info.get('uploader'),
            'webpage_url': info.get('webpage_url', url),
            'duration': info.get('duration', 0),
            'width': info.get('width', 0),
            'height': info.get('height', 0),
            'verified': info.get('creator_is_verified') or info.get('uploader_is_verified') or info.get('verified') or False,
        }
        
        downloaded_files = list(DOWNLOADS_DIR.glob(f"*{unique_id}*"))
        if not downloaded_files:
            path = Path(prepared_name)
            if path.exists(): downloaded_files = [path]
            else: raise ValueError("Download failed: file not found")

        if is_instagram and info.get("entries"):
            downloaded_files.sort(key=lambda p: p.name)
            return downloaded_files, None, metadata

        file_path = _select_best_downloaded_file(downloaded_files)
        if not skip_cleanup: _cleanup_extra_files(downloaded_files, file_path)
        
        # --- IPHONE COMPATIBILITY CHECK ---
        # If video is VP9 or AV1, convert it to H.264 for iPhone support
        if not is_music and file_path.suffix.lower() in ('.mp4', '.webm', '.mkv'):
            codec = await asyncio.to_thread(probe_video_codec, file_path)
            if codec in ('vp9', 'av1'):
                file_path = await asyncio.to_thread(convert_video_to_h264, file_path)
        # ----------------------------------

        if file_path.suffix == '.unknown_video':
            if file_path.stat().st_size < 500 * 1024:
                file_path.unlink()
                raise ValueError("File too small.")
            new_path = file_path.with_suffix('.mp4')
            file_path.rename(new_path)
            file_path = new_path
        
        final_thumbnail = None
        if not is_music:
            if not metadata.get('width') or not metadata.get('height'):
                w, h = probe_video_dimensions(file_path)
                metadata['width'], metadata['height'] = w, h
            thumbnail_path = DOWNLOADS_DIR / f"{file_path.stem}_thumb.jpg"
            if generate_video_thumbnail(file_path, thumbnail_path): final_thumbnail = thumbnail_path

        return file_path, final_thumbnail, metadata
                    
    except Exception as e:
        # Retry once if we hit the curl_cffi shutdown error
        if "cannot schedule new futures after shutdown" in str(e) and attempt == 1:
            logging.warning("⚠️ curl_cffi shutdown error detected. Retrying download once...")
            attempt = 2
            # Wait a moment for things to settle
            await asyncio.sleep(2)
            # Recursively call with attempt 2
            return await _download_local_ytdlp(url, is_music, video_height, use_proxy, min_duration, progress_callback, skip_cleanup, attempt=2)
            
        logging.error(f"YT-DLP critical error: {str(e)[:200]}")
        raise e
    
    # All attempts failed with 403/429
    raise last_error if last_error else Exception("All user-agent attempts failed")



async def _download_local_tiktok(url: str, use_proxy: bool = False, progress_callback: Callable = None) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    """Скачивание TikTok на VPS. Поддерживает видео (h264) и фото-слайдшоу."""
    
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOADS_DIR / f"%(title).50s_%(id)s_{unique_id}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"
    
    # Check for slideshow (images)
    is_slideshow = "/photo/" in url
    
    ydl_opts_base = {
        'outtmpl': output_template,
        'cookiefile': str(cookie_file) if cookie_file.exists() and cookie_file.is_file() and cookie_file.stat().st_size > 0 else None,
        'noplaylist': True,
        'quiet': False,
        'verbose': True,
        'http_headers': {
            'User-Agent': random.choice(USER_AGENTS),
        },
        'extractor_args': {
            'tiktok': {
                'app_name': ['tiktok_web'],
                'app_version': [''],
            }
        },
        'plugin_dirs': get_plugin_dirs(),
        'fixup': 'detect_or_warn',
        'postprocessor_args': {
            'ffmpeg': ['-movflags', '+faststart']
        },
        # Не указываем target явно — yt-dlp сам выберет доступный на ARM64
    }
    
    # Добавляем или ПРИНУДИТЕЛЬНО ОТКЛЮЧАЕМ прокси
    if use_proxy and SOCKS_PROXY:
        ydl_opts_base['proxy'] = SOCKS_PROXY
    else:
        # Принудительно отключаем прокси (пустая строка перебивает ENV переменные)
        ydl_opts_base['proxy'] = ''
    
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
             if progress_callback:
                 loop = asyncio.get_running_loop()
                 last_update = 0
                 def ytdlp_hook(d):
                     nonlocal last_update
                     if d['status'] == 'downloading':
                         now = time.time()
                         if now - last_update < 1:  # Throttle updates to 1 per second
                             return
                         
                         p = d.get('_percent_str', '').replace('%','')
                         s = d.get('_speed_str', '')
                         t = d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', ''))
                         if p and s:
                             last_update = now
                             asyncio.run_coroutine_threadsafe(progress_callback(f"{p}% of {t} at {s}"), loop)
                 ydl_opts_base['progress_hooks'] = [ytdlp_hook]
             
             ydl_opts = ydl_opts_base.copy()
    else:
        # Strict legacy codec check for videos
        ydl_opts = ydl_opts_base.copy()
        ydl_opts['format'] = 'best[vcodec^=h264]/best[vcodec^=avc]'

    info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)

    metadata = {
        'title': None if info.get('title') == 'Unknown' or info.get('title') == 'None' else info.get('title', 'TikTok Media'),
        'uploader': None if info.get('uploader') == 'Unknown' or info.get('uploader') == 'None' else info.get('uploader'),
        'webpage_url': info.get('webpage_url', url),
        'duration': info.get('duration', 0),
        'width': info.get('width', 0),
        'height': info.get('height', 0),
        'verified': info.get('creator_is_verified') or info.get('uploader_is_verified') or info.get('verified') or False,
    }
    
    # Check description for 'Unknown' as well
    if info.get('description') == 'Unknown' or info.get('description') == 'None':
        metadata['description'] = None
    else:
        metadata['description'] = info.get('description')

    # Determine downloaded files
    # We search by unique_id to catch all files (images, mp3, mp4)
    downloaded_files = list(DOWNLOADS_DIR.glob(f"*{unique_id}*"))

    if not downloaded_files:
        # Fallback to prepare_filename
        path = Path(prepared_name)
        if path.exists():
            downloaded_files = [path]
        else:
             raise ValueError("Download failed: file not found")

    if is_slideshow:
        return downloaded_files, None, metadata
    
    # Video handling - проверяем кодек, только H264 разрешён для yt-dlp
    video_files = [f for f in downloaded_files if f.suffix in ['.mp4', '.mov']]
    if video_files:
        path = _select_best_downloaded_file(video_files)
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
        
    selected_path = _select_best_downloaded_file(downloaded_files)
    if not skip_cleanup:
        _cleanup_extra_files(downloaded_files, selected_path)
    return selected_path, None, metadata


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
    
    # Add a small delay for TikWM free tier limit (1 req/sec)
    await asyncio.sleep(1.5)
    
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
    author = result.get('author', {}).get('unique_id')
    title = result.get('title')
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
    
    # Enrich metadata with verification status (requires extra API call)
    verified = False
    try:
        temp_meta = await asyncio.to_thread(fetch_tiktok_metadata, url)
        verified = temp_meta.get('verified', False)
        # Use uploader from fetch_tiktok_metadata if tikwm main API missed it
        if (not author or author == 'Unknown' or author == 'None') and temp_meta.get('uploader'):
            author = temp_meta['uploader']
    except Exception as e:
        logging.warning(f"Failed to fetch verification status in _download_tiktok_tikwm: {e}")

    metadata = {
        'title': None if title == 'Unknown' or title == 'None' else title,
        'uploader': None if author == 'Unknown' or author == 'None' else author,
        'webpage_url': url,
        'duration': duration,
        'verified': verified,
        'ext': 'mp4'
    }
    
    return video_path, thumbnail_path, metadata

async def _download_playlist_ytdlp(url: str, is_music: bool = True, progress_callback: Optional[Callable] = None, on_track_callback: Optional[Callable] = None) -> List[Tuple[Path, Optional[Path], dict]]:
    """Download entire playlist/album via local yt-dlp."""
    playlist_results = []
    
    ydl_opts = {
        'cookiefile': str(DATA_DIR / "cookies.txt") if (DATA_DIR / "cookies.txt").exists() else None,
        'quiet': True,
        'extract_flat': True,
        'playlist_items': '1-50', # Limit to 50 items for safety
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # We must use wait=True or similar to get entries correctly in flat mode
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            entries = info.get('entries', [])
            
            total = len(entries)
            if not entries: return []

            for i, entry in enumerate(entries, 1):
                entry_url = entry.get('url') or entry.get('webpage_url')
                if not entry_url: continue
                
                if progress_callback:
                    await progress_callback(f"⏳ Downloading track {i}/{total}...")
                
                try:
                    # WE PASS skip_cleanup=True here to preserve all files for the ZIP
                    res = await _download_local_ytdlp(entry_url, is_music=is_music, skip_cleanup=True)
                    
                    if on_track_callback:
                        # If we have a track callback (e.g. for direct sending), use it immediately
                        await on_track_callback(res, i, total)
                        # We can still add to results, BUT if on_track handled it, 
                        # maybe we don't want to keep it in memory? 
                        # For ZIP we NEED to keep it. For 'each' we can skip.
                    
                    playlist_results.append(res)
                except Exception as e:
                    logging.error(f"Error downloading playlist item {i}: {e}")
                    continue
                    
        return playlist_results
    except Exception as e:
        logging.error(f"Playlist download error: {e}")
        return []

async def _resolve_spotify_via_songlink(url: str) -> str:
    """Helper to resolve Spotify URL to YouTube Music using Odesli (song.link)."""
    import aiohttp
    try:
        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Try to find YouTube Music link
                    links = data.get('linksByPlatform', {})
                    if 'youtubeMusic' in links:
                        return links['youtubeMusic']['url']
                    if 'youtube' in links:
                        return links['youtube']['url']
    except Exception as e:
        logging.error(f"Songlink resolution failed: {e}")
    return ""

async def _download_spotify_spotdl(url: str, progress_callback: Optional[Callable] = None) -> Tuple[Path, Optional[Path], Dict]:
    """Download Spotify track using spotdl CLI."""
    unique_id = uuid.uuid4().hex[:8]
    # spotdl needs a clean working dir for temp files sometimes, but let's just use DOWNLOADS_DIR
    tmp_name = f"spotify_{unique_id}"
    
    cmd = [
        "python3", "-m", "spotdl", "download", url,
        "--output", f"{DOWNLOADS_DIR}/%(title)s - %(artist)s_{unique_id}.%(ext)s",
        "--no-cache"        # Avoid stale rate-limit headers
    ]
    
    logging.info(f"Running spotdl command: {' '.join(cmd)}")
    
    # Run the command
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        err_msg = stderr.decode().strip()
        if "rate/request limit" in err_msg or "86400" in err_msg:
             logging.warning(f"Spotify API rate limit hit! Falling back to generic download...")
             # Fallback: manually search for song via YouTube Music
             raise Exception("SPOTIFY_RATE_LIMIT")
        raise Exception(f"spotdl failed with code {process.returncode}: {err_msg}")
    
    # Find the downloaded file
    downloaded_files = list(DOWNLOADS_DIR.glob(f"*{unique_id}*"))
    if not downloaded_files:
        raise Exception("spotdl: File not found after download (search by unique_id failed)")
        
    audio_path = _select_best_downloaded_file(downloaded_files)
    
    # Meta (spotdl already embeds metadata into MP3, so we just try to read it back or guess)
    # We use mutagen if we need to be really precise, but basic guess works
    filename = audio_path.name
    try:
        title_artist = filename.split(f"_{unique_id}")[0]
        title = title_artist.split(" - ")[0]
        uploader = title_artist.split(" - ")[1] if " - " in title_artist else "Spotify"
    except:
        title, uploader = filename, "Spotify"

    meta = {
        'title': title,
        'uploader': uploader,
        'webpage_url': url,
        'duration': 0, # mutagen could fill this
        'verified': False,
    }
    
    # No extra thumbnail needed since spotdl embeds it into the MP3
    return audio_path, None, meta
