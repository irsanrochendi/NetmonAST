#!/usr/bin/env bash
# ============================================================
# NetMon Health Check Script
# ============================================================
# Checks all containers and services, restarts if needed.
# Designed to be run as a cron job every 5 minutes.
#
# Usage:
#   ./health_check.sh
#   ./health_check.sh --verbose
# ============================================================

set -euo pipefail

COMPOSE_FILE="docker-compose.yml"
LOG_FILE="/var/log/netmon/health_check.log"
VERBOSE=false

# ── Parse args ────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --verbose|-v) VERBOSE=true; shift ;;
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

verbose() {
    $VERBOSE && log "[DEBUG] $1" || true
}

# ── Check Docker Compose containers ───────────────────────────────
check_containers() {
    local failed=0

    local containers=("netmon-db" "netmon-api" "netmon-snmp-poller" "netmon-esxi-poller" "netmon-alert-worker")

    for container in "${containers[@]}"; do
        local status
        status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "not_found")
        local health
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container" 2>/dev/null || echo "unknown")

        if [[ "$status" != "running" ]]; then
            log "⚠️  $container is $status — restarting..."
            docker compose -f "$COMPOSE_FILE" restart "$container"
            failed=$((failed + 1))
        elif [[ "$health" == "unhealthy" ]]; then
            log "⚠️  $container is unhealthy — restarting..."
            docker compose -f "$COMPOSE_FILE" restart "$container"
            failed=$((failed + 1))
        else
            verbose "$container: status=$status health=$health ✅"
        fi
    done

    return $failed
}

# ── Check API endpoint ────────────────────────────────────────────
check_api() {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")

    if [[ "$http_code" != "200" ]]; then
        log "⚠️  API health check failed (HTTP $http_code) — restarting API..."
        docker compose -f "$COMPOSE_FILE" restart api
        return 1
    fi

    verbose "API health check: HTTP $http_code ✅"
    return 0
}

# ── Check database connection ─────────────────────────────────────
check_database() {
    local result
    result=$(docker exec netmon-db pg_isready -U netmon -d netmon 2>/dev/null || echo "not_ready")

    if [[ "$result" != *"accepting connections"* ]]; then
        log "⚠️  Database not accepting connections — restarting..."
        docker compose -f "$COMPOSE_FILE" restart timescaledb
        sleep 10
        return 1
    fi

    verbose "Database: accepting connections ✅"
    return 0
}

# ── Check disk space ──────────────────────────────────────────────
check_disk() {
    local usage
    usage=$(df / | tail -1 | awk '{print $5}' | tr -d '%')

    if [[ "$usage" -gt 90 ]]; then
        log "🔴 Disk usage critical: ${usage}%"
        return 1
    elif [[ "$usage" -gt 80 ]]; then
        log "🟡 Disk usage warning: ${usage}%"
    else
        verbose "Disk usage: ${usage}% ✅"
    fi
    return 0
}

# ── Main ──────────────────────────────────────────────────────────
main() {
    log "── Health check started ──"

    local errors=0

    check_containers || errors=$((errors + 1))
    check_database || errors=$((errors + 1))
    check_api || errors=$((errors + 1))
    check_disk || errors=$((errors + 1))

    if [[ $errors -gt 0 ]]; then
        log "⚠️  Health check completed with $errors issue(s)"
    else
        log "✅ All checks passed"
    fi

    log "── Health check finished ──"
}

main
