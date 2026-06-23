#!/usr/bin/env bash
# ============================================================
# NetMon Linux Agent — Uninstaller
# Usage: sudo ./uninstall.sh
# ============================================================

set -euo pipefail

SERVICE_NAME="netmon-agent"
INSTALL_DIR="/opt/netmon"
CONFIG_FILE="/etc/netmon/agent.conf"
AGENT_USER="netmon"

if [[ $EUID -ne 0 ]]; then
    echo "❌ Run as root: sudo ./uninstall.sh"
    exit 1
fi

echo "🗑️  Uninstalling NetMon Agent..."

# Stop and disable service
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

# Remove files
rm -rf "${INSTALL_DIR}"
rm -f "${CONFIG_FILE}"

# Remove user
if id "${AGENT_USER}" &>/dev/null; then
    userdel "${AGENT_USER}" 2>/dev/null || true
fi

echo "✅ NetMon Agent uninstalled."
