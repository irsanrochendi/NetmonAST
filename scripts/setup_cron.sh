#!/usr/bin/env bash
# ============================================================
# NetMon Cron Setup
# ============================================================
# Installs cron jobs for health check and database backup.
#
# Usage:
#   sudo ./setup_cron.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_USER="${USER}"

echo "╔══════════════════════════════════════════╗"
echo "║   NetMon Cron Setup                     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Make scripts executable
chmod +x "${SCRIPT_DIR}/health_check.sh"
chmod +x "${SCRIPT_DIR}/backup_db.sh"

# Create necessary directories
sudo mkdir -p /var/log/netmon
sudo mkdir -p /var/backups/netmon
sudo chown -R "${CRON_USER}:${CRON_USER}" /var/log/netmon
sudo chown -R "${CRON_USER}:${CRON_USER}" /var/backups/netmon

# Create cron entries
CRON_CONTENT="# NetMon — Health check (every 5 minutes)
*/5 * * * * ${SCRIPT_DIR}/health_check.sh >> /var/log/netmon/health_check.log 2>&1

# NetMon — Database backup (daily at 2 AM)
0 2 * * * ${SCRIPT_DIR}/backup_db.sh --retain 30 >> /var/log/netmon/backup.log 2>&1
"

# Install cron
echo "$CRON_CONTENT" | crontab -

echo "✅ Cron jobs installed:"
echo ""
echo "  Health check : Every 5 minutes"
echo "  DB Backup    : Daily at 2:00 AM (30-day retention)"
echo ""
echo "  Logs: /var/log/netmon/"
echo "  Backups: /var/backups/netmon/"
echo ""
echo "View crontab: crontab -l"
echo "Remove:       crontab -r"
