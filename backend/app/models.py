"""SQLAlchemy models for NetMon database schema."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Double, Enum, ForeignKey,
    Index, Integer, String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class DeviceType(str, enum.Enum):
    MIKROTIK = "mikrotik"
    ESXI = "esxi"
    VM_GUEST = "vm_guest"


class DeviceStatus(str, enum.Enum):
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class SeverityLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(str, enum.Enum):
    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    device_type = Column(Enum(DeviceType, name="device_type"), nullable=False)
    ip_address = Column(INET, nullable=True)
    # Mikrotik SNMP
    snmp_community = Column(String(128))
    snmp_version = Column(String(8), default="2c")
    snmp_port = Column(Integer, default=161)
    # ESXi
    esxi_username = Column(String(128))
    esxi_password = Column(String(256))
    esxi_port = Column(Integer, default=443)
    # VM guest
    agent_token = Column(String(64), unique=True)
    # Meta
    location = Column(String(256))
    description = Column(Text)
    poll_interval = Column(Integer, default=60)
    status = Column(Enum(DeviceStatus, name="device_status"), default=DeviceStatus.UNKNOWN)
    last_poll_at = Column(DateTime(timezone=True))
    last_seen_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    metrics = relationship("DeviceMetric", back_populates="device", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="device", cascade="all, delete-orphan")


class DeviceMetric(Base):
    __tablename__ = "device_metrics"

    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    metric_name = Column(String(64), primary_key=True, nullable=False)
    metric_value = Column(Double, nullable=False)
    labels = Column(JSONB, default={})

    device = relationship("Device", back_populates="metrics")


class InterfaceMetric(Base):
    __tablename__ = "interface_metrics"

    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    interface_name = Column(String(64), primary_key=True, nullable=False)
    rx_bytes = Column(BigInteger)
    tx_bytes = Column(BigInteger)
    rx_packets = Column(BigInteger)
    tx_packets = Column(BigInteger)
    rx_errors = Column(BigInteger)
    tx_errors = Column(BigInteger)
    rx_rate = Column(Double)
    tx_rate = Column(Double)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True)
    device_type = Column(Enum(DeviceType, name="device_type"), nullable=True)
    metric_name = Column(String(64), nullable=False)
    operator = Column(String(8), nullable=False)
    threshold = Column(Double, nullable=False)
    duration = Column(Integer, default=0)
    severity = Column(Enum(SeverityLevel, name="severity_level"), default=SeverityLevel.WARNING)
    enabled = Column(Boolean, default=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    severity = Column(Enum(SeverityLevel, name="severity_level"), nullable=False)
    state = Column(Enum(AlertState, name="alert_state"), default=AlertState.FIRING)
    metric_name = Column(String(64), nullable=False)
    metric_value = Column(Double, nullable=False)
    threshold = Column(Double, nullable=False)
    message = Column(Text)
    acknowledged_by = Column(String(128))
    acknowledged_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    device = relationship("Device", back_populates="alerts")


class AlertNotification(Base):
    __tablename__ = "alert_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(32), nullable=False)
    recipient = Column(String(256))
    status = Column(String(16), default="pending")
    error_message = Column(Text)
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    email = Column(String(128), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default="admin")
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
