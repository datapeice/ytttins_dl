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

    def extract_tracker_url(self, torrent_path: Path) -> Optional[str]:
        """Tries to extract a tracker URL (like rutracker) from .torrent metadata."""
        try:
            with open(torrent_path, 'rb') as f:
                data = f.read()
            
            # 1. Search for typical tracker URL pattern (e.g. rutracker)
            match = re.search(rb'https?://[^\s<>"]+viewtopic\.php\?t=\d+', data)
            if match:
                return match.group(0).decode('utf-8', errors='ignore')
                
            # 2. Fallback: Search for bencoded 'comment' field
            match = re.search(rb'7:comment(\d+):', data)
            if match:
                try:
                    length = int(match.group(1))
                    start = match.end()
                    comment = data[start:start+length].decode('utf-8', errors='ignore')
                    if comment.startswith('http'):
                        return comment
                except: pass
            return None
        except Exception:
            return None

    async def get_torrent_info(self, torrent_path: Path) -> Dict:
        """Returns information about the torrent: files, total_size, name."""
        cmd = ["aria2c", "--show-files", str(torrent_path)]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode()
        
        if process.returncode != 0:
            err = stderr.decode()
            if "not found" in err.lower():
                raise Exception("aria2c is not installed on the system.")
            raise Exception(f"Failed to get torrent info: {err}")
        
        files = []
        total_size = 0
        name = ""
        
        lines = output.splitlines()
        data_started = False
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Parse Name
            if line.lower().startswith("name:"):
                name = line.split(":", 1)[1].strip()
                continue
                
            # Parse Total Length
            if line.lower().startswith("total length:"):
                # Format: Total Length: 279MiB (292,804,887)
                size_match = re.search(r"\((\d+)\)", line)
                if size_match:
                    total_size = int(size_match.group(1))
                else:
                    # Try to parse the first part if parenthesis not found
                    parts = line.split(":", 1)[1].strip().split()
                    if parts:
                        total_size = self._parse_size(parts[0])
                continue

            # Parse files list (idx|path|size format)
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
                    data_started = True
        
        return {
            'files': files,
            'total_size': total_size,
            'name': name
        }

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
        
        # aria2c command with BitTorrent optimizations
        cmd = [
            "aria2c",
            "--dir", str(output_dir),
            "--seed-time=0",
            "--summary-interval=6",
            "--bt-stop-timeout=120", # Wait up to 120s of no progress
            "--file-allocation=none",
            "--enable-dht=true",
            "--bt-enable-lpd=true",
            "--enable-peer-exchange=true", # PEX helps find peers without tracker
            "--bt-max-peers=120",
            "--listen-port=16881-16890",
            "--dht-listen-port=16881-16890",
            "--bt-tracker-timeout=30",
            "--bt-tracker-interval=60",
            "--user-agent=Transmission/3.00", # Some trackers block aria2c
            "--peer-id-prefix=-TR3000-",      # Impersonate Transmission
            str(torrent_path)
        ]
        
        logging.info(f"Starting torrent download: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        last_progress_time = asyncio.get_event_loop().time()
        start_time = last_progress_time
        has_health_ever = False
        last_status_text = ""
        
        # Stall detection timeout (increased to 90s for slower trackers)
        STALL_TIMEOUT = 90
        
        while True:
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                if asyncio.get_event_loop().time() - start_time > STALL_TIMEOUT and not has_health_ever:
                    process.terminate()
                    raise Exception("No seeds/peers found. This torrent appears to be dead (cannot download).")
                continue
                
            if not line:
                break
            
            line_str = line.decode().strip()
            
            # Seed/Peer/Connection regexes
            percent_match = re.search(r"\((\d+)%\)", line_str) or re.search(r"(\d+)%", line_str)
            sp_match = re.search(r"[(\[]S:(\d+)[, ]+P:(\d+)[\)\]]", line_str)
            if not sp_match:
                sp_match = re.search(r"S:(\d+).*P:(\d+)", line_str)
            
            cn_match = re.search(r"CN:(\d+)", line_str)
            dl_match = re.search(r"DL:([\d.]+)([a-zA-Z]+)", line_str)
            
            status_text = ""
            status_parts = []
            
            if percent_match:
                status_parts.append(f"Downloading: {percent_match.group(1)}%")
                if int(percent_match.group(1)) > 0:
                    has_health_ever = True
            
            if sp_match:
                seeds = int(sp_match.group(1))
                peers = int(sp_match.group(2))
                if seeds > 0 or peers > 0:
                    has_health_ever = True
                status_parts.append(f"Seeds: {seeds} | Peers: {peers}")
            elif cn_match:
                status_parts.append(f"Connections: {cn_match.group(1)}")
            
            if dl_match:
                speed_val = float(dl_match.group(1))
                if speed_val > 0:
                    has_health_ever = True
                status_parts.append(f"Speed: {dl_match.group(1)}{dl_match.group(2)}")
            
            if status_parts:
                status_text = "\n".join(status_parts)
            
            if status_text and status_text != last_status_text:
                if progress_callback:
                    await progress_callback(status_text)
                last_status_text = status_text
                
            # Periodic check for dead torrents if stuck at start
            if asyncio.get_event_loop().time() - start_time > STALL_TIMEOUT and not has_health_ever:
                process.terminate()
                raise Exception("No seeds/peers found. This torrent appears to be dead (cannot download).")
        
        await process.wait()
        
        if process.returncode != 0:
            # Check if it was terminated by us or failed
            stderr_data = await process.stderr.read()
            err_msg = stderr_data.decode()
            if "Terminated" in err_msg or process.returncode == -15: # SIGTERM
                raise Exception("No seeds/peers found. This torrent appears to be dead (cannot download).")
            
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
