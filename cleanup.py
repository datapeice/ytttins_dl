import os
import time
import asyncio
from pathlib import Path
from config import DOWNLOADS_DIR

async def delete_old_files():
    while True:
        try:
            now = time.time()
            # 10 minutes
            age_limit = 10 * 60
            downloads_path = Path(DOWNLOADS_DIR)
            if downloads_path.exists():
                for f in downloads_path.glob('*'):
                    if f.is_file() and (now - f.stat().st_mtime) > age_limit:
                        try:
                            f.unlink()
                            print(f"Deleted old file: {f.name}")
                        except Exception as e:
                            print(f"Failed to delete {f.name}: {e}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        await asyncio.sleep(60) # Wait 1 minute before checking again
