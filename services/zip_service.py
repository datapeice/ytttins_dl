import os
import uuid
import time
import zipfile
import shutil
import logging
from pathlib import Path
from typing import Dict, Optional
from config import DOWNLOADS_DIR, BASE_DIR

ZIP_DIR = DOWNLOADS_DIR / "zips"
ZIP_DIR.mkdir(exist_ok=True)

# Map of secure_id -> { 'path': Path, 'expiry': float, 'name': str }
zip_cache: Dict[str, dict] = {}

def create_playlist_zip(files: list[Path], playlist_name: str) -> str:
    """Creates a zip file from a list of files and returns a secure_id."""
    secure_id = str(uuid.uuid4()).replace("-", "")[:12]
    zip_filename = f"{secure_id}.zip"
    zip_path = ZIP_DIR / zip_filename
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            if file.exists():
                # Add file to zip using its original name
                zipf.write(file, arcname=file.name)
    
    expiry = time.time() + (24 * 3600) # 24 hours
    zip_cache[secure_id] = {
        'path': zip_path,
        'expiry': expiry,
        'name': f"{playlist_name}.zip"
    }
    
    logging.info(f"Created ZIP {secure_id} for playlist '{playlist_name}', expires in 24h")
    return secure_id

def get_zip_info(secure_id: str) -> Optional[dict]:
    """Retrieves zip info if it exists and hasn't expired."""
    info = zip_cache.get(secure_id)
    if info:
        if time.time() < info['expiry']:
            return info
        else:
            # Expired, clean up
            cleanup_zip(secure_id)
    return None

def cleanup_zip(secure_id: str):
    """Deletes the zip file and removes from cache."""
    info = zip_cache.pop(secure_id, None)
    if info and info['path'].exists():
        try:
            info['path'].unlink()
            logging.info(f"Cleaned up expired ZIP {secure_id}")
        except Exception as e:
            logging.error(f"Error cleaning up ZIP {secure_id}: {e}")

def run_zip_cleanup_task():
    """Checks all cached zips and removes expired ones."""
    now = time.time()
    to_delete = [sid for sid, info in zip_cache.items() if now > info['expiry']]
    for sid in to_delete:
        cleanup_zip(sid)
        
    # Also scan directory for stray files not in cache (e.g. from previous runs)
    for zip_file in ZIP_DIR.glob("*.zip"):
        sid = zip_file.stem
        if sid not in zip_cache:
            file_age = now - zip_file.stat().st_mtime
            if file_age > (24 * 3600):
                try:
                    zip_file.unlink()
                    logging.info(f"Cleaned up stray ZIP {zip_file.name}")
                except Exception:
                    pass
