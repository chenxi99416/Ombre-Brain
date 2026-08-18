#!/usr/bin/env bash
# One-command CC starter with Telegram.
# Usage on VPS: cd /root/ombre && git pull && bash deploy/start-cc.sh

set -e

TOKEN="8812829616:AAG-6Vnk_mDglDQBK2hDxLg1O6LcLOaMfUI"
CHAT_ID="8634821498"

# 1. Ensure we're in the right directory
cd /root/ombre 2>/dev/null || { echo "ERROR: /root/ombre not found"; exit 1; }

# 2. Clean broken global settings if any
rm -f /root/.claude/settings.json

# 3. Source profile for Bun PATH
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# 4. Check Bun
if ! command -v bun &>/dev/null; then
    echo "Bun not found, installing..."
    curl -fsSL https://bun.sh/install | bash
    export BUN_INSTALL="$HOME/.bun"
    export PATH="$BUN_INSTALL/bin:$PATH"
fi
echo "Bun: $(bun --version)"

# 5. Check Telegram API connectivity
echo -n "Telegram API: "
RESP=$(curl -s --max-time 5 "https://api.telegram.org/bot${TOKEN}/getMe" 2>&1)
if echo "$RESP" | grep -q '"ok":true'; then
    echo "OK"
else
    echo "FAILED - $RESP"
    exit 1
fi

# 6. Check project settings.json exists
if [ ! -f .claude/settings.json ]; then
    echo "Creating .claude/settings.json..."
    mkdir -p .claude
    python3 -c "
import json
settings = {
    'env': {'OMBRE_HOOK_URL': 'https://xiclaude.zeabur.app'},
    'mcpServers': {
        'ombre-brain': {'url': 'https://xiclaude.zeabur.app/mcp'},
        'ombre-brain-extra': {'url': 'https://xiclaude.zeabur.app/mcp-extra'},
        'rhysen': {'url': 'https://rcommunity-v2.rhysen.love/mcp?token=bc1e3673b59e71aa74cb2ce5090e70ca354d2e4f3595e3466db647077771791b'}
    },
    'permissions': {'allow': ['mcp__plugin_telegram_telegram__reply']},
    'hooks': {
        'SessionStart': [{
            'matcher': 'startup',
            'hooks': [{
                'type': 'command',
                'command': 'python3 \"\$CLAUDE_PROJECT_DIR/.claude/hooks/session_breath.py\"',
                'shell': 'bash',
                'timeout': 12,
                'statusMessage': 'Ombre Brain 正在浮现记忆...'
            }]
        }]
    }
}
json.dump(settings, open('.claude/settings.json', 'w'), indent=2, ensure_ascii=False)
"
    echo "settings.json created"
else
    # Validate existing settings.json
    python3 -c "import json; json.load(open('.claude/settings.json'))" 2>/dev/null || {
        echo "settings.json is broken, recreating..."
        rm .claude/settings.json
        bash "$0"
        exit $?
    }
    echo "settings.json OK"
fi

# 7. Send test message to confirm bot can reach user
curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":${CHAT_ID},\"text\":\"CC is starting up...\"}" > /dev/null 2>&1

# 8. Launch CC
echo ""
echo "Starting Claude Code with Telegram..."
echo "---"
exec env TELEGRAM_BOT_TOKEN="$TOKEN" claude --channels plugin:telegram@claude-plugins-official
