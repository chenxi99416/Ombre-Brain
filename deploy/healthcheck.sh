#!/bin/bash
# Health check script - auto-alerts via Telegram if something's wrong
# Run via cron or manually. Checks: bun, telegram, memory, disk, claude process.

source /root/ombre/deploy/env.sh
ALERT_PREFIX="[健康检查]"

send_alert() {
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="${ALERT_PREFIX} $1" > /dev/null 2>&1
}

ISSUES=""

# 0. Check bun — auto-recover if missing
if ! command -v bun &>/dev/null && [ ! -f /root/.bun/bin/bun ]; then
    echo "$(date): bun missing, reinstalling..."
    curl -fsSL https://bun.sh/install | bash 2>/dev/null
    export PATH="/root/.bun/bin:$PATH"
    if command -v bun &>/dev/null || [ -f /root/.bun/bin/bun ]; then
        send_alert "bun 消失后自动装回来了"
        echo "$(date): bun reinstalled"
    else
        ISSUES="${ISSUES}\n- bun 装不回来，telegram 插件跑不起来"
    fi
fi

# 1. Check telegram polling
PENDING=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['pending_update_count'])" 2>/dev/null)
if [ -n "$PENDING" ] && [ "$PENDING" -gt 3 ] 2>/dev/null; then
    ISSUES="${ISSUES}\n- telegram 有 ${PENDING} 条消息堆积，poller 可能没在消费"
fi

# 2. Check memory (alert if available < 100M)
AVAIL_MEM=$(free -m | awk '/Mem/{print $7}')
if [ -n "$AVAIL_MEM" ] && [ "$AVAIL_MEM" -lt 100 ] 2>/dev/null; then
    ISSUES="${ISSUES}\n- 内存不足：可用 ${AVAIL_MEM}M"
fi

# 3. Check disk (alert if usage > 90%)
DISK_PCT=$(df /root | tail -1 | awk '{print $5}' | tr -d '%')
if [ -n "$DISK_PCT" ] && [ "$DISK_PCT" -gt 90 ] 2>/dev/null; then
    ISSUES="${ISSUES}\n- 磁盘使用率 ${DISK_PCT}%"
fi

# 4. Check claude process — alive AND responsive
if ! pgrep -f "claude.exe" > /dev/null; then
    ISSUES="${ISSUES}\n- claude 进程不在了"
else
    # Check for zombie: process alive but transcript stale while messages pending
    LATEST_JSONL=$(ls -t /root/.claude/projects/-root-ombre/*.jsonl 2>/dev/null | head -1)
    if [ -n "$LATEST_JSONL" ]; then
        MTIME=$(stat -c %Y "$LATEST_JSONL" 2>/dev/null)
        NOW=$(date +%s)
        AGE_MIN=$(( (NOW - MTIME) / 60 ))
        if [ "$AGE_MIN" -gt 30 ] && [ -n "$PENDING" ] && [ "$PENDING" -gt 0 ] 2>/dev/null; then
            ISSUES="${ISSUES}\n- claude 进程疑似僵尸（transcript ${AGE_MIN}分钟没更新，${PENDING} 条消息堆积）"
        fi
    fi
fi

if [ -n "$ISSUES" ]; then
    send_alert "$(echo -e "发现问题：${ISSUES}")"
    echo "$(date): ALERT sent"
    exit 1
else
    echo "$(date): all clear"
    exit 0
fi
