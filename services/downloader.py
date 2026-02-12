import logging
import os
import uuid
import yt_dlp
import asyncio
import random
import aiohttp
import requests
import concurrent.futures
from pathlib import Path
from typing import Tuple, Dict, Optional, Callable, Union, List

from config import DOWNLOADS_DIR, DATA_DIR, COOKIES_CONTENT, USE_COBALT, COBALT_API_URL, SOCKS_PROXY
from database.storage import stats
from database.models import Cookie
from services.tiktok_scraper import download_tiktok_images

IS_HEROKU = bool(os.getenv("DYNO"))

# User-agents для обхода блокировок
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
]

# TLS fingerprints для curl-cffi (имитация браузеров)
# Безопасные targets, которые работают на большинстве систем
IMPERSONATE_TARGETS = [
    'chrome120',
    'chrome110',
    'chrome99',
    'edge101',
    'safari15_5',
    'safari15_3',
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
    elif "dailymotion.com" in url_lower or "dai.ly" in url_lower:
        return "dailymotion"
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
        if final_url and "/s/" in final_url:
            response = requests.get(url, proxies=proxies, headers=headers, allow_redirects=True, timeout=10)
            final_url = response.url
        if final_url and "?" in final_url:
            final_url = final_url.split("?")[0]
        return final_url or url
    except Exception as e:
        logging.warning(f"Failed to unshorten Reddit URL: {e}")
        return url

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

async def download_media(url: str, is_music: bool = False, video_height: int = None, progress_callback: Optional[Callable] = None) -> Tuple[Union[Path, List[Path]], Optional[Path], Dict]:
    logging.info(f"Using yt-dlp version: {yt_dlp.version.__version__}")

    async def maybe_add_instagram_audio(files: List[Path]) -> List[Path]:
        if not cobalt_client:
            return files
        try:
            audio_path, _, _ = await cobalt_client.download_media(
                url=url,
                quality="1080",
                is_audio=True,
                progress_callback=progress_callback
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

    platform = get_platform(url)

    # Strip query parameters (they often confuse extractors or contain tracking)
    if '?' in url and platform not in ("youtube", "instagram"):
        url = url.split('?')[0]
    
    # Показываем смешной статус сразу
    if progress_callback:
        funny_status = random.choice(FUNNY_STATUSES)
        await progress_callback(f"🎬 {funny_status}")

    # Prefer Cobalt on Heroku for Reddit (yt-dlp impersonate fails on Heroku)
    if platform == "reddit" and IS_HEROKU and cobalt_client:
        try:
            logging.info(f"[COBALT] Heroku-first attempt for Reddit: {url}")
            file_path, thumb_path, metadata = await cobalt_client.download_media(
                url=url,
                quality="1080",
                is_audio=is_music,
                progress_callback=progress_callback
            )
            if file_path:
                    if isinstance(file_path, list):
                        logging.info(f"[COBALT] ✅ Success: {len(file_path)} files")
                        return file_path, thumb_path, metadata
                    elif file_path.exists():
                        logging.info(f"[COBALT] ✅ Success: {file_path.name}")
                        return file_path, thumb_path, metadata
            logging.warning("[COBALT] ⚠️ No file returned")
        except Exception as cobalt_error:
            logging.error(f"[COBALT] ❌ Error (Heroku-first): {cobalt_error}")

    # Prefer Cobalt for Instagram photos when available
    if platform == "instagram" and cobalt_client and not is_music:
        try:
            logging.info(f"[COBALT] Instagram-first attempt: {url}")
            file_path, thumb_path, metadata = await cobalt_client.download_media(
                url=url,
                quality="1080",
                is_audio=is_music,
                progress_callback=progress_callback
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
            logging.error(f"[COBALT] ❌ Error (Instagram-first): {cobalt_error}")
    
    # === МЕТОД 1: YT-DLP (основной) ===
    ytdlp_error = None
    try:
        logging.info(f"[YT-DLP] Attempting download: {url}")
        
        # TikTok через специальный метод
        if platform == "tiktok":
            return await _download_local_tiktok(url)
        
        # YouTube/Instagram/музыка через универсальный метод
        return await _download_local_ytdlp(url, is_music, video_height=video_height)
        
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
                progress_callback=progress_callback
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
                return await _download_local_tiktok(url, use_proxy=True)
            
            # YouTube/Instagram/музыка с прокси
            return await _download_local_ytdlp(url, is_music, video_height=video_height, use_proxy=True)
            
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
    
    # Все методы провалились
    raise Exception(f"All download methods failed. YT-DLP error: {ytdlp_error}")


async def _download_local_ytdlp(url: str, is_music: bool = False, video_height: int = None, use_proxy: bool = False) -> Tuple[Path, Optional[Path], Dict]:
    """Универсальный метод для YouTube/Instagram/музыки через yt-dlp с retry на 403"""
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOADS_DIR / f"%(title)s_%(id)s_{unique_id}.%(ext)s")
    cookie_file = DATA_DIR / "cookies.txt"

    is_reddit = "reddit.com" in url or "redd.it" in url
    is_youtube = "youtube.com" in url or "youtu.be" in url
    is_instagram = "instagram.com" in url
    
    # Try multiple user-agents if we get 403
    last_error = None
    for attempt, user_agent in enumerate(USER_AGENTS, 1):
        # First try with impersonate, fallback to without if it fails
        impersonate_modes = [True, False]
        if is_reddit and IS_HEROKU:
            # Avoid yt-dlp impersonate on Heroku (AssertionError from ImpersonateTarget)
            impersonate_modes = [False]
        for use_impersonate in impersonate_modes:
            try:
                impersonate_target = IMPERSONATE_TARGETS[(attempt - 1) % len(IMPERSONATE_TARGETS)]
                
                ydl_opts = {
                    'outtmpl': output_template,
                    'cookiefile': cookie_file if cookie_file.exists() else None,
                    'noplaylist': True,
                    'quiet': False,
                    'verbose': True,
                    'legacy_server_connect': True,  # GitHub: helps with old TLS configs & Cloudflare
                }
                
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
                            logging.info(f"🔒 Attempting TLS impersonation: {impersonate_target}")
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
                    if video_height:
                        ydl_opts['format'] = f"best[height={video_height}]/best[height<={video_height}]/best"
                    else:
                        # Видео с H.264 кодеком
                        ydl_opts['format'] = 'best[vcodec^=h264]/best[vcodec^=avc]/best'
                
                try:
                    info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)
                except Exception as extract_error:
                    error_text = str(extract_error)
                    if is_youtube and video_height and "Requested format is not available" in error_text:
                        ydl_opts['format'] = 'best'
                        ydl_opts.pop('merge_output_format', None)
                        info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)
                    else:
                        raise

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
                logging.info(f"Downloaded: {file_path.name}")

                if use_impersonate and attempt > 1:
                    logging.info(f"✅ Success with user-agent {attempt}/{len(USER_AGENTS)} + impersonate={impersonate_target}")
                elif not use_impersonate:
                    logging.info(f"✅ Success without impersonate (attempt {attempt}/{len(USER_AGENTS)})")

                return file_path, None, metadata
                    
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
                    
                # If not 403, raise immediately
                logging.error(f"YT-DLP error: {error_str[:200]}")
                raise e
    
    # All attempts failed with 403
    raise last_error if last_error else Exception("All user-agent attempts failed")


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
        # Note: impersonate disabled for TikTok as it causes crashes
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

    info, prepared_name = await asyncio.to_thread(_run_ytdlp_extract, ydl_opts, url)

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
