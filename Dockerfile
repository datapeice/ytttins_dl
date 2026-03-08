FROM python:3.13-slim

WORKDIR /app

# Install system dependencies including FFmpeg and cleanup
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
    && rm -rf /var/lib/apt/lists/*

# Install PhantomJS for x86_64 headless extractors
RUN wget -q -O /tmp/phantomjs.tar.bz2 https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2 && \
    tar -xf /tmp/phantomjs.tar.bz2 -C /tmp/ && \
    mv /tmp/phantomjs-2.1.1-linux-x86_64/bin/phantomjs /usr/local/bin/ && \
    chmod +x /usr/local/bin/phantomjs && \
    rm -rf /tmp/phantomjs*

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
