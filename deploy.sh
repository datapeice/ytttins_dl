#!/bin/bash

# Configuration
REMOTE_USER="remote_user"
REMOTE_HOST="remote_host"
REMOTE_DIR="remote_directory"
APP_NAME="telegram-downloader-bot"

# Colors for output
GREEN='\034[0;32m'
RED='\034[0;31m'
NC='\034[0m'

echo -e "${GREEN}Starting deployment...${NC}"

# Check if all required files exist
required_files=("main.py" "Dockerfile" "docker-compose.yml" "requirements.txt" ".env")
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: $file not found${NC}"
        exit 1
    fi
done

# Create remote directory if it doesn't exist
echo "Creating remote directory..."
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR"

# Sync files to remote server
echo "Copying files to remote server..."
rsync -avz --exclude 'downloads' --exclude 'logs' --exclude 'data' \
    --exclude '.git' --exclude '__pycache__' \
    ./ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR

# Create required directories on remote server
echo "Creating required directories on remote server..."
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/{downloads,logs,data}"

# Deploy using docker compose
echo "Deploying with docker compose..."
ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && \
    docker compose down && \
    docker compose build --no-cache && \
    docker compose up -d"

# Check if deployment was successful
if ssh $REMOTE_USER@$REMOTE_HOST "docker ps | grep -q $APP_NAME"; then
    echo -e "${GREEN}Deployment successful! Bot is running.${NC}"
    echo "You can check the logs with:"
    echo "ssh $REMOTE_USER@$REMOTE_HOST \"docker logs -f $APP_NAME\""
else
    echo -e "${RED}Deployment might have failed. Please check the logs.${NC}"
    exit 1
fi
