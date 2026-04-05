import os
import time
import asyncio
from pathlib import Path
from config import DOWNLOADS_DIR

async def delete_old_files():
    import shutil
    while True:
        try:
            now = time.time()
            # 10 minutes for single files (standard videos/audios)
            file_age_limit = 10 * 60
            # 4 hours for directories (torrents usually finish by then or are abandoned)
            dir_age_limit = 4 * 3600
            
            downloads_path = Path(DOWNLOADS_DIR)
            if downloads_path.exists():
                for f in downloads_path.glob('*'):
                    # Skip zips as they have their own cleanup in zip_service
                    if 'zips' in str(f): continue
                    
                    try:
                        mtime = f.stat().st_mtime
                        if f.is_file() and (now - mtime) > file_age_limit:
                            f.unlink()
                            # logging is better but print is fine here given existing code
                            print(f"Deleted old file: {f.name}")
                        elif f.is_dir() and (now - mtime) > dir_age_limit:
                            shutil.rmtree(f)
                            print(f"Deleted old directory: {f.name}")
                    except Exception as e:
                        print(f"Failed to delete {f.name}: {e}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        await asyncio.sleep(300) # Wait 5 minutes before checking again
