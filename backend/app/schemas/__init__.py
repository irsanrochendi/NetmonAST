"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Device Schemas ──────────────────────────────────────────────────

class DeviceCreate(BaseModel):
    name: str = Field(..., max_length=128)
    device_type: str = Field(..., pattern="^(mikrotik|esxi|vm_guest)$")
    ip_address: Optional[str] = None
    snmp_community: Optional[str] = "public"
    snmp_version: Optional[str] = "2c"
    snmp_port: Optional[int] = 161
    esxi_username: Optional[str] = "root"
    esxi_password: Optional[str] = ""
    esxi_port: Optional[int] = 443
    location: Optional[str] = None
    description: Optional[str] = None
    poll_interval: int = 60


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_version: Optional[str] = None
    snmp_port: Optional[int] = None
    esxi_username: Optional[str] = None
    esxi_password: Optional[str] = None
    esxi_port: Optional[int] = None
    location: Optional[str] = None
    description: Optional[str] = None
    poll_interval: Optional[int] = None
    is_active: Optional[bool] = None


class DeviceResponse(BaseModel):
    id: int
    name: str
    device_type: str
    ip_address: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_version: str = "2c"
    snmp_port: int = 161
    esxi_username: Optional[str] = None
    esxi_port: int = 443
    agent_token: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    poll_interval: int = 60
    status: str = "unknown"
    last_poll_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Metric Schemas ──────────────────────────────────────────────────

class MetricPoint(BaseModel):
    time: datetime
    value: float


class MetricSeries(BaseModel):
    device_id: int
    device_name: str
    metric_name: str
    points: List[MetricPoint]


class InterfaceTrafficPoint(BaseModel):
    time: datetime
    rx_bytes: int
    tx_bytes: int
    rx_rate: Optional[float] = None
    tx_rate: Optional[float] = None


class InterfaceTrafficResponse(BaseModel):
    device_id: int
    interface_name: str
    points: List[InterfaceTrafficPoint]


# ── Agent Schemas ───────────────────────────────────────────────────

class AgentMetricPayload(BaseModel):
    cpu_percent: float
    mem_total_mb: float
    mem_used_mb: float
    mem_percent: float
    disk_total_gb: float
    disk_used_gb: float
    disk_percent: float
    uptime_seconds: int


class AgentRegisterRequest(BaseModel):
    name: str
    device_type: str = "vm_guest"
    location: Optional[str] = None
    description: Optional[str] = None


class AgentRegisterResponse(BaseModel):
    agent_token: str
    device_id: int
    poll_interval: int


# ── Alert Rule Schemas ──────────────────────────────────────────────

class AlertRuleCreate(BaseModel):
    name: str
    device_id: Optional[int] = None
    device_type: Optional[str] = None
    metric_name: str
    operator: str = Field(..., pattern="^(>|<|>=|<=|==|!=)$")
    threshold: float
    duration: int = 0
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    description: Optional[str] = None


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    device_id: Optional[int] = None
    device_type: Optional[str] = None
    metric_name: str
    operator: str
    threshold: float
    duration: int
    severity: str
    enabled: bool = True
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Alert Schemas ───────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: int
    rule_id: int
    device_id: int
    device_name: str = ""
    severity: str
    state: str
    metric_name: str
    metric_value: float
    threshold: float
    message: Optional[str] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertAcknowledge(BaseModel):
    acknowledged_by: str


# ── Dashboard Overview ──────────────────────────────────────────────

class DeviceStatusSummary(BaseModel):
    total: int
    up: int
    down: int
    unknown: int


class OverviewResponse(BaseModel):
    devices: DeviceStatusSummary
    active_alerts: int
    critical_alerts: int
    recent_metrics: List[MetricSeries] = []


# ── Auth Schemas ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class RegisterRequest(BaseModel):
    username: str = Field(..., max_length=64)
    email: str = Field(..., max_length=128)
    password: str = Field(..., min_length=8)
