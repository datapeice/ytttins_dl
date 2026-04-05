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
            # 2 hours for single files (standard videos/audios)
            # Increased from 10m to avoid deleting long-running downloads (like 4K videos or playlists)
            file_age_limit = 2 * 3600
            # 6 hours for directories (torrents usually finish by then or are abandoned)
            dir_age_limit = 6 * 3600
            
            downloads_path = Path(DOWNLOADS_DIR)
            if downloads_path.exists():
                for f in downloads_path.glob('*'):
                    # Skip zips as they have their own cleanup in zip_service
                    if 'zips' in str(f): continue
                    
                    try:
                        mtime = f.stat().st_mtime
                        age = now - mtime
                        
                        # 🛡️ Immunity for ACTIVE download fragments
                        # But ONLY if they are younger than 12 hours (43200s)
                        # If more than 12h, they are likely garbage from a crashed download
                        is_fragment = f.suffix.lower() in ('.part', '.ytdl', '.aria2', '.tmp')
                        
                        if is_fragment and age < 43200:
                            continue
                            
                        if f.is_file() and age > file_age_limit:
                            f.unlink()
                            print(f"Deleted old file: {f.name}")
                        elif f.is_dir() and age > dir_age_limit:
                            shutil.rmtree(f)
                            print(f"Deleted old directory: {f.name}")
                    except Exception as e:
                        print(f"Failed to delete {f.name}: {e}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        await asyncio.sleep(300) # Wait 5 minutes before checking again
