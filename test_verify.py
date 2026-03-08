import asyncio
from services.downloader import download_media
from config import DATA_DIR
import sys

async def main():
    url = "https://vt.tiktok.com/ZNRu2WWyE/"
    user_id = 123
    
    file_path, thumb_path, meta = await download_media(url, user_id, 'tiktok')
    print("KEYS:", meta.keys())
    print("Uploader:", meta.get('uploader'))
    print("Verified:", meta.get('verified'))
    print("Uploader is verified:", meta.get('uploader_is_verified'))
    print("Channel is verified:", meta.get('channel_is_verified'))
    print("Creator is verified:", meta.get('creator_is_verified'))
    print("is_verified:", meta.get('is_verified'))
    
if __name__ == "__main__":
    asyncio.run(main())
