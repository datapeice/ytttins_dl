# Telegram Media Downloader Bot

A Telegram bot that downloads media from YouTube, YouTube Music, TikTok, and Instagram. Built with Python, aiogram 3.x, and yt-dlp.

## Features

- 📥 **Multi-platform downloads**:
  - YouTube videos with format selection (Video/Audio)
  - YouTube Music (automatic MP3 extraction)
  - TikTok videos
  - Instagram videos
- 🎵 High-quality audio extraction (320kbps MP3)
- � User whitelist management system
- 📊 **Advanced statistics tracking**:
  - Download counts (videos/music)
  - Active user monitoring
  - Weekly usage analytics
- � **Admin panel features**:
  - Live yt-dlp updates
  - Interactive user management
  - Real-time statistics
- 💾 Persistent data storage with JSON
- 🐋 Docker deployment ready
- 📝 Detailed logging system

## Prerequisites

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- FFmpeg (for audio extraction)
- Telegram Bot Token from [@BotFather](https://t.me/botfather)

## Quick Start

### 1. Configuration

Create a `.env` file in the root directory:

```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_USERNAME=your_telegram_username
```

> **Note**: Get your bot token from [@BotFather](https://t.me/botfather) on Telegram

### 2. Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py
```

### 3. Docker Deployment (Recommended)

```bash
# Build and start
docker compose up -d --build

# View logs
docker compose logs -f bot

# Stop the bot
docker compose down

# Stop and remove volumes
docker compose down -v
```

## Project Structure

```
ytttins_dl/
├── main.py                 # Main bot application
├── Dockerfile             # Docker container configuration
├── docker-compose.yml     # Docker Compose setup
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── example .env.txt       # Environment variables template
├── README.md             # This file
├── data/                 # Persistent storage (auto-created)
│   ├── stats.json       # Download statistics
│   └── users.json       # Whitelist data
├── downloads/            # Temporary download cache (auto-created)
└── logs/                # Application logs (auto-created)
    ├── bot.log         # General bot logs
    └── downloads.log   # Download history
```

## Bot Commands

### User Commands
- `/start` - Display welcome message and bot capabilities

### Admin Commands
- `/panel` - Open admin control panel with:
  - Weekly statistics dashboard
  - Download counts (videos/music)
  - Active users list
  - Whitelisted users
  - yt-dlp version info
- `add <username>` - Add user to whitelist

### Admin Panel Features

The interactive admin panel (`/panel`) provides:

1. **📊 Statistics Dashboard**
   - Weekly video downloads
   - Weekly music downloads
   - Active users count (last 7 days)
   - Current yt-dlp version

2. **👥 User Management**
   - View whitelisted users
   - Add users to whitelist
   - Remove users with one click
   - Active users monitoring

3. **🔄 System Maintenance**
   - Live yt-dlp updates with progress tracking
   - Real-time status updates in Telegram

## Usage Examples

### Downloading Videos

1. Send a YouTube URL to the bot
2. Choose format (🎵 Audio or 🎥 Video)
3. Wait for processing and upload

### YouTube Music

Simply send a `music.youtube.com` link - it will automatically download as MP3.

### TikTok/Instagram

Send the video URL directly - no format selection needed.

## Technical Details

### Dependencies

- `aiogram>=3.0.0` - Telegram Bot API framework
- `python-dotenv>=0.19.0` - Environment variable management
- `yt-dlp` - Media download engine
- FFmpeg - Audio/video processing (system dependency)

### Data Persistence

All data is stored in JSON format:

**users.json**:
```json
{
    "whitelisted_users": ["username1", "username2"]
}
```

**stats.json**:
```json
{
    "downloads_count": {
        "Video": 42,
        "Music": 28
    },
    "active_users": {
        "2025-11-17": [123456789, 987654321]
    }
}
```

### Docker Configuration

The bot runs in a containerized environment with:
- Persistent volumes for `data/`, `downloads/`, and `logs/`
- Automatic restart on failure
- Health checks every 30 seconds
- Log rotation (max 10MB, 3 files)

## Logging

Two log files are maintained:

1. **bot.log** - General bot operations and errors
2. **downloads.log** - Detailed download history with user info

Log format:
```
2025-11-17 15:30:00 - User: John Doe (@johndoe, ID: 123456789) | Platform: youtube | Type: Music | URL: https://...
```

## Security

- Admin commands require username verification
- Environment variables for sensitive data
- Whitelist system for user access control
- No hardcoded credentials

## Troubleshooting

### Bot not responding
```bash
# Check logs
docker compose logs -f bot

# Restart container
docker compose restart bot
```

### yt-dlp outdated
Use the admin panel's "🔄 Update yt-dlp" button for live updates without restarting.

### Permission errors
```bash
# Fix data directory permissions
sudo chown -R $USER:$USER data/ downloads/ logs/
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `ADMIN_USERNAME` | Yes | Telegram username for admin access |

## License

[MIT License](https://opensource.org/licenses/MIT)

## Contributing

Feel free to open issues or submit pull requests for improvements.

## Author

[@datapeice](https://github.com/datapeice)
