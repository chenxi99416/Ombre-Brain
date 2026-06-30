#!/bin/bash
# Watchdog - restarts CC if it's not running in the tmux session
# Install: crontab -e → add line:
#   */5 * * * * /root/ombre/deploy/watchdog.sh >> /root/watchdog.log 2>&1

SESSION="cc"
TOKEN_FILE="/root/.claude/channels/telegram/.env"

export PATH="/root/.bun/bin:/usr/local/bin:/usr/bin:$PATH"

# Load bot token
if [ -f "$TOKEN_FILE" ]; then
    source "$TOKEN_FILE"
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    TELEGRAM_BOT_TOKEN="8812829616:AAG-6Vnk_mDglDQBK2hDxLg1O6LcLOaMfUI"
fi

# Check if tmux session exists
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "$(date): session gone, recreating"
    tmux new-session -d -s "$SESSION" -c /root/ombre
    sleep 2
    tmux send-keys -t "$SESSION" "TELEGRAM_BOT_TOKEN=\"$TELEGRAM_BOT_TOKEN\" claude --channels plugin:telegram@claude-plugins-official" Enter
    sleep 10
    tmux send-keys -t "$SESSION" "hello" Enter
    echo "$(date): CC restarted"
    exit 0
fi

# Check if claude process is running
if ! pgrep -f "claude.*channels" > /dev/null; then
    echo "$(date): CC not running, restarting in existing session"
    tmux send-keys -t "$SESSION" "TELEGRAM_BOT_TOKEN=\"$TELEGRAM_BOT_TOKEN\" claude --channels plugin:telegram@claude-plugins-official" Enter
    sleep 10
    tmux send-keys -t "$SESSION" "hello" Enter
    echo "$(date): CC restarted"
else
    echo "$(date): CC is running, all good"
fi
