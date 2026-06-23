"""Initial schema — NetMon v1.0

Creates all tables, types, indexes, hypertables, continuous aggregates.
Revision ID: 001_initial_schema
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all NetMon tables and TimescaleDB objects."""

    # ── Create custom types ──────────────────────────────────────────
    op.execute("CREATE TYPE device_type AS ENUM ('mikrotik', 'esxi', 'vm_guest')")
    op.execute("CREATE TYPE device_status AS ENUM ('up', 'down', 'unknown')")
    op.execute("CREATE TYPE severity_level AS ENUM ('info', 'warning', 'critical')")
    op.execute("CREATE TYPE alert_state AS ENUM ('firing', 'acknowledged', 'resolved')")

    # ── Devices ─────────────────────────────────────────────────────
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_type", sa.Enum("mikrotik", "esxi", "vm_guest", name="device_type"), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("snmp_community", sa.String(128), nullable=True),
        sa.Column("snmp_version", sa.String(8), server_default="2c"),
        sa.Column("snmp_port", sa.Integer(), server_default="161"),
        sa.Column("esxi_username", sa.String(128), nullable=True),
        sa.Column("esxi_password", sa.String(256), nullable=True),
        sa.Column("esxi_port", sa.Integer(), server_default="443"),
        sa.Column("agent_token", sa.String(64), nullable=True, unique=True),
        sa.Column("location", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("poll_interval", sa.Integer(), server_default="60"),
        sa.Column("status", sa.Enum("up", "down", "unknown", name="device_status"), server_default="unknown"),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_devices_type", "devices", ["device_type"])
    op.create_index("idx_devices_status", "devices", ["status"])
    op.create_index("idx_devices_active", "devices", ["is_active"])
    op.create_index("idx_devices_agent_token", "devices", ["agent_token"], unique=True)

    # ── Device Metrics (hypertable) ─────────────────────────────────
    op.create_table(
        "device_metrics",
        sa.Column("time", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("labels", postgresql.JSONB(), server_default="{}"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("time", "device_id", "metric_name"),
    )
    op.execute("SELECT create_hypertable('device_metrics', 'time', chunk_time_interval => INTERVAL '1 day')")
    op.create_index("idx_metrics_device_time", "device_metrics", ["device_id", sa.text("time DESC")])
    op.create_index("idx_metrics_name_time", "device_metrics", ["metric_name", sa.text("time DESC")])

    # ── Interface Metrics (hypertable) ──────────────────────────────
    op.create_table(
        "interface_metrics",
        sa.Column("time", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("interface_name", sa.String(64), nullable=False),
        sa.Column("rx_bytes", sa.BigInteger(), nullable=True),
        sa.Column("tx_bytes", sa.BigInteger(), nullable=True),
        sa.Column("rx_packets", sa.BigInteger(), nullable=True),
        sa.Column("tx_packets", sa.BigInteger(), nullable=True),
        sa.Column("rx_errors", sa.BigInteger(), nullable=True),
        sa.Column("tx_errors", sa.BigInteger(), nullable=True),
        sa.Column("rx_rate", sa.Float(), nullable=True),
        sa.Column("tx_rate", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("time", "device_id", "interface_name"),
    )
    op.execute("SELECT create_hypertable('interface_metrics', 'time', chunk_time_interval => INTERVAL '1 day')")
    op.create_index("idx_ifmetrics_device_time", "interface_metrics", ["device_id", sa.text("time DESC")])

    # ── Alert Rules ─────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("device_type", sa.Enum("mikrotik", "esxi", "vm_guest", name="device_type"), nullable=True),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("duration", sa.Integer(), server_default="0"),
        sa.Column("severity", sa.Enum("info", "warning", "critical", name="severity_level"), server_default="warning"),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Alerts ──────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.Enum("info", "warning", "critical", name="severity_level"), nullable=False),
        sa.Column("state", sa.Enum("firing", "acknowledged", "resolved", name="alert_state"), server_default="firing"),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("acknowledged_by", sa.String(128), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_alerts_state", "alerts", ["state"])
    op.create_index("idx_alerts_device", "alerts", ["device_id"])

    # ── Alert Notifications ─────────────────────────────────────────
    op.create_table(
        "alert_notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("recipient", sa.String(256), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Admin Users ─────────────────────────────────────────────────
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(128), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), server_default="admin"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    # ── Maintenance Windows ─────────────────────────────────────────
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Continuous Aggregates ───────────────────────────────────────
    op.execute("""
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
        WITH NO DATA
    """)

    op.execute("""
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
        WITH NO DATA
    """)

    # ── Compression policy ──────────────────────────────────────────
    op.execute("""
        ALTER TABLE device_metrics SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'device_id, metric_name',
            timescaledb.compress_orderby = 'time DESC'
        )
    """)
    op.execute("SELECT add_compression_policy('device_metrics', INTERVAL '7 days')")

    # ── Retention policy ────────────────────────────────────────────
    op.execute("SELECT add_retention_policy('device_metrics', INTERVAL '90 days')")
    op.execute("SELECT add_retention_policy('interface_metrics', INTERVAL '90 days')")


def downgrade() -> None:
    """Drop all NetMon tables and TimescaleDB objects."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS device_metrics_1h CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS device_metrics_5min CASCADE")

    op.drop_table("maintenance_windows")
    op.drop_table("admin_users")
    op.drop_table("alert_notifications")
    op.drop_table("alerts")
    op.drop_table("alert_rules")
    op.drop_table("interface_metrics")
    op.drop_table("device_metrics")
    op.drop_table("devices")

    op.execute("DROP TYPE IF EXISTS device_type CASCADE")
    op.execute("DROP TYPE IF EXISTS device_status CASCADE")
    op.execute("DROP TYPE IF EXISTS severity_level CASCADE")
    op.execute("DROP TYPE IF EXISTS alert_state CASCADE")
