"""ESXi / vSphere client via pyVmomi."""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

logger = logging.getLogger(__name__)


@dataclass
class ESXiVMData:
    name: str
    power_state: str  # poweredOn, poweredOff, suspended
    guest_os: str = ""
    cpu_count: int = 0
    cpu_usage_mhz: int = 0
    mem_total_mb: int = 0
    mem_usage_mb: int = 0
    mem_usage_pct: float = 0.0
    ip_address: str = ""
    tools_status: str = ""


@dataclass
class ESXiDatastoreData:
    name: str
    capacity_gb: float = 0.0
    free_gb: float = 0.0
    used_gb: float = 0.0
    usage_pct: float = 0.0
    type: str = ""  # VMFS, NFS, etc.


@dataclass
class ESXiResult:
    success: bool
    host_name: str = ""
    model: str = ""
    vendor: str = ""
    cpu_model: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    cpu_usage_pct: float = 0.0
    cpu_usage_mhz: int = 0
    cpu_total_mhz: int = 0
    mem_total_gb: float = 0.0
    mem_usage_gb: float = 0.0
    mem_usage_pct: float = 0.0
    uptime_seconds: int = 0
    vms: List[ESXiVMData] = field(default_factory=list)
    datastores: List[ESXiDatastoreData] = field(default_factory=list)
    error: Optional[str] = None


class ESXiClient:
    """Connects to ESXi host via pyVmomi and collects metrics."""

    def __init__(
        self,
        host: str,
        username: str = "root",
        password: str = "",
        port: int = 443,
        disable_ssl_verify: bool = True,
        timeout: int = 30,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.disable_ssl_verify = disable_ssl_verify
        self.timeout = timeout
        self._service_instance: Optional[Any] = None

    def _connect(self) -> Any:
        """Establish connection to ESXi host."""
        ssl_context = None
        if self.disable_ssl_verify:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            si = SmartConnect(
                host=self.host,
                user=self.username,
                pwd=self.password,
                port=self.port,
                sslContext=ssl_context,
                connectionPoolTimeout=self.timeout,
            )
            self._service_instance = si
            return si
        except Exception as e:
            raise ConnectionError(f"ESXi connection failed for {self.host}: {e}")

    def _disconnect(self):
        if self._service_instance:
            try:
                Disconnect(self._service_instance)
            except Exception:
                pass
            self._service_instance = None

    def poll(self) -> ESXiResult:
        """Full poll: host info + CPU/memory + VMs + datastores."""
        result = ESXiResult(success=False)

        try:
            si = self._connect()
            content = si.RetrieveContent()

            # Get the host system
            host_view = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.HostSystem], True
            )
            hosts = host_view.view
            host_view.Destroy()

            if not hosts:
                result.error = "No host system found"
                return result

            host = hosts[0]
            summary = host.summary
            hw = summary.hardware
            stats = summary.quickStats
            runtime = summary.runtime

            # ── Host info ───────────────────────────────────────
            result.host_name = summary.config.name
            result.model = hw.model
            result.vendor = hw.vendor
            result.cpu_model = hw.cpuModel
            result.cpu_cores = hw.numCpuCores
            result.cpu_threads = hw.numCpuThreads
            result.uptime_seconds = stats.uptime

            # ── CPU ─────────────────────────────────────────────
            if hw and hw.cpuMhz:
                result.cpu_total_mhz = hw.numCpuCores * hw.cpuMhz
                result.cpu_usage_mhz = stats.overallCpuUsage or 0
                if result.cpu_total_mhz > 0:
                    result.cpu_usage_pct = round(
                        (result.cpu_usage_mhz / result.cpu_total_mhz) * 100, 2
                    )

            # ── Memory ──────────────────────────────────────────
            if hw and hw.memorySize:
                result.mem_total_gb = round(hw.memorySize / (1024 ** 3), 2)
                mem_used_mb = stats.overallMemoryUsage or 0
                result.mem_usage_gb = round(mem_used_mb / 1024, 2)
                if result.mem_total_gb > 0:
                    result.mem_usage_pct = round(
                        (result.mem_usage_gb / result.mem_total_gb) * 100, 2
                    )

            # ── VMs ─────────────────────────────────────────────
            vm_view = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )
            for vm in vm_view.view:
                vm_data = self._extract_vm_data(vm)
                result.vms.append(vm_data)
            vm_view.Destroy()

            # ── Datastores ──────────────────────────────────────
            ds_view = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.Datastore], True
            )
            for ds in ds_view.view:
                ds_data = self._extract_datastore_data(ds)
                result.datastores.append(ds_data)
            ds_view.Destroy()

            result.success = True
            logger.info(
                "ESXi poll OK: %s (cpu=%.1f%%, mem=%.1f%%, vms=%d)",
                self.host, result.cpu_usage_pct, result.mem_usage_pct, len(result.vms),
            )

        except ConnectionError as e:
            result.error = str(e)
            logger.warning("ESXi poll FAILED for %s: %s", self.host, e)
        except Exception as e:
            result.error = str(e)
            logger.error("ESXi poll ERROR for %s: %s", self.host, e, exc_info=True)
        finally:
            self._disconnect()

        return result

    def _extract_vm_data(self, vm) -> ESXiVMData:
        """Extract metrics from a VirtualMachine object."""
        summary = vm.summary
        config = summary.config
        runtime = summary.runtime
        guest = summary.guest
        stats = summary.quickStats

        data = ESXiVMData(
            name=config.name or "unknown",
            power_state=runtime.powerState if runtime else "unknown",
            guest_os=config.guestFullName or "",
            cpu_count=config.numCpu or 0,
            ip_address=guest.ipAddress or "",
            tools_status=str(guest.toolsStatus) if guest and guest.toolsStatus else "",
        )

        # CPU usage in MHz
        if stats:
            data.cpu_usage_mhz = stats.overallCpuUsage or 0

        # Memory
        if config:
            data.mem_total_mb = config.memorySizeMB or 0
        if stats:
            data.mem_usage_mb = stats.guestMemoryUsage or 0
            if data.mem_total_mb > 0:
                data.mem_usage_pct = round(
                    (data.mem_usage_mb / data.mem_total_mb) * 100, 2
                )

        return data

    def _extract_datastore_data(self, ds) -> ESXiVMData:
        """Extract info from a Datastore object."""
        summary = ds.summary
        cap = summary.capacity
        free = summary.freeSpace

        used = cap - free
        usage_pct = round((used / cap) * 100, 2) if cap > 0 else 0.0

        return ESXiDatastoreData(
            name=summary.name or "unknown",
            capacity_gb=round(cap / (1024 ** 3), 2),
            free_gb=round(free / (1024 ** 3), 2),
            used_gb=round(used / (1024 ** 3), 2),
            usage_pct=usage_pct,
            type=summary.type or "",
        )
