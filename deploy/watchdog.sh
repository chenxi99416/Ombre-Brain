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
    echo "$(date): CC is running, all good"
fi
