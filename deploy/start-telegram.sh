#!/bin/bash
# Quick-start script for VPS Telegram Channel
# Usage: bash start-telegram.sh

export PATH="/root/.bun/bin:$PATH"

cd /root/ombre || exit 1

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Error: TELEGRAM_BOT_TOKEN not set"
    echo "Usage: TELEGRAM_BOT_TOKEN=\"your-token\" bash start-telegram.sh"
    exit 1
fi

exec claude --channels plugin:telegram@claude-plugins-official
