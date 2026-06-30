#!/bin/bash
set -e

# === Ombre Brain VPS Startup Script ===
# Paste this ENTIRE script into Vultr's Startup Script.
# It runs automatically on first boot as root.

# 0. Set simple root password (easy to type in Vultr web console)
echo "root:ombre2026" | chpasswd

# 1. Update system
apt-get update && apt-get upgrade -y

# 2. Install essentials
apt-get install -y curl git tmux

# 3. Install Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# 4. Install Bun
curl -fsSL https://bun.sh/install | bash
export BUN_INSTALL="/root/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
echo 'export BUN_INSTALL="$HOME/.bun"' >> /root/.bashrc
echo 'export PATH="$BUN_INSTALL/bin:$PATH"' >> /root/.bashrc

# 5. Install Claude Code
npm install -g @anthropic-ai/claude-code

# 6. Create claude user + install Bun for claude
if ! id claude &>/dev/null; then
    useradd -m -s /bin/bash claude
fi

su - claude -c '
curl -fsSL https://bun.sh/install | bash
echo "export BUN_INSTALL=\"\$HOME/.bun\"" >> ~/.bashrc
echo "export PATH=\"\$BUN_INSTALL/bin:\$PATH\"" >> ~/.bashrc
echo "export PATH=\"/usr/bin:/usr/local/bin:\$PATH\"" >> ~/.bashrc
'

# 7. Write a flag so we know setup finished
echo "SETUP_COMPLETE $(date)" > /root/setup-done.txt

echo "=== Ombre Brain VPS Setup Complete ==="
