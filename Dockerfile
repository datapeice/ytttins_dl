FROM python:3.13-slim

WORKDIR /app

# Install system dependencies including FFmpeg, Chrome, and cleanup
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    python3-pip \
    git \
    libcurl4 \
    ca-certificates \
    wget \
    bzip2 \
    aria2 \
    mkvtoolnix \
    rtmpdump \
    atomicparsley \
    fontconfig \
    libfreetype6 \
    nodejs \
    # Dependencies for Chrome
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libvulkan1 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome Stable for browser impersonation
RUN wget -q -O /tmp/google-chrome-stable.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y /tmp/google-chrome-stable.deb && \
    rm /tmp/google-chrome-stable.deb && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js for JS execution (replaces broken PhantomJS)
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/node /usr/local/bin/node && \
    node --version

# Create directories for persistent storage
RUN mkdir -p /app/downloads /app/logs /app/data

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure correct permissions for persistent directories
RUN chmod -R 777 /app/downloads /app/logs /app/data \
    && rm -rf /app/users.json  # Remove old users.json if it exists

# Create volume mount points for persistent data
VOLUME ["/app/downloads", "/app/logs", "/app/data"]

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app:${PATH}"

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ps aux | grep python | grep main.py || exit 1

# Command to run the bot
CMD ["python", "main.py"]
