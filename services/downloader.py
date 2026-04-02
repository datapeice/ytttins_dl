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
    elif "://t.me" in url_lower or "://telegram.me" in url_lower:
        return "unknown"
    elif "https://" in url_lower or "http://" in url_lower:
        # yt-dlp supports 1800+ sites, try anyway
        return "video"
    else:
        return "unknown"

def is_youtube_music(url: str) -> bool:
    return "music.youtube.com" in url

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


def _download_reddit_direct(url: str, proxy_url: Optional[str] = None) -> Optional[Path]:
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

    try:
        post = data[0]['data']['children'][0]['data']
        media = post.get('media') or post.get('secure_media') or {}
        reddit_video = media.get('reddit_video', {})
        video_url = reddit_video.get('fallback_url') or reddit_video.get('hls_url')
        if not video_url:
            # Try crosspost
            xpost = (post.get('crosspost_parent_list') or [{}])[0]
            xmedia = xpost.get('media') or xpost.get('secure_media') or {}
            reddit_video = xmedia.get('reddit_video', {})
            video_url = reddit_video.get('fallback_url') or reddit_video.get('hls_url')
        if not video_url:
            logging.warning("[REDDIT-DIRECT] No video URL found in post JSON")
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
                r'hd_src\s*:\s*"([^"]+\.mp4[^"]*?)"',
                r'sd_src\s*:\s*"([^"]+\.mp4[^"]*?)"',
                r'"video_url"\s*:\s*"([^"]+)"',
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

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None, min_duration: int = 0) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
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
    # Exclude platforms that need query params: youtube, instagram, pornhub (viewkey)
    if '?' in url and platform not in ("youtube", "instagram", "pornhub"):
        url = url.split('?')[0]
    
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

        # Все методы провалились
        raise Exception(f"All download methods failed. YT-DLP error: {ytdlp_error}")
    finally:
        if status_task:
            status_task.cancel()

