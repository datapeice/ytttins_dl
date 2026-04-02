"""
Test: Spotify download via spotDL
==================================
Usage:
  python test_spotify.py                  - download default test track
  python test_spotify.py <spotify_url>    - download by URL
  python test_spotify.py "song name"      - search and download
"""

import sys
import io
import os
import subprocess
import shutil
import time
from pathlib import Path

# Force UTF-8 stdout so Cyrillic / special chars don't crash on Windows CP1252
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Settings ──────────────────────────────────────────────────────────────────
OUTPUT_DIR   = Path(__file__).parent / "spotify_downloads"
DEFAULT_URL  = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"  # Rick Astley
AUDIO_FORMAT = "mp3"   # mp3 / flac / ogg / opus / m4a / wav
BITRATE      = "320k"  # audio bitrate

# Use Windows 'py' launcher when available (avoids broken-prefix issues)
PY_CMD = shutil.which("py") or sys.executable
# ──────────────────────────────────────────────────────────────────────────────


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def check_spotdl() -> bool:
    if shutil.which("spotdl"):
        return True
    r = subprocess.run([PY_CMD, "-m", "spotdl", "--version"],
                       capture_output=True, text=True)
    return r.returncode == 0


def get_spotdl_version() -> str:
    for cmd in [["spotdl", "--version"], [PY_CMD, "-m", "spotdl", "--version"]]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return (r.stdout.strip() or r.stderr.strip())
        except Exception:
            continue
    return "unknown"


def install_spotdl() -> None:
    print("  [!] spotDL not found - installing...")
    subprocess.run([PY_CMD, "-m", "pip", "install", "spotdl"], check=True)
    print("  [OK] spotDL installed")


def download(target: str) -> bool:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        PY_CMD, "-m", "spotdl", "download", target,
        "--output", str(OUTPUT_DIR),
        "--format", AUDIO_FORMAT,
        "--bitrate", BITRATE,
        "--print-errors",
    ]

    print("\n>>> " + " ".join(cmd))
    print("-" * 64)

    t0 = time.time()
    result = subprocess.run(cmd, text=True)
    elapsed = time.time() - t0

    print("-" * 64)

    if result.returncode == 0:
        files = sorted(
            OUTPUT_DIR.glob(f"*.{AUDIO_FORMAT}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        print(f"\n[OK] Finished in {elapsed:.1f}s")
        if files:
            print(f"[+] Downloaded {len(files)} file(s):")
            for f in files[:10]:
                print(f"    * {f.name}  ({f.stat().st_size // 1024} KB)")
        return True
    else:
        print(f"\n[FAIL] spotDL exited with code {result.returncode}")
        return False


def main():
    sep = "=" * 64
    print(sep)
    print("  Spotify Download Test  (spotDL + ffmpeg)")
    print(f"  py launcher : {PY_CMD}")
    print(sep)

    # --- dependency checks ---
    print("\n[1/3] Checking dependencies...")

    if not check_ffmpeg():
        print("  [FAIL] ffmpeg not found!")
        print("         Install ffmpeg: https://ffmpeg.org/download.html")
        sys.exit(1)
    print("  [OK] ffmpeg found")

    if not check_spotdl():
        install_spotdl()
    else:
        print(f"  [OK] spotDL: {get_spotdl_version()}")

    # --- target ---
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"\n[2/3] Target:\n  {target}")
    print(f"\n[3/3] Saving to: {OUTPUT_DIR}\n")

    ok = download(target)

    print("\n" + sep)
    print("  Result:", "PASSED" if ok else "FAILED")
    print(sep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
