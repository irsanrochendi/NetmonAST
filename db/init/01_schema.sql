-- ============================================================
-- NetMon Database Schema
-- TimescaleDB (PostgreSQL 16)
-- ============================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- 1. DEVICES
-- ============================================================
CREATE TYPE device_type AS ENUM ('mikrotik', 'esxi', 'vm_guest');
CREATE TYPE device_status AS ENUM ('UP', 'DOWN', 'UNKNOWN');

CREATE TABLE devices (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    device_type     device_type NOT NULL,
    ip_address      INET,
    -- Mikrotik SNMP
    snmp_community  VARCHAR(128),
    snmp_version    VARCHAR(8) DEFAULT '2c',
    snmp_port       INTEGER DEFAULT 161,
    -- ESXi
    esxi_username   VARCHAR(128),
    esxi_password   VARCHAR(256),  -- encrypted at application layer
    esxi_port       INTEGER DEFAULT 443,
    -- VM guest
    agent_token     VARCHAR(64) UNIQUE,
    -- Meta
    location        VARCHAR(256),
    description     TEXT,
    poll_interval   INTEGER DEFAULT 60,  -- seconds
    status          device_status DEFAULT 'unknown',
    last_poll_at    TIMESTAMPTZ,
    last_seen_at    TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_devices_type ON devices(device_type);
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_devices_active ON devices(is_active);

-- ============================================================
-- 2. DEVICE METRICS (TimescaleDB hypertable)
-- ============================================================
CREATE TABLE device_metrics (
    time            TIMESTAMPTZ NOT NULL,
    device_id       INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    metric_name     VARCHAR(64) NOT NULL,  -- cpu_usage, mem_usage, mem_total, uptime, etc.
    metric_value    DOUBLE PRECISION NOT NULL,
    labels          JSONB DEFAULT '{}'     -- extra: interface_name, datastore_name, etc.
);

SELECT create_hypertable('device_metrics', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX idx_metrics_device_time ON device_metrics(device_id, time DESC);
CREATE INDEX idx_metrics_name_time ON device_metrics(metric_name, time DESC);

-- Retention: compress after 7 days, drop after 90 days
SELECT add_retention_policy('device_metrics', INTERVAL '90 days',
    if_not_exists => TRUE);

ALTER TABLE device_metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id, metric_name',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('device_metrics', INTERVAL '7 days',
    if_not_exists => TRUE);

-- ============================================================
-- 3. INTERFACE METRICS (TimescaleDB hypertable)
-- ============================================================
CREATE TABLE interface_metrics (
    time            TIMESTAMPTZ NOT NULL,
    device_id       INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    interface_name  VARCHAR(64) NOT NULL,
    rx_bytes        BIGINT,
    tx_bytes        BIGINT,
    rx_packets      BIGINT,
    tx_packets      BIGINT,
    rx_errors       BIGINT,
    tx_errors       BIGINT,
    rx_rate         DOUBLE PRECISION,  -- bytes/sec calculated
    tx_rate         DOUBLE PRECISION   -- bytes/sec calculated
);

SELECT create_hypertable('interface_metrics', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX idx_ifmetrics_device_time ON interface_metrics(device_id, time DESC);
CREATE INDEX idx_ifmetrics_ifname ON interface_metrics(interface_name);

SELECT add_retention_policy('interface_metrics', INTERVAL '90 days',
    if_not_exists => TRUE);

-- ============================================================
-- 4. ALERT RULES
-- ============================================================
CREATE TYPE severity_level AS ENUM ('info', 'warning', 'critical');

CREATE TABLE alert_rules (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    device_id       INTEGER REFERENCES devices(id) ON DELETE CASCADE,  -- NULL = all devices
    device_type     device_type,  -- NULL = all types
    metric_name     VARCHAR(64) NOT NULL,
    operator        VARCHAR(8) NOT NULL CHECK (operator IN ('>', '<', '>=', '<=', '==', '!=')),
    threshold       DOUBLE PRECISION NOT NULL,
    duration        INTEGER DEFAULT 0,  -- seconds metric must breach before alerting
    severity        severity_level DEFAULT 'warning',
    enabled         BOOLEAN DEFAULT TRUE,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 5. ALERTS
-- ============================================================
CREATE TYPE alert_state AS ENUM ('firing', 'acknowledged', 'resolved');

CREATE TABLE alerts (
    id              SERIAL PRIMARY KEY,
    rule_id         INTEGER NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    device_id       INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    severity        severity_level NOT NULL,
    state           alert_state DEFAULT 'firing',
    metric_name     VARCHAR(64) NOT NULL,
    metric_value    DOUBLE PRECISION NOT NULL,
    threshold       DOUBLE PRECISION NOT NULL,
    message         TEXT,
    acknowledged_by VARCHAR(128),
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_state ON alerts(state);
CREATE INDEX idx_alerts_device ON alerts(device_id);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);

-- ============================================================
-- 6. ALERT NOTIFICATIONS LOG
-- ============================================================
CREATE TABLE alert_notifications (
    id              SERIAL PRIMARY KEY,
    alert_id        INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    channel         VARCHAR(32) NOT NULL CHECK (channel IN ('telegram', 'email')),
    recipient       VARCHAR(256),
    status          VARCHAR(16) DEFAULT 'pending',  -- pending, sent, failed
    error_message   TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 7. ADMIN USERS
-- ============================================================
CREATE TABLE admin_users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(64) UNIQUE NOT NULL,
    email           VARCHAR(128) UNIQUE NOT NULL,
    password_hash   VARCHAR(256) NOT NULL,
    role            VARCHAR(16) DEFAULT 'admin' CHECK (role IN ('admin', 'viewer')),
    is_active       BOOLEAN DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 8. MAINTENANCE WINDOWS
-- ============================================================
CREATE TABLE maintenance_windows (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    device_id       INTEGER REFERENCES devices(id) ON DELETE CASCADE,  -- NULL = all
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- CONTINUOUS AGGREGATES (materialized views)
-- ============================================================

-- 5-minute rollup for device metrics
CREATE MATERIALIZED VIEW IF NOT EXISTS device_metrics_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    device_id,
    metric_name,
    AVG(metric_value) AS avg_value,
    MAX(metric_value) AS max_value,
    MIN(metric_value) AS min_value
FROM device_metrics
GROUP BY bucket, device_id, metric_name
WITH NO DATA;

SELECT add_continuous_aggregate_policy('device_metrics_5min',
    start_offset    => INTERVAL '1 hour',
    end_offset      => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists   => TRUE
);

-- 1-hour rollup
CREATE MATERIALIZED VIEW IF NOT EXISTS device_metrics_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    device_id,
    metric_name,
    AVG(metric_value) AS avg_value,
    MAX(metric_value) AS max_value,
    MIN(metric_value) AS min_value
FROM device_metrics
GROUP BY bucket, device_id, metric_name
WITH NO DATA;

SELECT add_continuous_aggregate_policy('device_metrics_1h',
    start_offset    => INTERVAL '1 day',
    end_offset      => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists   => TRUE
);

-- ============================================================
-- SEED: default admin user (password: admin123 — change immediately!)
-- bcrypt hash of 'admin123'
-- ============================================================
INSERT INTO admin_users (username, email, password_hash, role)
VALUES (
    'admin',
    'admin@netmon.local',
    '$2b$12$LJ3m4ys3Lk0TSwMCfNBP0OqQZ8XJYhSQKcJ8mZ5vR7tKpYwN2eF6i',
    'admin'
) ON CONFLICT (username) DO NOTHING;
