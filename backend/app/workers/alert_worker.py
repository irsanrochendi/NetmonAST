"""Alert Worker — runs as a standalone Docker container.

Periodically evaluates alert rules and sends notifications.
Skips alerts for devices in active maintenance windows.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

from app.database import SyncSessionLocal
from app.models import Device
from app.services.alert_engine import AlertEvaluator
from app.services.alert_sender import AlertSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("alert_worker")

EVAL_INTERVAL = int(os.environ.get("ALERT_EVAL_INTERVAL", 30))
RUNNING = True


def _handle_signal(signum, frame):
    global RUNNING
    logger.info("Received signal %d, shutting down...", signum)
    RUNNING = False


async def evaluate_and_send():
    """Run one evaluation cycle, skipping devices in maintenance."""
    sender = AlertSender()

    with SyncSessionLocal() as session:
        # Import here to avoid circular imports
        from app.services.maintenance import MaintenanceService
        from datetime import datetime, timezone
        from sqlalchemy import and_, or_
        from app.models import MaintenanceWindow

        # Get active maintenance windows
        now = datetime.now(timezone.utc)
        maint_result = session.query(MaintenanceWindow).filter(
            and_(
                MaintenanceWindow.start_time <= now,
                MaintenanceWindow.end_time >= now,
            )
        ).all()

        # Build set of device IDs in maintenance (None = global = all devices)
        maint_device_ids = set()
        global_maintenance = False
        for mw in maint_result:
            if mw.device_id is None:
                global_maintenance = True
                break
            maint_device_ids.add(mw.device_id)

        if global_maintenance:
            logger.info("Global maintenance window active — skipping all alerts")
            return

        if maint_device_ids:
            logger.info("Devices in maintenance: %s", maint_device_ids)

        evaluator = AlertEvaluator(session)
        evaluations = evaluator.evaluate_all()

        # Filter out evaluations for devices in maintenance
        if maint_device_ids:
            evaluations = [e for e in evaluations if e.device_id not in maint_device_ids]

        new_alerts = evaluator.process_evaluations(evaluations)

        if new_alerts:
            logger.info("Processing %d new alert(s)...", len(new_alerts))
            for alert in new_alerts:
                dev = session.query(Device).get(alert.device_id)
                device_name = dev.name if dev else f"device-{alert.device_id}"
                await sender.send_alert(alert, device_name, session)


def main():
    global RUNNING
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("Alert Worker started (eval interval=%ds)", EVAL_INTERVAL)

    while RUNNING:
        try:
            asyncio.run(evaluate_and_send())
        except Exception as e:
            logger.error("Alert evaluation error: %s", e)

        for _ in range(EVAL_INTERVAL):
            if not RUNNING:
                break
            time.sleep(1)

    logger.info("Alert Worker stopped.")


if __name__ == "__main__":
    main()
