"""ESXi Poller — runs as a standalone Docker container.

Polls all active ESXi hosts and stores metrics in TimescaleDB.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.collectors.esxi_client import ESXiClient
from app.database import sync_engine, SyncSessionLocal
from app.models import Device, DeviceStatus
from app.security import get_encryptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("esxi_poller")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 120))
RUNNING = True


def _handle_signal(signum, frame):
    global RUNNING
    logger.info("Received signal %d, shutting down...", signum)
    RUNNING = False


def poll_host(session, device: Device) -> bool:
    """Poll a single ESXi host. Returns True if successful."""
    # Decrypt credentials
    encryptor = get_encryptor()
    password = encryptor.decrypt(device.esxi_password) if device.esxi_password else ""

    client = ESXiClient(
        host=str(device.ip_address),
        username=device.esxi_username or "root",
        password=password,
        port=device.esxi_port or 443,
        disable_ssl_verify=True,
    )

    result = client.poll()
    now = datetime.now(timezone.utc)

    if result.success:
        device.status = DeviceStatus.UP
        device.last_seen_at = now
        device.last_poll_at = now

        metrics = [
            ("cpu_usage_pct", result.cpu_usage_pct),
            ("cpu_usage_mhz", float(result.cpu_usage_mhz)),
            ("mem_usage_pct", result.mem_usage_pct),
            ("mem_usage_gb", result.mem_usage_gb),
            ("mem_total_gb", result.mem_total_gb),
            ("uptime_seconds", float(result.uptime_seconds)),
        ]

        for metric_name, value in metrics:
            session.execute(
                text(
                    "INSERT INTO device_metrics (time, device_id, metric_name, metric_value) "
                    "VALUES (:time, :device_id, :metric_name, :value)"
                ),
                {"time": now, "device_id": device.id, "metric_name": metric_name, "value": value},
            )

        # VM metrics
        for vm in result.vms:
            labels = {"vm_name": vm.name, "power_state": vm.power_state}
            vm_metrics = [
                ("vm_cpu_usage_mhz", float(vm.cpu_usage_mhz)),
                ("vm_mem_usage_pct", vm.mem_usage_pct),
                ("vm_mem_usage_mb", float(vm.mem_usage_mb)),
                ("vm_mem_total_mb", float(vm.mem_total_mb)),
            ]
            for metric_name, value in vm_metrics:
                session.execute(
                    text(
                        "INSERT INTO device_metrics (time, device_id, metric_name, metric_value, labels) "
                        "VALUES (:time, :device_id, :metric_name, :value, :labels)"
                    ),
                    {
                        "time": now,
                        "device_id": device.id,
                        "metric_name": metric_name,
                        "value": value,
                        "labels": labels,
                    },
                )

        # Datastore metrics
        for ds in result.datastores:
            labels = {"datastore_name": ds.name, "ds_type": ds.type}
            ds_metrics = [
                ("ds_usage_pct", ds.usage_pct),
                ("ds_used_gb", ds.used_gb),
                ("ds_free_gb", ds.free_gb),
                ("ds_capacity_gb", ds.capacity_gb),
            ]
            for metric_name, value in ds_metrics:
                session.execute(
                    text(
                        "INSERT INTO device_metrics (time, device_id, metric_name, metric_value, labels) "
                        "VALUES (:time, :device_id, :metric_name, :value, :labels)"
                    ),
                    {
                        "time": now,
                        "device_id": device.id,
                        "metric_name": metric_name,
                        "value": value,
                        "labels": labels,
                    },
                )

        session.commit()
        logger.info("ESXi host %s (%s) polled OK", device.name, device.ip_address)
        return True
    else:
        device.status = DeviceStatus.DOWN
        device.last_poll_at = now
        session.commit()
        logger.warning("ESXi host %s (%s) DOWN: %s", device.name, device.ip_address, result.error)
        return False


def main():
    global RUNNING
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("ESXi Poller started (interval=%ds)", POLL_INTERVAL)

    while RUNNING:
        try:
            with SyncSessionLocal() as session:
                devices = session.query(Device).filter(
                    Device.device_type == "esxi",
                    Device.is_active == True,
                ).all()

                if not devices:
                    logger.debug("No active ESXi hosts to poll")
                else:
                    logger.info("Polling %d ESXi host(s)...", len(devices))
                    for device in devices:
                        if not RUNNING:
                            break
                        try:
                            poll_host(session, device)
                        except Exception as e:
                            logger.error("Error polling ESXi host %s: %s", device.name, e)
        except Exception as e:
            logger.error("Poller loop error: %s", e)

        for _ in range(POLL_INTERVAL):
            if not RUNNING:
                break
            time.sleep(1)

    logger.info("ESXi Poller stopped.")


if __name__ == "__main__":
    main()
