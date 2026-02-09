#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Cobalt API с прокси.
Использование: python test_cobalt.py <youtube_url>
"""

import asyncio
import sys
import logging
from services.cobalt_client import cobalt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def test_cobalt(url: str):
    """Тест загрузки через Cobalt API"""
    print(f"\n🧪 Testing Cobalt API with URL: {url}")
    print(f"📡 API URL: {cobalt.api_url}")
    print(f"🔐 Proxy: {cobalt._mask_proxy(cobalt.proxy) if cobalt.proxy else 'No proxy'}")
    print("-" * 60)
    
    try:
        # Тест видео
        print("\n🎥 Testing video download...")
        file_path, thumb_path, metadata = await cobalt.download_media(url, quality="720")
        
        print(f"✅ Download successful!")
        print(f"   File: {file_path}")
        print(f"   Size: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
        print(f"   Metadata: {metadata}")
        
        # Очистка
        if file_path and file_path.exists():
            file_path.unlink()
            print(f"🧹 Cleaned up: {file_path.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        logging.exception("Test failed")
        return False

async def test_audio(url: str):
    """Тест загрузки аудио"""
    print(f"\n🎵 Testing audio download...")
    
    try:
        file_path, thumb_path, metadata = await cobalt.download_media(url, is_audio=True)
        
        print(f"✅ Audio download successful!")
        print(f"   File: {file_path}")
        print(f"   Size: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # Очистка
        if file_path and file_path.exists():
            file_path.unlink()
            print(f"🧹 Cleaned up: {file_path.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_cobalt.py <youtube_url>")
        print("Example: python test_cobalt.py 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Запускаем тесты
    asyncio.run(test_cobalt(url))
    
    # Опционально тест аудио
    if "--audio" in sys.argv:
        asyncio.run(test_audio(url))