async def _download_local_ytdlp(url: str, is_music: bool = False, video_height: int = None, use_proxy: bool = False, min_duration: int = 0, progress_callback: Callable = None) -> Tuple[Path, Optional[Path], Dict]:
    """Универсальный метод для YouTube/Instagram/музыки через yt-dlp с retry на 403"""
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOADS_DIR / f"%(title).50s_%(id)s_{unique_id}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"

    is_reddit = "reddit.com" in url or "redd.it" in url
    is_youtube = "youtube.com" in url or "youtu.be" in url
    is_instagram = "instagram.com" in url
    
    # Try multiple user-agents if we get 403
    last_error = None
    for attempt, user_agent in enumerate(USER_AGENTS, 1):
        # First try with impersonate, fallback to without if it fails
        impersonate_modes = [True, False]
        if is_reddit:
            # Avoid yt-dlp impersonate on Heroku (AssertionError from ImpersonateTarget)
            impersonate_modes = [False]
        for use_impersonate in impersonate_modes:
            try:
                impersonate_target = IMPERSONATE_TARGETS[(attempt - 1) % len(IMPERSONATE_TARGETS)]
                
                # Facebook's Tahoe API fingerprints TLS — only chrome-99 works reliably
                # (yt-dlp issue #15161: chrome-110 causes "Cannot parse data")
                is_facebook = "facebook.com" in url or "fb.watch" in url
                if is_facebook and use_impersonate:
                    impersonate_target = 'chrome-99'
                
                ydl_opts = {
                    'outtmpl': output_template,
                    'cookiefile': str(cookie_file) if cookie_file.exists() and cookie_file.is_file() and cookie_file.stat().st_size > 0 else None,
                    'noplaylist': True,
                    'quiet': False,
                    'verbose': True,
                    'legacy_server_connect': True,  # GitHub: helps with old TLS configs & Cloudflare
                    'socket_timeout': 30,  # Prevent hanging on slow/blocked connections
                    'retries': 3,  # Retry failed fragments
                    'fragment_retries': 3,  # Retry failed fragments
                    'playlist_items': '1' if is_youtube else '1-5',  # Try multiple embeds for generic sites
                    'noplaylist': True,  # Skip playlists
                    'max_filesize': 2048 * 1024 * 1024,  # 2GB limit for safety (Telegram max)
                    'external_downloader': 'aria2c',
                    'external_downloader_args': ['--max-connection-per-server=4', '--split=4', '--min-split-size=1M'],
                    'exec_before_download': [],  # Prevent PhantomJS usage
                    'extractor_args': {
                        'pornhub': {
                            'no_js': True  # Try without JS first
                        }
                    },
                    'js_runtimes': {
                        'node': {'path': '/usr/local/bin/node'}
                    },
                    'remote_components': ['ejs:github'],
                    'fixup': 'never',  # Skip redundant container fixups
                }

                if min_duration > 0:
                    def duration_filter(info_dict, *, incomplete):
                        duration = info_dict.get('duration')
                        if duration and duration < min_duration:
                            return f'Duration {duration}s is shorter than {min_duration}s'
                        return None
                    ydl_opts['match_filter'] = duration_filter
                
                # No progress_hooks used here anymore to keep UI clean
                ydl_opts['progress_hooks'] = []
                
                # Расширенные HTTP-заголовки для имитации браузера
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
                # Facebook: use headers matching Chrome 99 to be consistent with impersonate target
                if is_facebook and use_impersonate:
                    browser_headers['Sec-Ch-Ua'] = '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"'
                    browser_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'
                ydl_opts['http_headers'] = browser_headers
                
                # Имитация TLS-отпечатка браузера через curl-cffi (если поддерживается)
                if use_impersonate:
                    try:
                        target_obj = build_impersonate_target(impersonate_target)
                        if ImpersonateTarget and not isinstance(target_obj, ImpersonateTarget):
                            logging.warning(
                                f"⚠️ Impersonate target not supported on this runtime: {impersonate_target}"
                            )
                            use_impersonate = False
                        else:
                            ydl_opts['impersonate'] = target_obj
                            logging.info(f"🔒 Attempting TLS impersonation: {impersonate_target} + User-Agent: {user_agent[:50]}...")
                    except Exception as imp_err:
                        logging.error(f"❌ Failed to set impersonate={impersonate_target}: {imp_err}")
                        # Don't retry with impersonate if setting fails
                        use_impersonate = False
                
                # Reddit-specific configuration to avoid blocks
                if "reddit.com" in url or "redd.it" in url:
                    ydl_opts['extractor_args'] = {
                        'reddit': {
                            'user_agent': user_agent
                        }
                    }

                if is_instagram:
                    ydl_opts['noplaylist'] = False
                    ydl_opts['extractor_args'] = {
                        'instagram': {
                            'include_videos': True,
                            'include_pictures': True,
                        }
                    }
                
                # Добавляем или ПРИНУДИТЕЛЬНО ОТКЛЮЧАЕМ прокси
                if use_proxy and SOCKS_PROXY:
                    ydl_opts['proxy'] = SOCKS_PROXY
                else:
                    # Принудительно отключаем прокси (пустая строка перебивает ENV переменные)
                    ydl_opts['proxy'] = ''
                
                if is_music:
                    # Только аудио (приоритет форматов без конвертации для скорости)
                    ydl_opts['format'] = 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '320',
                    }]
                else:
                    ydl_opts['merge_output_format'] = 'mp4'
                    if video_height:
                        ydl_opts['format'] = f"bestvideo[height<={video_height}]+bestaudio/best[height<={video_height}]/bestvideo+bestaudio/best"
                    else:
                        # Видео с H.264 кодеком
                        ydl_opts['format'] = 'bestvideo[vcodec^=h264]+bestaudio/bestvideo[vcodec^=avc]+bestaudio/bestvideo+bestaudio/best[vcodec^=h264]/best[vcodec^=avc]/best'
                
                # Add progress hook to log to console (so user sees life in docker logs)
                last_logged_percent = -1
                def console_progress_hook(d):
                    nonlocal last_logged_percent
                    if d['status'] == 'downloading':
                        try:
                            p_str = d.get('_percent_str', '0%').replace('%','').strip()
                            p = int(float(p_str))
                            if p >= last_logged_percent + 2:
                                last_logged_percent = (p // 2) * 2
                                logging.info(f"[YT-DLP] Download progress: {p}% ({d.get('_speed_str', 'N/A')})")
                        except: pass
                
                ydl_opts['progress_hooks'] = [console_progress_hook]
                
                try:
                    info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)
                except Exception as extract_error:
                    error_text = str(extract_error)
                    if "Requested format is not available" in error_text:
                        ydl_opts['format'] = 'bestvideo+bestaudio/best'
                        ydl_opts.pop('merge_output_format', None)
                        info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)
                    else:
                        raise

                metadata = {
                    'title': None if info.get('title') == 'Unknown' or info.get('title') == 'None' else info.get('title', 'Media'),
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

                # Находим скачанный файл
                downloaded_files = list(DOWNLOADS_DIR.glob(f"*{unique_id}*"))

                if not downloaded_files:
                    path = Path(prepared_name)
                    if path.exists():
                        downloaded_files = [path]
                    else:
                        raise ValueError("Download failed: file not found")

                if is_instagram and info.get("entries"):
                    downloaded_files.sort(key=lambda p: p.name)
                    return downloaded_files, None, metadata

                file_path = _select_best_downloaded_file(downloaded_files)
                _cleanup_extra_files(downloaded_files, file_path)
                
                if file_path.suffix == '.unknown_video':
                    fsize = file_path.stat().st_size
                    if fsize < 500 * 1024: # Less than 500KB - likely a placeholder/error page
                        file_path.unlink()
                        raise ValueError(f"Downloaded file is too small ({fsize/1024:.1f}KB) and has unknown format.")
                    else:
                        logging.info(f"Allowing .unknown_video file due to significant size: {fsize/1024/1024:.1f}MB")
                        # Rename it to .mp4 so Telegram shows it correctly
                        new_path = file_path.with_suffix('.mp4')
                        try:
                            file_path.rename(new_path)
                            file_path = new_path
                            logging.info(f"Renamed .unknown_video to {file_path.name} for better Telegram compatibility")
                        except Exception as rename_err:
                            logging.error(f"Failed to rename .unknown_video: {rename_err}")
                
                logging.info(f"Downloaded: {file_path.name}")
                
                # Generate thumbnail if missing and mandatory probe for dimensions
                final_thumbnail = None
                if not is_music:
                    if not metadata.get('width') or not metadata.get('height'):
                        w, h = probe_video_dimensions(file_path)
                        metadata['width'] = w
                        metadata['height'] = h
                    
                    thumbnail_path = DOWNLOADS_DIR / f"{file_path.stem}_thumb.jpg"
                    if generate_video_thumbnail(file_path, thumbnail_path):
                        final_thumbnail = thumbnail_path

                if use_impersonate and attempt > 1:
                    logging.info(f"✅ Success with user-agent {attempt}/{len(USER_AGENTS)} + impersonate={impersonate_target}")
                elif not use_impersonate:
                    logging.info(f"✅ Success without impersonate (attempt {attempt}/{len(USER_AGENTS)})")

                return file_path, final_thumbnail, metadata
                    
            except Exception as e:
                error_str = str(e)
                error_type = type(e).__name__
                
                # Detailed diagnostics for AssertionError (curl_cffi issue)
                if isinstance(e, AssertionError):
                    import traceback
                    tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
                    tb_str = ''.join(tb_lines[-5:])  # Last 5 lines
                    logging.error(f"❌ AssertionError in yt-dlp (curl_cffi failure):")
                    logging.error(f"   Target: {impersonate_target if use_impersonate else 'none'}")
                    logging.error(f"   Message: {error_str if error_str else '(empty)'}")
                    logging.error(f"   Traceback (last 5 lines):\n{tb_str}")
                
                # If impersonate failed, try without it
                if use_impersonate and (not error_str or "impersonate" in error_str.lower() or error_type == "AssertionError"):
                    logging.warning(f"⚠️ Impersonate failed ({error_type}): {error_str[:100] if error_str else 'empty'}")
                    logging.info(f"Retrying attempt {attempt} without TLS impersonation...")
                    continue
                
                # Check if it's a 403 error
                if "403" in error_str or "Blocked" in error_str or "Forbidden" in error_str:
                    logging.warning(f"Attempt {attempt}/{len(USER_AGENTS)} failed with 403: {error_str[:150]}")
                    last_error = e
                    if attempt < len(USER_AGENTS):
                        logging.info(f"Retrying with different user-agent...")
                        break  # Break inner loop, continue outer loop

                # Check if it's a 429 rate-limit error — retry with backoff
                if "429" in error_str or "Too Many Requests" in error_str:
                    logging.warning(f"Attempt {attempt}/{len(USER_AGENTS)} failed with 429 (rate limit): {error_str[:150]}")
                    last_error = e
                    if attempt < len(USER_AGENTS):
                        sleep_secs = 2 * attempt  # 2s, 4s, 6s …
                        logging.info(f"Rate-limited — sleeping {sleep_secs}s before retry with different user-agent...")
                        await asyncio.sleep(sleep_secs)
                        break  # Break inner loop, continue outer loop

                # If not 403/429, raise immediately
                logging.error(f"YT-DLP error: {error_str[:200]}")
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
