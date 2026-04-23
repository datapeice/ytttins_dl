import aiohttp
import logging
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Optional
from config import DOWNLOADS_DIR

try:
    from ytmusicapi import YTMusic as _YTMusic
except ImportError:
    _YTMusic = None  # type: ignore


async def search_ytmusic_video_id(query: str) -> Optional[str]:
    """
    Search YouTube Music for the best matching song and return its video URL.

    Strategy (in order of priority):
    1. Deezer API → ISRC code → YouTube Music search by ISRC (most precise)
    2. ytmusicapi → search in 'songs' filter → first result videoId

    Returns a full YouTube watch URL on success, or None if nothing was found.
    """
    if _YTMusic is None:
        logging.warning("[SEARCH] ytmusicapi is not installed; skipping YouTube Music search")
        return None

    # --- Step 1: Try to get ISRC via Deezer (no API key required) ---
    isrc = None
    try:
        deezer_url = "https://api.deezer.com/search/track"
        params = {"q": query, "limit": 1}
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession() as session:
            async with session.get(deezer_url, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    items = data.get("data", [])
                    if items:
                        isrc = items[0].get("isrc")
                        logging.info(f"[SEARCH] Deezer ISRC for '{query}': {isrc}")
    except Exception as e:
        logging.warning(f"[SEARCH] Deezer ISRC lookup failed: {e}")

    # Initialise the YTMusic client once and reuse it for both lookups
    try:
        ytm = await asyncio.to_thread(_YTMusic)
    except Exception as e:
        logging.warning(f"[SEARCH] YTMusic client init failed: {e}")
        return None

    # --- Step 2a: If we have an ISRC, search YouTube Music directly ---
    if isrc:
        try:
            results = await asyncio.to_thread(ytm.search, f"isrc:{isrc}", filter="songs", limit=1)
            if results:
                video_id = results[0].get("videoId")
                if video_id:
                    logging.info(f"[SEARCH] ✅ ytmusicapi ISRC match: {video_id}")
                    return f"https://www.youtube.com/watch?v={video_id}"
        except Exception as e:
            logging.warning(f"[SEARCH] ytmusicapi ISRC search failed: {e}")

    # --- Step 2b: Fall back to ytmusicapi plain 'songs' search ---
    try:
        results = await asyncio.to_thread(ytm.search, query, filter="songs", limit=3)
        if results:
            video_id = results[0].get("videoId")
            if video_id:
                logging.info(f"[SEARCH] ✅ ytmusicapi songs match: {video_id}")
                return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        logging.warning(f"[SEARCH] ytmusicapi songs search failed: {e}")

    return None


async def fetch_song_metadata(query: str) -> Dict[str, str]:
    """
    Fetches song metadata (title, artist, album, cover art) from the iTunes API.
    iTunes is used instead of Spotify because it requires zero API keys/setup
    while providing identical high-quality metadata.
    """
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "entity": "song",
        "limit": 1
    }
    
    metadata = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=5) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    if data.get("resultCount", 0) > 0:
                        result = data["results"][0]
                        metadata["title"] = result.get("trackName")
                        metadata["artist"] = result.get("artistName")
                        metadata["album"] = result.get("collectionName")
                        # Get a high-res cover art (iTunes returns 100x100, we replace to 1000x1000)
                        if "artworkUrl100" in result:
                            cover_url = result["artworkUrl100"].replace("100x100bb", "1000x1000bb")
                            metadata["cover_url"] = cover_url
                            
                            # Download the cover locally
                            async with session.get(cover_url, timeout=10) as img_resp:
                                if img_resp.status == 200:
                                    img_path = DOWNLOADS_DIR / f"cover_{uuid.uuid4().hex[:8]}.jpg"
                                    with open(img_path, "wb") as f:
                                        f.write(await img_resp.read())
                                    metadata["local_cover_path"] = str(img_path)
    except Exception as e:
        logging.warning(f"Failed to fetch metadata from iTunes for '{query}': {e}")
        
    return metadata
