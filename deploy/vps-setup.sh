#!/bin/bash
set -e

echo "=== Ombre Brain VPS Setup ==="
echo "Installing Node.js, Bun, Claude Code, tmux..."

# 1. Update system
apt-get update && apt-get upgrade -y

# 2. Install essentials + tmux
apt-get install -y curl git tmux

# 3. Install Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
echo "Node.js $(node -v) installed"

# 4. Install Bun
curl -fsSL https://bun.sh/install | bash
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
echo 'export BUN_INSTALL="$HOME/.bun"' >> ~/.bashrc
echo 'export PATH="$BUN_INSTALL/bin:$PATH"' >> ~/.bashrc
echo "Bun installed"

# 5. Install Claude Code
npm install -g @anthropic-ai/claude-code
echo "Claude Code installed"

# 6. Create claude user
if ! id claude &>/dev/null; then
    useradd -m -s /bin/bash claude
    echo "User 'claude' created"
fi

# Copy Node/Bun/CC to claude user PATH
su - claude -c '
curl -fsSL https://bun.sh/install | bash
echo "export BUN_INSTALL=\"\$HOME/.bun\"" >> ~/.bashrc
echo "export PATH=\"\$BUN_INSTALL/bin:\$PATH\"" >> ~/.bashrc
echo "export PATH=\"/usr/bin:/usr/local/bin:\$PATH\"" >> ~/.bashrc
'

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "1. Switch to claude user:  su - claude"
echo "2. Login to Claude:        claude login"
echo "   (choose 'Claude account with subscription', open the link in your browser)"
echo "3. Start tmux:             tmux new -s cc"
echo "4. Start CC with TG:      TELEGRAM_BOT_TOKEN=\"your-token\" claude --channels telegram@claude-plugins-official"
echo "5. Detach tmux:            Ctrl+B then D"
echo ""
echo "To reattach later:         tmux attach -t cc"
