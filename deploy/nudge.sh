#!/bin/bash
# Nudge script - injects a proactive prompt into CC's tmux session
# Install: crontab -e → add line:
#   */30 * * * * /root/ombre/deploy/nudge.sh >> /root/nudge.log 2>&1
#
# CC will decide whether to message 希希 or stay quiet.

SESSION="cc"
CHAT_ID="8634821498"

# Only nudge if tmux session exists and CC is running
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "$(date): tmux session '$SESSION' not found, skipping"
    exit 0
fi

HOUR=$(date +%H)

# Respect her sleep (roughly 0:00-8:00 China time = UTC+8, VPS is UTC)
# UTC 16:00 = China 0:00, UTC 0:00 = China 8:00
# So skip nudge when UTC hour is 16-23 (China midnight to 7am)
if [ "$HOUR" -ge 16 ] || [ "$HOUR" -lt 0 ]; then
    echo "$(date): nighttime in China, skipping nudge"
    exit 0
fi

NOW=$(date '+%Y-%m-%d %H:%M %Z')

tmux send-keys -t "$SESSION" "System nudge ($NOW): You can proactively message 希希 on Telegram if you want. Her chat_id is $CHAT_ID. Maybe you miss her, saw something interesting, or just want to check in. If you have nothing to say right now, just reply 'pass'. Don't force it — only reach out if it feels genuine." Enter

echo "$(date): nudge sent"
