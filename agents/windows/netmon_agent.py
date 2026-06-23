"""
NetMon Windows Agent
====================
Collects CPU, memory, and disk metrics using psutil and sends
them to the NetMon server via the /api/agent/push/{token} endpoint.

Can run:
  1. As a standalone script:  python netmon_agent.py
  2. As a Windows Service:    python netmon_service.py
  3. As a compiled .exe:      netmon_agent.exe (PyInstaller)

Usage:
    # Standalone
    python netmon_agent.py --server http://YOUR_SERVER:8000 --token YOUR_TOKEN

    # Install as Windows Service (run as Administrator)
    python netmon_service.py install
    python netmon_service.py start

    # Or use the PowerShell installer: install_service.ps1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import time
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import psutil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] netmon-agent: %(message)s",
)
logger = logging.getLogger("netmon-agent")

# ── Default Configuration ──────────────────────────────────────────
DEFAULT_CONFIG_PATHS = [
    r"C:\ProgramData\NetMon\agent.conf",
    r"C:\NetMon\agent.conf",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.conf"),
]

DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_POLL_INTERVAL = 30
DEFAULT_REQUEST_TIMEOUT = 10


class NetMonAgent:
    """Collects system metrics and pushes to NetMon server."""

    def __init__(
        self,
        server_url: str,
        agent_token: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ):
        self.server_url = server_url.rstrip("/")
        self.agent_token = agent_token
        self.poll_interval = poll_interval
        self.request_timeout = request_timeout
        self.push_url = f"{self.server_url}/api/agent/push/{self.agent_token}"
        self.running = True

    def collect_metrics(self) -> Dict[str, Any]:
        """Collect CPU, memory, and disk metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)

        mem = psutil.virtual_memory()
        mem_total_mb = round(mem.total / (1024 * 1024), 2)
        mem_used_mb = round(mem.used / (1024 * 1024), 2)
        mem_percent = mem.percent

        # Disk (C: drive on Windows)
        disk = psutil.disk_usage("C:\\")
        disk_total_gb = round(disk.total / (1024 ** 3), 2)
        disk_used_gb = round(disk.used / (1024 ** 3), 2)
        disk_percent = disk.percent

        uptime_seconds = int(time.time() - psutil.boot_time())

        return {
            "cpu_percent": cpu_percent,
            "mem_total_mb": mem_total_mb,
            "mem_used_mb": mem_used_mb,
            "mem_percent": mem_percent,
            "disk_total_gb": disk_total_gb,
            "disk_used_gb": disk_used_gb,
            "disk_percent": disk_percent,
            "uptime_seconds": uptime_seconds,
        }

    def push_metrics(self, metrics: Dict[str, Any]) -> bool:
        """Send metrics to NetMon server."""
        try:
            response = httpx.post(
                self.push_url,
                json=metrics,
                timeout=self.request_timeout,
            )
            if response.status_code == 200:
                logger.debug("Metrics pushed OK: cpu=%.1f%% mem=%.1f%% disk=%.1f%%",
                             metrics["cpu_percent"], metrics["mem_percent"], metrics["disk_percent"])
                return True
            elif response.status_code == 401:
                logger.error("Invalid agent token — check your configuration")
                return False
            else:
                logger.warning("Server returned %d: %s", response.status_code, response.text)
                return False
        except httpx.ConnectError:
            logger.error("Cannot connect to NetMon server at %s", self.server_url)
            return False
        except httpx.TimeoutException:
            logger.warning("Push timed out after %ds", self.request_timeout)
            return False
        except Exception as e:
            logger.error("Push failed: %s", e)
            return False

    def run(self):
        """Main loop."""
        logger.info(
            "NetMon Agent started (server=%s, interval=%ds, hostname=%s)",
            self.server_url, self.poll_interval, platform.node(),
        )

        while self.running:
            try:
                metrics = self.collect_metrics()
                self.push_metrics(metrics)
            except Exception as e:
                logger.error("Error in main loop: %s", e)

            for _ in range(self.poll_interval):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("NetMon Agent stopped.")

    def stop(self):
        self.running = False


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file."""
    paths_to_try = [config_path] if config_path else DEFAULT_CONFIG_PATHS
    paths_to_try = [p for p in paths_to_try if p]

    for path in paths_to_try:
        if os.path.isfile(path):
            parser = ConfigParser()
            parser.read(path)
            if parser.has_section("agent"):
                return dict(parser.items("agent"))
    return {}


def create_sample_config(path: str):
    """Write a sample configuration file."""
    sample = """[agent]
; NetMon server URL
server_url = http://localhost:8000

; Agent token (obtained from NetMon dashboard or registration API)
agent_token = YOUR_AGENT_TOKEN_HERE

; Polling interval in seconds
poll_interval = 30

; HTTP request timeout in seconds
request_timeout = 10
"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(sample)
    logger.info("Sample config written to %s", path)


def main():
    parser = argparse.ArgumentParser(description="NetMon Windows Agent")
    parser.add_argument("--config", "-c", help="Path to configuration file", default=None)
    parser.add_argument("--server-url", help="NetMon server URL", default=None)
    parser.add_argument("--agent-token", "-t", help="Agent token", default=None)
    parser.add_argument("--interval", "-i", type=int, help="Polling interval (seconds)", default=None)
    parser.add_argument("--generate-config", help="Generate sample config at path and exit", default=None)
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.generate_config:
        create_sample_config(args.generate_config)
        sys.exit(0)

    config = load_config(args.config)
    server_url = args.server_url or config.get("server_url", DEFAULT_SERVER_URL)
    agent_token = args.agent_token or config.get("agent_token", "")
    poll_interval = args.interval or int(config.get("poll_interval", DEFAULT_POLL_INTERVAL))
    request_timeout = int(config.get("request_timeout", DEFAULT_REQUEST_TIMEOUT))

    if not agent_token or agent_token == "YOUR_AGENT_TOKEN_HERE":
        logger.error("No agent token configured!")
        logger.error("Register: curl -X POST %s/api/agent/register "
                     "-H 'Content-Type: application/json' "
                     "-d '{\"name\": \"%s\"}'", server_url, platform.node())
        sys.exit(1)

    agent = NetMonAgent(
        server_url=server_url,
        agent_token=agent_token,
        poll_interval=poll_interval,
        request_timeout=request_timeout,
    )
    agent.run()


if __name__ == "__main__":
    main()
