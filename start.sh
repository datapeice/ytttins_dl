#!/bin/bash
set -e

echo "[INIT] Using external Cobalt worker: ${COBALT_API_URL}"
echo "[INIT] Starting Telegram bot..."

# Start bot directly (foreground, no trap needed)
exec python main.py
