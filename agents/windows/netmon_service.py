"""
NetMon Windows Service
======================
Runs the NetMon agent as a Windows Service using pywin32.

Requires: pip install pywin32

Commands (run as Administrator):
    python netmon_service.py install     # Install the service
    python netmon_service.py start       # Start the service
    python netmon_service.py stop        # Stop the service
    python netmon_service.py remove      # Remove the service
    python netmon_service.py debug       # Run in debug mode (console)
"""

from __future__ import annotations

import logging
import os
import sys
import time

# Add script directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from netmon_agent import NetMonAgent, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] netmon-service: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(SCRIPT_DIR, "netmon_service.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("netmon-service")

CONFIG_PATH = os.path.join(SCRIPT_DIR, "agent.conf")
SERVICE_NAME = "NetMonAgent"
SERVICE_DISPLAY_NAME = "NetMon Windows Agent"
SERVICE_DESCRIPTION = "NetMon VM Guest Monitoring Agent — collects CPU, memory, and disk metrics"


class NetMonWindowsService(win32serviceutil.ServiceFramework if HAS_WIN32 else object):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        if not HAS_WIN32:
            raise RuntimeError("pywin32 is required for Windows Service mode")
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.agent = None

    def SvcStop(self):
        """Called when service is asked to stop."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.agent:
            self.agent.stop()
        logger.info("Service stop requested.")

    def SvcDoRun(self):
        """Main service loop."""
        logger.info("NetMon Windows Service starting...")
        try:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
        except Exception:
            pass

        config = load_config(CONFIG_PATH)
        if not config:
            logger.error("No configuration found at %s", CONFIG_PATH)
            logger.error("Create agent.conf with server_url and agent_token")
            return

        self.agent = NetMonAgent(
            server_url=config.get("server_url", "http://localhost:8000"),
            agent_token=config.get("agent_token", ""),
            poll_interval=int(config.get("poll_interval", 30)),
            request_timeout=int(config.get("request_timeout", 10)),
        )

        # Run agent in a thread so we can respond to stop events
        import threading
        agent_thread = threading.Thread(target=self.agent.run, daemon=True)
        agent_thread.start()

        # Wait for stop signal
        while True:
            rc = win32event.WaitForSingleObject(self.stop_event, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                logger.info("Stop signal received.")
                self.agent.stop()
                break

        agent_thread.join(timeout=15)
        logger.info("NetMon Windows Service stopped.")


def run_debug():
    """Run agent in console debug mode."""
    logger.info("Running in debug mode (console)...")
    config = load_config(CONFIG_PATH)
    if not config:
        logger.error("No config at %s — creating sample...", CONFIG_PATH)
        from netmon_agent import create_sample_config
        create_sample_config(CONFIG_PATH)
        logger.error("Edit agent.conf and re-run.")
        return

    agent = NetMonAgent(
        server_url=config.get("server_url", "http://localhost:8000"),
        agent_token=config.get("agent_token", ""),
        poll_interval=int(config.get("poll_interval", 30)),
        request_timeout=int(config.get("request_timeout", 10)),
    )
    agent.run()


if __name__ == "__main__":
    if not HAS_WIN32:
        print("pywin32 not available — running in debug mode")
        run_debug()
    elif len(sys.argv) > 1 and sys.argv[1] == "debug":
        run_debug()
    else:
        win32serviceutil.HandleCommandLine(NetMonWindowsService)
