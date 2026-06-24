#!/bin/bash
# NetMon Deployment Script for 10.78.78.13
# Run via: sshpass -p 'P@ssw0rd' ssh netmonast@10.78.78.13 'bash -s' < ssh_setup.sh

set -e

echo "╔══════════════════════════════════════════╗"
echo "║   NetMon AST — Auto Deploy              ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Check if running as root or with sudo ──────────────────────────
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

# ── Step 1: Install Docker ─────────────────────────────────────────
echo "📦 Step 1: Installing Docker..."

# Check if Docker already installed
if command -v docker &> /dev/null; then
    echo "   Docker already installed: $(docker --version)"
else
    # Update
    $SUDO apt update -y

    # Prerequisites
    $SUDO apt install -y ca-certificates curl gnupg lsb-release apt-transport-https

    # Docker GPG key
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

    # Docker repo
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install
    $SUDO apt update -y
    $SUDO apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # Add user to docker group
    $SUDO usermod -aG docker $USER

    # Enable & start
    $SUDO systemctl enable docker
    $SUDO systemctl start docker

    echo "   ✅ Docker installed: $(docker --version)"
fi

# Verify Docker Compose
docker compose version
echo "   ✅ Docker Compose OK"
echo ""

# ── Step 2: Clone Repo ─────────────────────────────────────────────
echo "📥 Step 2: Cloning NetmonAST..."

if [ -d "$HOME/NetmonAST" ]; then
    echo "   Directory exists, pulling latest..."
    cd ~/NetmonAST
    git pull origin main
else
    cd ~
    git clone git@github.com:irsanrochendi/NetmonAST.git
    cd NetmonAST
fi

echo "   ✅ Repo ready at ~/NetmonAST"
echo ""

# ── Step 3: Setup Environment ──────────────────────────────────────
echo "⚙️  Step 3: Setting up environment..."

if [ ! -f ".env" ]; then
    cp .env.example .env

    # Generate secure values
    DB_PASS=$(openssl rand -hex 16)
    SECRET=$(openssl rand -hex 32)

    # Update .env
    sed -i "s/netmon_strong_password_here/$DB_PASS/" .env
    sed -i "s/change_me_use_openssl_rand_hex_32/$SECRET/" .env

    echo "   ✅ .env created with secure passwords"
    echo "   DB_PASSWORD: $DB_PASS"
    echo "   SECRET_KEY: $SECRET"
else
    echo "   .env already exists, keeping current config"
fi
echo ""

# ── Step 4: Open Firewall ──────────────────────────────────────────
echo "🔥 Step 4: Configuring firewall..."

if command -v ufw &> /dev/null; then
    $SUDO ufw allow OpenSSH
    $SUDO ufw allow 8000/tcp  # API
    $SUDO ufw allow 3000/tcp  # Dashboard
    $SUDO ufw --force enable
    $SUDO ufw status
    echo "   ✅ Firewall configured"
else
    echo "   ⚠️  UFW not installed, skipping firewall"
fi
echo ""

# ── Step 5: Build & Run ────────────────────────────────────────────
echo "🚀 Step 5: Building and starting NetMon..."

docker compose down 2>/dev/null || true
docker compose up -d --build

echo "   Waiting for containers to start..."
sleep 15

# ── Step 6: Verify ─────────────────────────────────────────────────
echo ""
echo "🔍 Step 6: Verification..."
echo ""

docker compose ps
echo ""

# Health check
HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{"status":"error"}')
echo "API Health: $HEALTH"
echo ""

# Test login
TOKEN_RESP=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -d "username=admin&password=admin123" 2>/dev/null || echo '{"error":"login failed"}')
echo "Login Test: $(echo "$TOKEN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK - Token received' if 'access_token' in d else 'FAILED: ' + str(d))" 2>/dev/null || echo "$TOKEN_RESP")"
echo ""

# ── Summary ────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ NetMon AST Deployed Successfully!   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "   🌐 API Docs  : http://$IP:8000/docs"
echo "   📊 Dashboard : http://$IP:3000"
echo "   🔑 Login     : admin / admin123"
echo ""
