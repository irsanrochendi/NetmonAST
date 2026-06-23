#!/usr/bin/env bash
# ============================================================
# NetMon Database Backup Script
# ============================================================
# Performs pg_dump of the NetMon TimescaleDB database.
# Designed to be run as a cron job daily.
#
# Usage:
#   ./backup_db.sh
#   ./backup_db.sh --retain 30  # Keep 30 days of backups
# ============================================================

set -euo pipefail

BACKUP_DIR="/var/backups/netmon"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/netmon_${DATE}.sql.gz"
LOG_FILE="/var/log/netmon/backup.log"

# ── Parse args ────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --retain) RETENTION_DAYS="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$msg" >> "$LOG_FILE"
}

# ── Pre-checks ────────────────────────────────────────────────────
if ! docker ps | grep -q "netmon-db"; then
    log "🔴 ERROR: netmon-db container is not running. Aborting backup."
    exit 1
fi

# ── Create backup ─────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

log "📦 Starting database backup..."

docker exec netmon-db pg_dump -U netmon -d netmon --clean --if-exists \
    | gzip > "$BACKUP_FILE"

local_size=$(du -h "$BACKUP_FILE" | cut -f1)
log "✅ Backup completed: $BACKUP_FILE ($local_size)"

# ── Cleanup old backups ───────────────────────────────────────────
log "🧹 Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "netmon_*.sql.gz" -mtime "+$RETENTION_DAYS" -delete
remaining=$(find "$BACKUP_DIR" -name "netmon_*.sql.gz" | wc -l)
log "📁 $remaining backup(s) remaining in $BACKUP_DIR"

log "── Backup finished ──"
