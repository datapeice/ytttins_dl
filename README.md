# Telegram Media Downloader Bot

A Telegram bot that downloads media from YouTube, YouTube Music, TikTok, and Instagram. Built with Python, aiogram 3.x, and yt-dlp.

## Features

- 📥 **Multi-platform downloads** with triple fallback system:
  - **yt-dlp** (primary method)
  - **Cobalt API** (fallback with funny status messages)
  - **TikWM** (TikTok-only fallback)
- 🌐 **Supported platforms**:
  - YouTube videos with format selection (Video/Audio)
  - YouTube Music (automatic MP3 extraction)
  - TikTok videos and photo slideshows
  - Instagram videos
- 🔐 **SOCKS5 proxy support** for geo-restricted content
- 🎭 **Funny status messages** during Cobalt download
- 📊 **Streaming progress updates** (20% intervals)
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
- (Optional) `cookies.txt` for YouTube authentication

## YouTube Authentication (Fix for "Sign in" errors)

If you encounter "Sign in to confirm you’re not a bot" errors:

1. Install a browser extension like "Get cookies.txt LOCALLY" (Chrome/Firefox).
2. Go to YouTube.com and make sure you are logged in.
3. Export your cookies to a file named `cookies.txt`.

### How to add cookies to the bot:

**Option 1: Via Telegram (Recommended)**
1. Open the Admin Panel (`/panel`).
2. Click "🍪 Update Cookies".
3. Send the `cookies.txt` file to the bot.

**Option 2: Via Environment Variable (Heroku/Docker)**
You can paste the content of `cookies.txt` into an environment variable named `COOKIES_CONTENT`. The bot will automatically create the file on startup.

**Option 3: Manual File Placement**
Place the file in the `data/` directory of the project.

## Heroku Deployment

Since Heroku has an ephemeral filesystem (files are deleted on restart), you have two options for persistence:

1. **Environment Variables (For Cookies)**:
   - Set `COOKIES_CONTENT` config var with the content of your `cookies.txt`.
   - This ensures cookies persist across restarts.

2. **Database (For Stats/Whitelist)**:
   - Currently, this bot uses local JSON files (`users.json`, `stats.json`).
   - On Heroku, these will be reset when the dyno restarts.
   - **Note**: If you need persistent stats/whitelist on Heroku, you will need to fork this project and implement a database (e.g., MongoDB/PostgreSQL).



## Quick Start

### 1. Configuration

Copy `.env.example` to `.env` and configure:

```env
# Required
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_USERNAME=your_telegram_username

# Cobalt API (optional but recommended)
COBALT_API_URL=http://your-cobalt-server:9000/
USE_COBALT=true
COBALT_API_KEY=your_api_key

# SOCKS5 Proxy (optional, for geo-restricted content)
HTTP_PROXY=socks5://user:password@proxy-host:1080
SOCKS_PROXY=socks5://user:password@proxy-host:1080
```

> **Note**: Get your bot token from [@BotFather](https://t.me/botfather) on Telegram
> 
> **Cobalt API**: External [Cobalt](https://github.com/imputnet/cobalt) instance for fallback downloads
> 
> **Proxy**: Encode special characters in password (& = %26, ^ = %5E, @ = %40)

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

## Download Fallback System

The bot uses a **triple fallback chain** for 100% download reliability:

### 1️⃣ yt-dlp (Primary)
- Direct download without proxy
- Fast and reliable for most videos

### 2️⃣ yt-dlp + SOCKS5 Proxy (Fallback #1)
- Automatically activates if direct download fails
- Bypasses geo-restrictions
- Shows status: `🔐 Retrying yt-dlp with proxy...`

### 3️⃣ Cobalt API (Fallback #2)
- External Cobalt instance
- Shows **funny status messages**:
  - "💻 Hacking the Pentagon..."
  - "🍕 Ordering pizza for the server's rats..."
  - "🇵🇱 Searching for Polish alt girls..."
  - etc. (21 total messages)
- Streaming progress: `⬇️ Downloading 40%...`

### 4️⃣ TikWM (Fallback #3, TikTok only)
- Last resort for TikTok videos
- Ensures 100% success rate

**Example flow:**
```
User sends URL → yt-dlp tries → Fails (geo-blocked)
              → yt-dlp+proxy tries → Fails (API down)
              → Cobalt API tries → Success! ✅
```

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
