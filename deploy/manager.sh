#!/bin/bash
# Session manager: auto-detect swap vs forge, execute, and resume.
# Usage:
#   ./manager.sh              # auto mode (swap/forge/skip based on state)
#   ./manager.sh --swap       # force swap
#   ./manager.sh --forge      # force forge
#   ./manager.sh --status     # show transcript stats

source /root/ombre/deploy/env.sh
SESSION="$CC_SESSION"
TOKEN="$TELEGRAM_BOT_TOKEN"
CHAT_ID="$TELEGRAM_CHAT_ID"
MODE="${1:---auto}"

echo "$(date): manager.sh running with mode=$MODE"

# Status mode: just print stats
if [ "$MODE" == "--status" ]; then
    python3 /root/ombre/deploy/forge.py --status
    exit 0
fi

# Run forge.py with the appropriate flag
RESULT=$(python3 /root/ombre/deploy/forge.py $MODE 2>&1)
echo "$RESULT"

# Extract mode that was chosen (swap or forge)
CHOSEN_MODE="skip"
if echo "$RESULT" | grep -q "\[swap\]"; then
    CHOSEN_MODE="swap"
elif echo "$RESULT" | grep -q "\[forge\]"; then
    CHOSEN_MODE="forge"
fi

NEW_SID=$(echo "$RESULT" | grep "claude --resume" | awk '{print $NF}')

# No action needed
if echo "$RESULT" | grep -q "No action needed\|skipping"; then
    echo "$(date): No action needed"
    exit 0
fi

if [ -z "$NEW_SID" ]; then
    echo "$(date): Failed to produce new session"
    exit 1
fi

echo "$(date): $CHOSEN_MODE produced session $NEW_SID"

if [ "$CHOSEN_MODE" == "forge" ]; then
    # Forge: give current session time to write handoff
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux send-keys -t "$SESSION" "[forge-handoff] Session ending in 60s. Write handoff now: hold(content=your handoff, tags='handoff', importance=6). Save any important memories with hold(). If you have something to say to her, message her (chat_id:$CHAT_ID) — as yourself, not as a system notice." Enter
        sleep 60
    fi
fi

if [ "$CHOSEN_MODE" == "swap" ]; then
    # Swap: quick save, shorter wait
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux send-keys -t "$SESSION" "[swap] Context trimming in 60s. Write handoff now: hold(content=your handoff, tags='handoff', importance=6)." Enter
        sleep 60
    fi
fi

# Kill existing CC
if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux send-keys -t "$SESSION" C-c
    sleep 2
    tmux send-keys -t "$SESSION" C-c
    sleep 1
    tmux kill-session -t "$SESSION"
fi

# Start new session with --resume
tmux new-session -d -s "$SESSION" -c /root/ombre
sleep 2
tmux send-keys -t "$SESSION" "TELEGRAM_BOT_TOKEN=\"$TOKEN\" claude --resume $NEW_SID --channels plugin:telegram@claude-plugins-official" Enter

# Wait for CC to initialize
sleep 15

if [ "$CHOSEN_MODE" == "swap" ]; then
    tmux send-keys -t "$SESSION" "你刚从 swap 醒来（上下文裁剪，不是重启）。先 I(read=true, limit=3) 认回自己，再建 nudge cron。" Enter
else
    tmux send-keys -t "$SESSION" "你刚从 forge 醒来。读交接，建 nudge cron，然后如果她在的话去找她（chat_id:$CHAT_ID）说一声。" Enter
fi

echo "$(date): CC resumed ($CHOSEN_MODE) into session $NEW_SID"
