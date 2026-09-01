#!/bin/bash
# Watchdog - restarts CC if it's not running in the tmux session
# Install: crontab -e → */5 * * * * /root/ombre/deploy/watchdog.sh >> /root/watchdog.log 2>&1

source /root/ombre/deploy/env.sh

find_latest_session() {
    local latest=""
    for dir in /root/.claude/projects/-root-ombre /root/.claude/projects/-root; do
        if [ -d "$dir" ]; then
            local candidate
            candidate=$(ls -t "$dir"/*.jsonl 2>/dev/null | head -1)
            if [ -n "$candidate" ]; then
                if [ -z "$latest" ] || [ "$candidate" -nt "$latest" ]; then
                    latest="$candidate"
                fi
            fi
        fi
    done
    if [ -n "$latest" ]; then
        basename "$latest" .jsonl
    fi
}

start_cc() {
    local resume_flag=""
    local sid
    sid=$(find_latest_session)
    if [ -n "$sid" ]; then
        resume_flag="--resume $sid"
        echo "$(date): resuming session $sid"
    else
        echo "$(date): no session to resume, starting fresh"
    fi

    if ! tmux has-session -t "$CC_SESSION" 2>/dev/null; then
        tmux new-session -d -s "$CC_SESSION" -c /root/ombre
        sleep 2
    fi

    tmux send-keys -t "$CC_SESSION" "TELEGRAM_BOT_TOKEN=\"$TELEGRAM_BOT_TOKEN\" claude $resume_flag --channels plugin:telegram@claude-plugins-official" Enter
    echo "$(date): CC started"
}

# Check if tmux session exists and CC is running
if ! tmux has-session -t "$CC_SESSION" 2>/dev/null; then
    echo "$(date): session gone, recreating"
    start_cc
    exit 0
fi

if ! pgrep -f "claude.*channels" > /dev/null; then
    echo "$(date): CC not running, restarting"
    start_cc
else
    # Check liveness: transcript should be modified within last 30 min
    # if there are pending telegram messages
    STALE_MINUTES=30
    LATEST_JSONL=$(ls -t /root/.claude/projects/-root-ombre/*.jsonl 2>/dev/null | head -1)
    if [ -n "$LATEST_JSONL" ]; then
        MTIME=$(stat -c %Y "$LATEST_JSONL" 2>/dev/null)
        NOW=$(date +%s)
        AGE_MIN=$(( (NOW - MTIME) / 60 ))
        if [ "$AGE_MIN" -gt "$STALE_MINUTES" ]; then
            source /root/ombre/deploy/env.sh
            PENDING=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['pending_update_count'])" 2>/dev/null)
            if [ -n "$PENDING" ] && [ "$PENDING" -gt 0 ] 2>/dev/null; then
                echo "$(date): CC zombie detected (transcript stale ${AGE_MIN}min, ${PENDING} pending msgs). Killing and restarting."
                pkill -f "claude.*channels" 2>/dev/null
                sleep 3
                pkill -9 -f "claude.*channels" 2>/dev/null
                sleep 2
                # Also kill any bg-pty-host leftovers
                pkill -f "bg-pty-host" 2>/dev/null
                sleep 1
                if tmux has-session -t "$CC_SESSION" 2>/dev/null; then
                    tmux kill-session -t "$CC_SESSION"
                fi
                start_cc
                exit 0
            fi
        fi
    fi
    echo "$(date): CC is running, all good"
fi
