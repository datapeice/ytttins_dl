# ytttins-dl — Java Rewrite

A complete Java rewrite of the Python Telegram media-downloader bot, preserving
all original logic and architecture.

## Architecture

```
java/
├── pom.xml                              # Maven build (Spring Boot 3, Java 17)
├── Dockerfile                           # Multi-stage Docker build
├── docker-compose.yml                   # Bot + PostgreSQL + Cobalt
├── .env.example                         # Environment variable template
└── src/
    ├── main/java/me/datapeice/ytttins/
    │   ├── YtttinsApplication.java       # Spring Boot entry point
    │   ├── config/
    │   │   └── BotConfig.java            # All env-var config (≈ config.py)
    │   ├── bot/
    │   │   └── TelegramBot.java          # Bot registration + update dispatch
    │   ├── handler/
    │   │   ├── UserHandler.java          # /start, URL handling, format selection
    │   │   └── AdminHandler.java         # /panel, whitelist, broadcast, cookies
    │   ├── service/
    │   │   ├── DownloaderService.java    # Triple-fallback download engine
    │   │   ├── CobaltClient.java         # Cobalt API HTTP client
    │   │   ├── TikTokScraper.java        # TikWM metadata + fallback download
    │   │   └── CleanupService.java       # Scheduled file cleanup (every 60 s)
    │   └── database/
    │       ├── entity/                   # JPA entities (5 tables)
    │       ├── repository/               # Spring Data repositories
    │       └── service/
    │           └── StorageService.java   # Whitelist, stats, history (≈ storage.py)
    └── resources/
        ├── application.yml              # Spring Boot configuration
        └── logback.xml                  # Logging (bot.log + downloads.log)
```

## Python → Java mapping

| Python file | Java equivalent |
|---|---|
| `main.py` | `YtttinsApplication.java` + `TelegramBot.java` |
| `config.py` | `BotConfig.java` |
| `handlers/user.py` | `UserHandler.java` |
| `handlers/admin.py` | `AdminHandler.java` |
| `services/downloader.py` | `DownloaderService.java` |
| `services/cobalt_client.py` | `CobaltClient.java` |
| `services/tiktok_scraper.py` | `TikTokScraper.java` |
| `cleanup.py` | `CleanupService.java` |
| `database/models.py` | `database/entity/*.java` |
| `database/storage.py` | `StorageService.java` |

## Download flow (same as Python)

```
URL received
  │
  ├─ TikTok short URL? → resolve redirect
  ├─ Reddit short URL? → unshorten
  ├─ Strip query params (non-YT/IG)
  │
  ├─ Instagram / Reddit on Heroku → try Cobalt FIRST
  │
  ├─ [Method 1] yt-dlp  (retry with multiple User-Agents on 403)
  │     └─ TikTok → dedicated method with slideshow support
  │
  ├─ [Method 1.5] yt-dlp + SOCKS5 proxy  (if SOCKS_PROXY is set)
  │
  ├─ [Method 2] Cobalt API  (if USE_COBALT=true)
  │
  └─ [Method 3] TikWM  (TikTok only)
```

## Quick start

### Local development (long-polling, H2 database)

```bash
cd java
cp .env.example .env
# Edit .env and set BOT_TOKEN and ADMIN_USERNAME

mvn spring-boot:run
```

### Docker Compose (PostgreSQL, production-ready)

```bash
cd java
cp .env.example .env
# Edit .env

docker compose up --build -d

# Optional: enable Cobalt fallback
docker compose --profile cobalt up -d
```

## Requirements

- Java 17+
- Maven 3.9+
- `yt-dlp` and `ffmpeg` installed on the host (or inside the Docker image)

## Key features (preserved from Python)

- ✅ Multi-platform downloads (1800+ sites via yt-dlp)
- ✅ YouTube format selection (audio MP3 / video with quality picker)
- ✅ TikTok videos + photo slideshows
- ✅ Instagram reels + carousel
- ✅ Triple fallback: yt-dlp → yt-dlp+proxy → Cobalt → TikWM
- ✅ Admin panel with stats, whitelist management, broadcast, cookie upload, yt-dlp update
- ✅ Whitelist access control
- ✅ Persistent storage (PostgreSQL or H2)
- ✅ Automatic file cleanup every 60 s
- ✅ Funny status messages during download
- ✅ Docker + Docker Compose deployment
