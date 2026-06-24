"""API route handlers — fully auth-protected with OAuth2 JWT."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.auth import (
    authenticate_user, create_access_token, get_current_admin,
    get_current_user, hash_password,
)
from app.database import get_db
from app.models import (
    AdminUser, Alert, AlertRule, AlertState, Device, DeviceMetric,
    DeviceStatus, SeverityLevel, UserRole,
)
from app.security import CredentialEncryptor, get_encryptor, validate_device_input
from .export import export_router
from app.schemas import (
    AgentMetricPayload, AgentRegisterRequest, AgentRegisterResponse,
    AlertAcknowledge, AlertRuleCreate, AlertRuleResponse,
    AlertResponse, DeviceCreate, DeviceResponse, DeviceUpdate,
    DeviceStatusSummary, InterfaceTrafficResponse,
    LoginRequest, LoginResponse, MetricSeries, MetricPoint,
    OverviewResponse, RegisterRequest,
)
from app.services.alert_engine import AlertEvaluator
from app.services.alert_sender import AlertSender

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
device_router = APIRouter(prefix="/devices", tags=["Devices"])
metric_router = APIRouter(prefix="/metrics", tags=["Metrics"])
alert_rule_router = APIRouter(prefix="/alert-rules", tags=["Alert Rules"])
alert_router = APIRouter(prefix="/alerts", tags=["Alerts"])
agent_router = APIRouter(prefix="/agent", tags=["Agent"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ═══════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════

@auth_router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with username/password → returns JWT access token."""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return LoginResponse(
        access_token=token,
        username=user.username,
        role=str(user.role),
    )


@auth_router.post("/register", response_model=LoginResponse, status_code=201)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new admin account. First user becomes admin."""
    existing = await db.execute(
        select(AdminUser).where(
            (AdminUser.username == request.username) | (AdminUser.email == request.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already taken")

    # Check if any user exists — first user is admin, rest are viewer by default
    count_result = await db.execute(select(func.count(AdminUser.id)))
    user_count = count_result.scalar() or 0
    role = UserRole.ADMIN if user_count == 0 else UserRole.VIEWER

    user = AdminUser(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "role": str(user.role)})
    return LoginResponse(
        access_token=token,
        username=user.username,
        role=str(user.role),
    )


@auth_router.get("/me", response_model=dict)
async def get_me(current_user: AdminUser = Depends(get_current_user)):
    """Get current authenticated user info."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": str(current_user.role),
        "last_login_at": current_user.last_login_at,
    }


# ═══════════════════════════════════════════════════════════════════
#  DEVICE CRUD (protected — admin for write, any auth for read)
# ═══════════════════════════════════════════════════════════════════

@device_router.get("", response_model=list[DeviceResponse])
async def list_devices(
    device_type: str | None = None,
    status: str | None = None,
    is_active: bool | None = None,
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Device)
    if device_type:
        query = query.where(Device.device_type == device_type)
    if status:
        query = query.where(Device.status == status)
    if is_active is not None:
        query = query.where(Device.is_active == is_active)

    result = await db.execute(query.order_by(Device.name))
    return result.scalars().all()


@device_router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: int,
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@device_router.post("", response_model=DeviceResponse, status_code=201)
async def create_device(
    body: DeviceCreate,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Validate input
    errors = validate_device_input(body.model_dump())
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    agent_token = None
    if body.device_type == "vm_guest":
        agent_token = secrets.token_hex(32)

    # Encrypt sensitive credentials
    encryptor = get_encryptor()
    esxi_password = encryptor.encrypt(body.esxi_password) if body.esxi_password else None
    snmp_community = encryptor.encrypt(body.snmp_community) if body.snmp_community else None

    device = Device(
        name=body.name,
        device_type=body.device_type,
        ip_address=body.ip_address,
        snmp_community=snmp_community,
        snmp_version=body.snmp_version,
        snmp_port=body.snmp_port,
        esxi_username=body.esxi_username,
        esxi_password=esxi_password,
        esxi_port=body.esxi_port,
        agent_token=agent_token,
        location=body.location,
        description=body.description,
        poll_interval=body.poll_interval,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@device_router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    body: DeviceUpdate,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = body.model_dump(exclude_unset=True)

    # Validate if name or ip_address being updated
    if "name" in update_data or "ip_address" in update_data:
        test_data = {**{c.name: getattr(device, c.name) for c in device.__table__.columns}, **update_data}
        errors = validate_device_input(test_data)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})

    # Encrypt sensitive fields if being updated
    encryptor = get_encryptor()
    if "esxi_password" in update_data and update_data["esxi_password"]:
        update_data["esxi_password"] = encryptor.encrypt(update_data["esxi_password"])
    if "snmp_community" in update_data and update_data["snmp_community"]:
        update_data["snmp_community"] = encryptor.encrypt(update_data["snmp_community"])

    for key, value in update_data.items():
        setattr(device, key, value)

    device.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(device)
    return device


