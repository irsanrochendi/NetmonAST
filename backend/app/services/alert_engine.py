"""Alert engine: evaluates rules against metrics and manages alert lifecycle."""

from __future__ import annotations

import logging
import operator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from app.models import (
    Alert, AlertRule, AlertState, Device, DeviceMetric, SeverityLevel,
)

logger = logging.getLogger("alert_engine")

OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


@dataclass
class AlertEvaluation:
    rule_id: int
    device_id: int
    metric_name: str
    metric_value: float
    threshold: float
    severity: str
    message: str
    should_fire: bool


class AlertEvaluator:
    """Evaluates alert rules against the latest device metrics."""

    def __init__(self, session: Session):
        self.session = session

    def evaluate_all(self) -> List[AlertEvaluation]:
        """Evaluate all enabled alert rules. Returns list of evaluations."""
        rules: List[AlertRule] = (
            self.session.query(AlertRule)
            .filter(AlertRule.enabled == True)
            .all()
        )

        evaluations = []
        for rule in rules:
            try:
                evals = self._evaluate_rule(rule)
                evaluations.extend(evals)
            except Exception as e:
                logger.error("Error evaluating rule %s (id=%d): %s", rule.name, rule.id, e)

        return evaluations

    def _evaluate_rule(self, rule: AlertRule) -> List[AlertEvaluation]:
        """Evaluate a single rule against matching devices."""
        # Build device filter
        device_filter = [Device.is_active == True]
        if rule.device_id:
            device_filter.append(Device.id == rule.device_id)
        if rule.device_type:
            device_filter.append(Device.device_type == rule.device_type)

        devices = self.session.query(Device).filter(and_(*device_filter)).all()
        results = []

        op_func = OPERATORS.get(rule.operator)
        if not op_func:
            logger.warning("Unknown operator '%s' in rule %s", rule.operator, rule.name)
            return results

        for device in devices:
            # Get latest metric value for this device + metric
            latest = (
                self.session.query(DeviceMetric)
                .filter(
                    DeviceMetric.device_id == device.id,
                    DeviceMetric.metric_name == rule.metric_name,
                )
                .order_by(DeviceMetric.time.desc())
                .first()
            )

            if not latest:
                continue

            value = latest.metric_value
            breached = op_func(value, rule.threshold)

            severity = (
                rule.severity.value
                if isinstance(rule.severity, SeverityLevel)
                else str(rule.severity)
            )

            message = (
                f"{device.name}: {rule.metric_name} = {value:.2f} "
                f"(threshold {rule.operator} {rule.threshold:.2f})"
            )

            results.append(
                AlertEvaluation(
                    rule_id=rule.id,
                    device_id=device.id,
                    metric_name=rule.metric_name,
                    metric_value=value,
                    threshold=rule.threshold,
                    severity=severity,
                    message=message,
                    should_fire=breached,
                )
            )

        return results

    def process_evaluations(self, evaluations: List[AlertEvaluation]) -> List[Alert]:
        """Create/update/resolve alerts based on evaluation results."""
        new_alerts = []

        for ev in evaluations:
            # Check if there's already a firing alert for this rule+device
            existing = (
                self.session.query(Alert)
                .filter(
                    Alert.rule_id == ev.rule_id,
                    Alert.device_id == ev.device_id,
                    Alert.state.in_([AlertState.FIRING, AlertState.ACKNOWLEDGED]),
                )
                .first()
            )

            if ev.should_fire:
                if existing and existing.state == AlertState.ACKNOWLEDGED:
                    # Already acknowledged, skip
                    continue
                if not existing:
                    # Create new alert
                    alert = Alert(
                        rule_id=ev.rule_id,
                        device_id=ev.device_id,
                        severity=SeverityLevel(ev.severity),
                        state=AlertState.FIRING,
                        metric_name=ev.metric_name,
                        metric_value=ev.metric_value,
                        threshold=ev.threshold,
                        message=ev.message,
                    )
                    self.session.add(alert)
                    new_alerts.append(alert)
                    logger.warning("NEW ALERT: %s", ev.message)
            else:
                if existing and existing.state in (AlertState.FIRING, AlertState.ACKNOWLEDGED):
                    # Resolve it
                    existing.state = AlertState.RESOLVED
                    existing.resolved_at = datetime.now(timezone.utc)
                    logger.info("RESOLVED: %s", ev.message)

        self.session.commit()
        return new_alerts
