#!/bin/bash
# ============================================================
#  WHALE-STREAM Server Setup Script
#  Run this ONCE on a fresh Ubuntu 22.04 VPS as root
#  Usage: bash setup_server.sh
# ============================================================

set -e   # stop on any error

REPO_URL="https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME.git"
APP_DIR="/opt/whalestream"
PYTHON="python3.11"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   WHALE-STREAM Server Setup                  ║"
echo "║   Ubuntu 22.04 — Python 3.11 — cron         ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Step 1: Update system ──────────────────────────────────
echo "[1/7] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
echo "      ✓ System updated"

# ── Step 2: Install Python 3.11 ───────────────────────────
echo "[2/7] Installing Python 3.11..."
apt-get install -y -qq python3.11 python3.11-venv python3-pip git curl
echo "      ✓ Python 3.11 installed"
python3.11 --version

# ── Step 3: Clone the repo ────────────────────────────────
echo "[3/7] Cloning repo from GitHub..."
if [ -d "$APP_DIR" ]; then
    echo "      Directory exists — pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
echo "      ✓ Code at $APP_DIR"

# ── Step 4: Install Python packages ───────────────────────
echo "[4/7] Installing Python dependencies..."
cd "$APP_DIR"
pip install -r requirements.txt --quiet
echo "      ✓ Dependencies installed"

# ── Step 5: Create logs directory ─────────────────────────
echo "[5/7] Creating logs directory..."
mkdir -p "$APP_DIR/logs"
echo "      ✓ Logs dir ready at $APP_DIR/logs"

# ── Step 6: Set timezone to Bangkok ───────────────────────
echo "[6/7] Setting server timezone to Bangkok (UTC+7)..."
timedatectl set-timezone Asia/Bangkok
echo "      ✓ Timezone: $(timedatectl | grep 'Time zone')"

# ── Step 7: Reminder — secrets needed ─────────────────────
echo "[7/7] Almost done! Two manual steps remain:"
echo ""
echo "  A) Create /opt/whalestream/local_config.py with your API keys"
echo "     (See CLOUD_MIGRATION_GUIDE.md → Step 5)"
echo ""
echo "  B) Upload google_credentials.json:"
echo "     Run this on your Windows PC (PowerShell):"
echo "     scp C:\Users\MAX\WhaleStream\google_credentials.json root@YOUR_SERVER_IP:/opt/whalestream/"
echo ""
echo "  C) Install cron jobs:"
echo "     crontab /opt/whalestream/whale_crontab.txt"
echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete! Do steps A, B, C above then"
echo "  test with: cd /opt/whalestream && python3.11 whale_stream_strategist.py"
echo "══════════════════════════════════════════════"
