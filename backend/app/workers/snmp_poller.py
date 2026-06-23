"""SNMP Poller — runs as a standalone Docker container.

Polls all active Mikrotik devices and stores metrics in TimescaleDB.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.collectors.snmp_client import SNMPClient
from app.database import sync_engine, SyncSessionLocal
from app.models import Device, DeviceStatus
from app.security import get_encryptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("snmp_poller")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 60))
RUNNING = True


def _handle_signal(signum, frame):
    global RUNNING
    logger.info("Received signal %d, shutting down...", signum)
    RUNNING = False


def poll_device(session, device: Device) -> bool:
    """Poll a single Mikrotik device. Returns True if successful."""
    # Decrypt SNMP community
    encryptor = get_encryptor()
    community = encryptor.decrypt(device.snmp_community) if device.snmp_community else "public"

    client = SNMPClient(
        host=str(device.ip_address),
        community=community,
        port=device.snmp_port or 161,
        version=device.snmp_version or "2c",
    )

    result = client.poll()
    now = datetime.now(timezone.utc)

    if result.success:
        # Update device status
        device.status = DeviceStatus.UP
        device.last_seen_at = now
        device.last_poll_at = now

        # Store metrics
        metrics = []
        if result.sys_uptime is not None:
            metrics.append(("sys_uptime", float(result.sys_uptime)))
        if result.cpu_usage is not None:
            metrics.append(("cpu_usage", result.cpu_usage))
        if result.mem_total is not None:
            metrics.append(("mem_total", float(result.mem_total)))
        if result.mem_free is not None:
            metrics.append(("mem_free", float(result.mem_free)))
        if result.mem_usage_pct is not None:
            metrics.append(("mem_usage_pct", result.mem_usage_pct))

        for metric_name, value in metrics:
            session.execute(
                text(
                    "INSERT INTO device_metrics (time, device_id, metric_name, metric_value) "
                    "VALUES (:time, :device_id, :metric_name, :value)"
                ),
                {"time": now, "device_id": device.id, "metric_name": metric_name, "value": value},
            )

        # Store interface metrics
        for iface in result.interfaces:
            if not iface.name:
                continue
            session.execute(
                text(
                    "INSERT INTO interface_metrics "
                    "(time, device_id, interface_name, rx_bytes, tx_bytes, "
                    "rx_packets, tx_packets, rx_errors, tx_errors, oper_status) "
                    "VALUES (:time, :device_id, :ifname, :rx, :tx, :rp, :tp, :re, :te, :os)"
                ),
                {
                    "time": now,
                    "device_id": device.id,
                    "ifname": iface.name,
                    "rx": iface.in_octets,
                    "tx": iface.out_octets,
                    "rp": iface.in_packets,
                    "tp": iface.out_packets,
                    "re": iface.in_errors,
                    "te": iface.out_errors,
                    "os": iface.oper_status,
                },
            )

        session.commit()
        logger.info("Device %s (%s) polled OK", device.name, device.ip_address)
        return True
    else:
        device.status = DeviceStatus.DOWN
        device.last_poll_at = now
        session.commit()
        logger.warning("Device %s (%s) DOWN: %s", device.name, device.ip_address, result.error)
        return False


def main():
    global RUNNING
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("SNMP Poller started (interval=%ds)", POLL_INTERVAL)

    while RUNNING:
        try:
            with SyncSessionLocal() as session:
                devices = session.query(Device).filter(
                    Device.device_type == "mikrotik",
                    Device.is_active == True,
                ).all()

                if not devices:
                    logger.debug("No active Mikrotik devices to poll")
                else:
                    logger.info("Polling %d Mikrotik device(s)...", len(devices))
                    for device in devices:
                        if not RUNNING:
                            break
                        try:
                            poll_device(session, device)
                        except Exception as e:
                            logger.error("Error polling device %s: %s", device.name, e)
        except Exception as e:
            logger.error("Poller loop error: %s", e)

        # Sleep in small increments for graceful shutdown
        for _ in range(POLL_INTERVAL):
            if not RUNNING:
                break
            time.sleep(1)

    logger.info("SNMP Poller stopped.")


if __name__ == "__main__":
    main()