@device_router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: int,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(device)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
#  METRICS (read-only, any authenticated user)
# ═══════════════════════════════════════════════════════════════════

@metric_router.get("/{device_id}", response_model=list[MetricSeries])
async def get_device_metrics(
    device_id: int,
    metric_name: str | None = None,
    hours: int = Query(default=24, ge=1, le=720),
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    params: dict = {"device_id": device_id, "hours": hours}
    sql = """
        SELECT metric_name, time, metric_value
        FROM device_metrics
        WHERE device_id = :device_id
          AND time > NOW() - make_interval(hours => :hours)
    """
    if metric_name:
        sql += " AND metric_name = :metric_name"
        params["metric_name"] = metric_name
    sql += " ORDER BY time ASC"

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    series_map: dict[str, list[MetricPoint]] = {}
    for row in rows:
        series_map.setdefault(row.metric_name, []).append(
            MetricPoint(time=row.time, value=row.metric_value)
        )

    return [
        MetricSeries(device_id=device_id, device_name=device.name, metric_name=name, points=pts)
        for name, pts in series_map.items()
    ]


@metric_router.get("/{device_id}/interfaces", response_model=list[InterfaceTrafficResponse])
async def get_interface_traffic(
    device_id: int,
    ifname: str | None = None,
    hours: int = Query(default=24, ge=1, le=168),
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"device_id": device_id, "hours": hours}
    sql = """
        SELECT interface_name, time, rx_bytes, tx_bytes
        FROM interface_metrics
        WHERE device_id = :device_id AND time > NOW() - make_interval(hours => :hours)
    """
    if ifname:
        sql += " AND interface_name = :ifname"
        params["ifname"] = ifname
    sql += " ORDER BY time ASC"

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    from app.schemas import InterfaceTrafficPoint

    series_map: dict[str, list[InterfaceTrafficPoint]] = {}
    for row in rows:
        series_map.setdefault(row.interface_name, []).append(
            InterfaceTrafficPoint(time=row.time, rx_bytes=row.rx_bytes, tx_bytes=row.tx_bytes)
        )

    return [
        InterfaceTrafficResponse(device_id=device_id, interface_name=name, points=pts)
        for name, pts in series_map.items()
    ]


# ═══════════════════════════════════════════════════════════════════
#  ALERT RULES CRUD (admin only)
# ═══════════════════════════════════════════════════════════════════

@alert_rule_router.get("", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AlertRule).order_by(AlertRule.name))
    return result.scalars().all()


