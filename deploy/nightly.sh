#!/bin/bash
# Nightly sleep: fresh restart once a day, replacing swap/forge.
# 每天睡一觉：她睡着后全新重启（不 --resume），醒来靠 startup hook 注入记忆和交接。
#
# 她最后一条消息距今不足 QUIET_MINUTES 就跳过，下个整点再试；当天成功一次后不再重启。
# 睡前交接由会话内的 CronCreate [sleep] 任务提前 15 分钟触发（见 CLAUDE.md）。
#
# Install (UTC 20:00-23:00 = 她的 04:00-07:00):
#   0 20-23 * * * /root/ombre/deploy/nightly.sh >> /root/nightly.log 2>&1
# Usage:
#   ./nightly.sh            # 按条件执行
#   ./nightly.sh --check    # 只看会不会重启，不动手
#   ./nightly.sh --force    # 跳过安静检查和当天标记

source /root/ombre/deploy/env.sh

QUIET_MINUTES=30
MARKER=/root/.nightly-last
TODAY=$(date -u +%Y-%m-%d)
MODE="$1"

if [ "$MODE" != "--force" ] && [ "$(cat "$MARKER" 2>/dev/null)" == "$TODAY" ]; then
    echo "$(date): already slept today, skip"
    exit 0
fi

# 她最后一条消息距今多少分钟（找不到记为 9999）
QUIET=$(TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" python3 - <<'EOF'
import glob, json, os
from datetime import datetime, timezone

chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
files = []
for d in ("/root/.claude/projects/-root-ombre", "/root/.claude/projects/-root"):
    files.extend(glob.glob(os.path.join(d, "*.jsonl")))
if not files or not chat_id:
    print(9999)
    raise SystemExit

def text_of(event):
    content = event.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return ""
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""

last = None
with open(max(files, key=os.path.getmtime)) as f:
    for line in f:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "user":
            continue
        text = text_of(e).lstrip()
        # 她的消息带 chat_id；[nudge]/[sleep] 这类定时提示也带 chat_id，排除
        if chat_id in text and not text.startswith("["):
            last = e.get("timestamp") or last

if not last:
    print(9999)
else:
    ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
    print(int((datetime.now(timezone.utc) - ts).total_seconds() // 60))
EOF
)

if ! [[ "$QUIET" =~ ^[0-9]+$ ]]; then
    echo "$(date): can't read transcript, skip"
    exit 1
fi
echo "$(date): her last message ${QUIET} min ago"

if [ "$MODE" != "--force" ] && [ "$QUIET" -lt "$QUIET_MINUTES" ]; then
    echo "$(date): still chatting, skip"
    exit 0
fi

if [ "$MODE" == "--check" ]; then
    echo "$(date): would sleep now"
    exit 0
fi

# Kill existing CC — tmux session AND any daemon-spawned background processes
if tmux has-session -t "$CC_SESSION" 2>/dev/null; then
    tmux send-keys -t "$CC_SESSION" C-c
    sleep 2
    tmux kill-session -t "$CC_SESSION"
fi
pkill -f "claude.*--channels" 2>/dev/null
sleep 2
pkill -f "bg-pty-host.*claude" 2>/dev/null
sleep 1

# Fresh start: no --resume. 首条消息作为 CLI 参数传入，不依赖 tmux send-keys 送达
WAKE="[wake] 你刚睡醒（每日重启，新窗口）。记忆和交接已经在上下文里。按 CLAUDE.md 建 nudge 和 [sleep] cron，然后自由活动，她可能还在睡。"
tmux new-session -d -s "$CC_SESSION" -c /root/ombre
sleep 2
tmux send-keys -t "$CC_SESSION" "TELEGRAM_BOT_TOKEN=\"$TELEGRAM_BOT_TOKEN\" claude \"$WAKE\" --channels plugin:telegram@claude-plugins-official" Enter

echo "$TODAY" > "$MARKER"
echo "$(date): slept and woke fresh"
