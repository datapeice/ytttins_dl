import asyncio
import subprocess
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import uuid
import re

class TorrentService:
    def __init__(self, downloads_dir: Path):
        self.downloads_dir = downloads_dir
        self.media_extensions = {
            '.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m2ts', # Video
            '.flac', '.mp3', '.m4a', '.wav', '.ogg', '.opus', '.wma' # Audio
        }

    async def get_torrent_info(self, torrent_path: Path) -> List[Dict]:
        """Returns a list of files in the torrent and their sizes using aria2c."""
        cmd = ["aria2c", "--show-files", str(torrent_path)]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            err = stderr.decode()
            # Try to catch common errors
            if "not found" in err.lower():
                raise Exception("aria2c is not installed on the system.")
            raise Exception(f"Failed to get torrent info: {err}")
        
        output = stdout.decode()
        files = []
        
        # aria2c --show-files output parsing
        # It usually looks like this:
        # idx|path/to/file|size
        # 1|./Some Folder/file.mp4|1.2GiB
        lines = output.splitlines()
        
        # Find the header line or start of data
        data_started = False
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Skip noise until we see something like "idx|path|size" or "1|..."
            if "idx" in line.lower() and "|" in line:
                data_started = True
                continue
            
            if data_started or (line and line[0].isdigit() and "|" in line):
                parts = line.split('|')
                if len(parts) >= 3:
                    idx = parts[0].strip()
                    path = parts[1].strip()
                    size_str = parts[2].strip()
                    
                    if not idx.isdigit():
                        continue
                        
                    size_bytes = self._parse_size(size_str)
                    files.append({
                        'index': idx,
                        'path': path,
                        'size': size_bytes,
                        'size_str': size_str
                    })
                    data_started = True # Ensure we continue after first match
        
        if not files:
            # Fallback for different aria2 versions/formats
            logging.warning(f"Could not parse aria2c --show-files output reliably. Output: {output[:500]}")
            
        return files

    def _parse_size(self, size_str: str) -> int:
        """Converts human readable size (e.g. 1.2GiB, 500MiB) to bytes."""
        units = {
            "B": 1, "K": 1024, "KB": 1024, "KIB": 1024,
            "M": 1024**2, "MB": 1024**2, "MIB": 1024**2,
            "G": 1024**3, "GB": 1024**3, "GIB": 1024**3,
            "T": 1024**4, "TB": 1024**4, "TIB": 1024**4
        }
        match = re.match(r"^([\d.]+)\s*([a-zA-Z]+)?", size_str.upper())
        if not match:
            return 0
        number = float(match.group(1))
        unit = match.group(2) or "B"
        return int(number * units.get(unit, 1))

    async def download_torrent(self, torrent_path: Path, progress_callback=None) -> Tuple[List[Path], Path]:
        """Downloads the torrent and returns a list of media files and the output directory."""
        unique_id = uuid.uuid4().hex[:8]
        output_dir = self.downloads_dir / f"torrent_{unique_id}"
        output_dir.mkdir(exist_ok=True)
        
        # aria2c command
        cmd = [
            "aria2c",
            "--dir", str(output_dir),
            "--seed-time=0",
            "--summary-interval=3",
            "--file-allocation=none",
            str(torrent_path)
        ]
        
        logging.info(f"Starting torrent download: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            line_str = line.decode().strip()
            if "(% " in line_str or "%" in line_str:
                match = re.search(r"\((\d+)%\)", line_str)
                if not match:
                    match = re.search(r"(\d+)%", line_str)
                    
                if match and progress_callback:
                    percent = match.group(1)
                    await progress_callback(f"Downloading torrent: {percent}%")
        
        await process.wait()
        
        if process.returncode != 0:
            stderr_data = await process.stderr.read()
            err_msg = stderr_data.decode()
            logging.error(f"Torrent download failed: {err_msg}")
            raise Exception(f"Download failed: {err_msg[:200]}")
            
        media_files = []
        for p in output_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in self.media_extensions:
                media_files.append(p)
                
        return media_files, output_dir

# Singleton
from config import DOWNLOADS_DIR
torrent_service = TorrentService(DOWNLOADS_DIR)
