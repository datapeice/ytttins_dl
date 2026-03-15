import json
import logging
from pathlib import Path

def convert_netscape_to_json(netscape_path: Path, json_path: Path):
    """
    Convert Netscape / yt-dlp cookie format to JSON for Cobalt.
    """
    if not netscape_path.exists():
        logging.warning(f"Netscape cookies not found at {netscape_path}")
        return False
        
    cookies = []
    try:
        with open(netscape_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    cookie = {
                        "domain": parts[0],
                        "httpOnly": parts[1].upper() == "TRUE",
                        "path": parts[2],
                        "secure": parts[3].upper() == "TRUE",
                        "expirationDate": int(parts[4]),
                        "name": parts[5],
                        "value": parts[6]
                    }
                    cookies.append(cookie)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
            
        logging.info(f"Successfully converted cookies to {json_path} ({len(cookies)} entries)")
        return True
    except Exception as e:
        logging.error(f"Failed to convert cookies: {e}")
        return False
