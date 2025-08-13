# Telegram Media Downloader Bot

A Telegram bot that can download media from YouTube, TikTok, and Instagram. Built with Python, aiogram, and yt-dlp.

## Features

- 📥 Download videos from:
  - YouTube
  - TikTok
  - Instagram
- 🎵 Extract audio from YouTube videos
- 👤 User whitelist system
- 📊 Statistics tracking
  - Download counts
  - Active users
  - Weekly stats
- 🔒 Admin panel with controls
- 💾 Persistent data storage
- 🐋 Docker deployment ready

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- FFmpeg

## Configuration

1. Create a `.env` file in the root directory:
```env
BOT_TOKEN=your_telegram_bot_token_here
```

2. Set your admin username in `main.py`:
```python
ADMIN_USER_ID = "your_telegram_username"
```

## Local Development

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the bot:
```bash
python main.py
```

## Docker Deployment

1. Build and run using Docker Compose:
```bash
docker compose up -d --build
```

2. View logs:
```bash
docker logs -f telegram-downloader-bot
```

3. Stop the bot:
```bash
docker compose down
```

## Remote Deployment

Use the provided deployment script:
```bash
chmod +x deploy.sh  # Make script executable
./deploy.sh
```

The script will:
- Copy files to the remote server
- Build and start the Docker container
- Set up persistent storage

## Project Structure

```
.
├── main.py              # Main bot code
├── Dockerfile          # Docker configuration
├── docker-compose.yml  # Docker Compose configuration
├── requirements.txt    # Python dependencies
├── deploy.sh          # Deployment script
├── .env               # Environment variables
├── data/              # Persistent data storage
│   ├── stats.json    # Statistics data
│   └── users.json    # Whitelist data
├── downloads/         # Temporary download directory
└── logs/             # Log files
    ├── bot.log      # Bot operation logs
    └── downloads.log # Download history
```

## Bot Commands

- `/start` - Start the bot and show welcome message
- `/panel` - Access admin panel (admin only)
- `/whitelist <username>` - Add user to whitelist (admin only)
- `/unwhitelist <username>` - Remove user from whitelist (admin only)

## Features

### Download Types
- YouTube videos (with format selection)
- YouTube Music (automatic MP3 conversion)
- TikTok videos
- Instagram videos

### Admin Panel
- View download statistics
- Manage whitelisted users
- Monitor active users
- View weekly usage stats

### Data Persistence
- Download statistics
- User whitelist
- Active user tracking
- All data persists through restarts

## License

[MIT License](https://opensource.org/licenses/MIT)
