import aiohttp
import logging
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Optional
from config import DOWNLOADS_DIR

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