@alert_rule_router.post("", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    body: AlertRuleCreate,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    rule = AlertRule(
        name=body.name,
        device_id=body.device_id,
        device_type=body.device_type,
        metric_name=body.metric_name,
        operator=body.operator,
        threshold=body.threshold,
        duration=body.duration,
        severity=body.severity,
        description=body.description,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@alert_rule_router.put("/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    body: AlertRuleCreate,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    rule.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(rule)
    return rule


@alert_rule_router.delete("/{rule_id}", status_code=204)
async def delete_alert_rule(
    rule_id: int,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await db.delete(rule)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
#  ALERTS (acknowledge/resolve = admin, list = any auth)
# ═══════════════════════════════════════════════════════════════════

@alert_router.get("", response_model=list[AlertResponse])
async def list_alerts(
    state: str | None = None,
    severity: str | None = None,
    device_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import join as sa_join

    query = (
        select(Alert, Device.name.label("device_name"))
        .select_from(sa_join(Alert, Device, Alert.device_id == Device.id))
    )
    if state:
        query = query.where(Alert.state == state)
    if severity:
        query = query.where(Alert.severity == severity)
    if device_id:
        query = query.where(Alert.device_id == device_id)

    query = query.order_by(Alert.created_at.desc()).limit(limit)
    result = await db.execute(query)

    alerts = []
    for alert, device_name in result.all():
        data = AlertResponse.model_validate(alert)
        data.device_name = device_name or f"device-{alert.device_id}"
        alerts.append(data)
    return alerts


@alert_router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    body: AlertAcknowledge,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.state = AlertState.ACKNOWLEDGED
    alert.acknowledged_by = body.acknowledged_by
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "acknowledged"}


@alert_router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.state = AlertState.RESOLVED
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "resolved"}


# ═══════════════════════════════════════════════════════════════════
#  AGENT ENDPOINTS (token-based, no JWT)
# ═══════════════════════════════════════════════════════════════════

@agent_router.post("/register", response_model=AgentRegisterResponse)
async def register_agent(
    body: AgentRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new VM agent. Returns agent_token for authentication."""
    agent_token = secrets.token_hex(32)
    device = Device(
        name=body.name,
        device_type="vm_guest",
        agent_token=agent_token,
        location=body.location,
        description=body.description,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return AgentRegisterResponse(
        agent_token=agent_token,
        device_id=device.id,
        poll_interval=30,
    )


@agent_router.post("/push/{agent_token}")
async def push_agent_metrics(
    agent_token: str,
    payload: AgentMetricPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Receive metrics from VM guest agent (token-based auth)."""
    result = await db.execute(
        select(Device).where(
            Device.agent_token == agent_token,
            Device.is_active == True,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid agent token")

    now = datetime.now(timezone.utc)
    device.last_seen_at = now
    device.last_poll_at = now
    device.status = DeviceStatus.UP

    metrics = [
        ("cpu_usage", payload.cpu_percent),
        ("mem_usage_pct", payload.mem_percent),
        ("mem_used_mb", payload.mem_used_mb),
        ("mem_total_mb", payload.mem_total_mb),
        ("disk_usage_pct", payload.disk_percent),
        ("disk_used_gb", payload.disk_used_gb),
        ("disk_total_gb", payload.disk_total_gb),
        ("uptime_seconds", float(payload.uptime_seconds)),
    ]

    for metric_name, value in metrics:
        await db.execute(
            text(
                "INSERT INTO device_metrics (time, device_id, metric_name, metric_value) "
                "VALUES (:time, :device_id, :metric_name, :value)"
            ),
            {"time": now, "device_id": device.id, "metric_name": metric_name, "value": value},
        )

    await db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
#  DASHBOARD OVERVIEW
# ═══════════════════════════════════════════════════════════════════

@dashboard_router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Device.id)).where(Device.is_active == True))).scalar() or 0
    up = (await db.execute(
        select(func.count(Device.id)).where(Device.is_active == True, Device.status == DeviceStatus.UP.value)
    )).scalar() or 0
    down = (await db.execute(
        select(func.count(Device.id)).where(Device.is_active == True, Device.status == DeviceStatus.DOWN.value)
    )).scalar() or 0
    unknown = (await db.execute(
        select(func.count(Device.id)).where(Device.is_active == True, Device.status == DeviceStatus.UNKNOWN.value)
    )).scalar() or 0

    active_alerts = (await db.execute(
        select(func.count(Alert.id)).where(Alert.state.in_([AlertState.FIRING, AlertState.ACKNOWLEDGED]))
    )).scalar() or 0
    critical_alerts = (await db.execute(
        select(func.count(Alert.id)).where(
            Alert.state.in_([AlertState.FIRING, AlertState.ACKNOWLEDGED]),
            Alert.severity == SeverityLevel.CRITICAL,
        )
    )).scalar() or 0

    return OverviewResponse(
        devices=DeviceStatusSummary(total=total, up=up, down=down, unknown=unknown),
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
    )


# ═══════════════════════════════════════════════════════════════════
#  MAINTENANCE WINDOWS CRUD
# ═══════════════════════════════════════════════════════════════════

maintenance_router = APIRouter(prefix="/maintenance", tags=["Maintenance Windows"])


@maintenance_router.get("", response_model=list)
async def list_maintenance_windows(
    current_user: AdminUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import MaintenanceWindow
    result = await db.execute(
        select(MaintenanceWindow).order_by(MaintenanceWindow.start_time.desc())
    )
    return result.scalars().all()


@maintenance_router.post("", status_code=201)
async def create_maintenance_window(
    body: dict,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.maintenance import MaintenanceService
    service = MaintenanceService(db)
    window = await service.create_window(
        name=body["name"],
        start_time=datetime.fromisoformat(body["start_time"]),
        end_time=datetime.fromisoformat(body["end_time"]),
        device_id=body.get("device_id"),
        description=body.get("description"),
    )
    return {"id": window.id, "name": window.name, "status": "created"}


@maintenance_router.delete("/{window_id}", status_code=204)
async def delete_maintenance_window(
    window_id: int,
    current_user: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.maintenance import MaintenanceService
    service = MaintenanceService(db)
    ok = await service.delete_window(window_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
