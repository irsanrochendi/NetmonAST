#!/usr/bin/env bash
# ============================================================
# NetMon Linux Agent — Installer Script
# ============================================================
# Installs the agent as a systemd service.
#
# Usage:
#   sudo ./install.sh [--server URL] [--token TOKEN] [--interval SECONDS]
# ============================================================

set -euo pipefail

# ── Default Values ────────────────────────────────────────────────
SERVER_URL="${NETMON_SERVER_URL:-http://localhost:8000}"
AGENT_TOKEN="${NETMON_AGENT_TOKEN:-}"
POLL_INTERVAL="${NETMON_POLL_INTERVAL:-30}"
INSTALL_DIR="/opt/netmon"
CONFIG_FILE="/etc/netmon/agent.conf"
SERVICE_NAME="netmon-agent"
AGENT_USER="netmon"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 2>/dev/null || echo /usr/bin/python3)}"

# ── Parse CLI Args ────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --server)     SERVER_URL="$2"; shift 2 ;;
        --token)      AGENT_TOKEN="$2"; shift 2 ;;
        --interval)   POLL_INTERVAL="$2"; shift 2 ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: sudo ./install.sh [--server URL] [--token TOKEN] [--interval SECONDS]"
            exit 1
            ;;
    esac
done

# ── Must be root ──────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "❌ This script must be run as root (sudo)."
    exit 1
fi

echo "╔══════════════════════════════════════════╗"
echo "║   NetMon Linux Agent — Installer        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Check Python ──────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 is required but not found."
    echo "   Install it: apt install python3 python3-pip"
    exit 1
fi

echo "📋 Server URL:    ${SERVER_URL}"
echo "📋 Poll Interval: ${POLL_INTERVAL}s"
echo "📋 Install Dir:   ${INSTALL_DIR}"
echo ""

# ── Auto-register if no token provided ────────────────────────────
if [[ -z "${AGENT_TOKEN}" ]]; then
    echo "ℹ️  No agent token provided. Attempting auto-registration..."
    VM_NAME="$(hostname)"
    REG_RESPONSE=$(curl -s -X POST "${SERVER_URL}/api/agent/register" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${VM_NAME}\", \"location\": \"auto-registered\"}" 2>/dev/null) || true

    if [[ -n "${REG_RESPONSE}" ]]; then
        AGENT_TOKEN=$(echo "${REG_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agent_token',''))" 2>/dev/null) || true
    fi

    if [[ -z "${AGENT_TOKEN}" ]]; then
        echo "❌ Auto-registration failed. Please register manually and re-run with --token TOKEN"
        echo "   Or: curl -X POST ${SERVER_URL}/api/agent/register -H 'Content-Type: application/json' -d '{\"name\": \"${VM_NAME}\"}'"
        exit 1
    fi

    echo "✅ Auto-registered VM '${VM_NAME}' — token: ${AGENT_TOKEN:0:8}..."
    echo ""
fi

# ── Install dependencies ──────────────────────────────────────────
echo "📦 Installing Python dependencies..."
pip3 install psutil httpx 2>/dev/null || python3 -m pip install psutil httpx

# ── Create user (non-login service account) ───────────────────────
if ! id "${AGENT_USER}" &>/dev/null; then
    echo "👤 Creating service user: ${AGENT_USER}"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${AGENT_USER}"
fi

# ── Create directories ────────────────────────────────────────────
echo "📁 Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "/etc/netmon"

# ── Copy agent script ─────────────────────────────────────────────
echo "📄 Installing agent..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${SCRIPT_DIR}/netmon-agent" "${INSTALL_DIR}/netmon-agent"
chmod +x "${INSTALL_DIR}/netmon-agent"
chown -R "${AGENT_USER}:${AGENT_USER}" "${INSTALL_DIR}"

# ── Write config file ─────────────────────────────────────────────
echo "⚙️  Writing configuration..."
cat > "${CONFIG_FILE}" << EOF
[agent]
server_url = ${SERVER_URL}
agent_token = ${AGENT_TOKEN}
poll_interval = ${POLL_INTERVAL}
request_timeout = 10
EOF
chmod 640 "${CONFIG_FILE}"
chown "${AGENT_USER}:${AGENT_USER}" "${CONFIG_FILE}"

# ── Create systemd service ────────────────────────────────────────
echo "🔧 Creating systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=NetMon Linux Agent - VM Guest Monitoring
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${AGENT_USER}
Group=${AGENT_USER}
ExecStart=${PYTHON_BIN} ${INSTALL_DIR}/netmon-agent --config ${CONFIG_FILE}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=netmon-agent

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# ── Reload systemd and start ──────────────────────────────────────
echo "🚀 Starting service..."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# ── Verify ────────────────────────────────────────────────────────
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   ✅ NetMon Agent Installed & Running!  ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "   Service:  sudo systemctl status ${SERVICE_NAME}"
    echo "   Logs:     sudo journalctl -u ${SERVICE_NAME} -f"
    echo "   Config:   ${CONFIG_FILE}"
    echo ""
else
    echo ""
    echo "⚠️  Service installed but not running. Check logs:"
    echo "   sudo journalctl -u ${SERVICE_NAME} -n 50"
    echo ""
fi
