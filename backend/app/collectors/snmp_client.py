"""SNMP client for Mikrotik devices using pysnmp."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    nextCmd,
)

logger = logging.getLogger(__name__)

# ── Standard MIB OIDs ──────────────────────────────────────────────
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"

# ── Mikrotik-specific OIDs ─────────────────────────────────────────
OID_CPU_LOAD = "1.3.6.1.4.1.14988.1.1.3.1.0"
OID_MEM_FREE = "1.3.6.1.4.1.14988.1.1.3.3.0"
OID_MEM_TOTAL = "1.3.6.1.4.1.14988.1.1.3.2.0"

# ── Interface OIDs (IF-MIB) ────────────────────────────────────────
OID_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_IN_UCAST = "1.3.6.1.2.1.2.2.1.11"
OID_IF_OUT_UCAST = "1.3.6.1.2.1.2.2.1.17"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"


@dataclass
class SNMPInterfaceData:
    index: int
    name: str = ""
    speed: int = 0
    in_octets: int = 0
    out_octets: int = 0
    in_packets: int = 0
    out_packets: int = 0
    in_errors: int = 0
    out_errors: int = 0
    oper_status: int = 0


@dataclass
class SNMPResult:
    success: bool
    sys_uptime: Optional[int] = None
    sys_name: Optional[str] = None
    sys_descr: Optional[str] = None
    cpu_usage: Optional[float] = None
    mem_free: Optional[int] = None
    mem_total: Optional[int] = None
    mem_usage_pct: Optional[float] = None
    interfaces: List[SNMPInterfaceData] = field(default_factory=list)
    error: Optional[str] = None


class SNMPClient:
    """SNMP v1/v2c client for querying Mikrotik and other SNMP devices."""

    def __init__(
        self,
        host: str,
        community: str = "public",
        port: int = 161,
        version: str = "2c",
        timeout: int = 5,
        retries: int = 2,
    ):
        self.host = host
        self.community = community
        self.port = port
        self.version = version
        self.timeout = timeout
        self.retries = retries

    def _get_transport(self) -> UdpTransportTarget:
        return UdpTransportTarget(
            (self.host, self.port),
            timeout=self.timeout,
            retries=self.retries,
        )

    def _get_community(self) -> CommunityData:
        if self.version == "1":
            return CommunityData(self.community, mpModel=0)
        return CommunityData(self.community, mpModel=1)

    def _snmp_get(self, *oids: str) -> Dict[str, Any]:
        """Perform SNMP GET for one or more OIDs."""
        engine = SnmpEngine()
        results: Dict[str, Any] = {}
        object_types = [ObjectType(ObjectIdentity(oid)) for oid in oids]

        error_indication, error_status, error_index, var_binds = next(
            getCmd(
                engine,
                self._get_community(),
                self._get_transport(),
                ContextData(),
                *object_types,
            )
        )

        if error_indication:
            raise ConnectionError(f"SNMP error: {error_indication}")
        if error_status:
            raise ConnectionError(
                f"SNMP error: {error_status.prettyPrint()} at "
                f"{var_binds[int(error_index) - 1][0] if error_index else '?'}"
            )

        for var_bind in var_binds:
            results[str(var_bind[0])] = var_bind[1]

        return results

    def _snmp_walk(self, oid: str) -> Dict[str, Any]:
        """Perform SNMP WALK for a given OID tree."""
        engine = SnmpEngine()
        results: Dict[str, Any] = {}

        for (error_indication, error_status, error_index, var_binds) in nextCmd(
            engine,
            self._get_community(),
            self._get_transport(),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if error_indication:
                logger.warning("SNMP walk error for %s: %s", self.host, error_indication)
                break
            if error_status:
                logger.warning("SNMP walk error for %s: %s", self.host, error_status.prettyPrint())
                break
            for var_bind in var_binds:
                results[str(var_bind[0])] = var_bind[1]

        return results

    def poll(self) -> SNMPResult:
        """Full poll: system info + CPU/memory + interfaces."""
        result = SNMPResult(success=False)

        try:
            # System info
            sys_data = self._snmp_get(OID_SYS_UPTIME, OID_SYS_NAME, OID_SYS_DESCR)
            for oid, val in sys_data.items():
                if OID_SYS_UPTIME in oid:
                    result.sys_uptime = int(val)
                elif OID_SYS_NAME in oid:
                    result.sys_name = str(val)
                elif OID_SYS_DESCR in oid:
                    result.sys_descr = str(val)

            # CPU & Memory (Mikrotik-specific)
            try:
                hw_data = self._snmp_get(OID_CPU_LOAD, OID_MEM_FREE, OID_MEM_TOTAL)
                for oid, val in hw_data.items():
                    if OID_CPU_LOAD in oid:
                        result.cpu_usage = float(int(val))
                    elif OID_MEM_FREE in oid:
                        result.mem_free = int(val)
                    elif OID_MEM_TOTAL in oid:
                        result.mem_total = int(val)
                if result.mem_total and result.mem_free:
                    used = result.mem_total - result.mem_free
                    result.mem_usage_pct = round((used / result.mem_total) * 100, 2)
            except Exception as e:
                logger.debug("Mikrotik HW OIDs not available for %s: %s", self.host, e)

            # Interfaces
            result.interfaces = self._poll_interfaces()

            result.success = True
            logger.info(
                "SNMP poll OK: %s (cpu=%.1f%%, mem=%.1f%%)",
                self.host, result.cpu_usage or 0, result.mem_usage_pct or 0,
            )

        except ConnectionError as e:
            result.error = str(e)
            logger.warning("SNMP poll FAILED for %s: %s", self.host, e)
        except Exception as e:
            result.error = str(e)
            logger.error("SNMP poll ERROR for %s: %s", self.host, e, exc_info=True)

        return result

    def _poll_interfaces(self) -> List[SNMPInterfaceData]:
        """Poll interface table via SNMP WALK."""
        interfaces: Dict[int, SNMPInterfaceData] = {}

        def _extract_index(oid_str: str) -> Optional[int]:
            parts = oid_str.split(".")
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                return None

        def _walk_and_collect(base_oid: str, attr_name: str, is_str: bool = False):
            try:
                data = self._snmp_walk(base_oid)
                for oid, val in data.items():
                    idx = _extract_index(oid)
                    if idx is None:
                        continue
                    if idx not in interfaces:
                        interfaces[idx] = SNMPInterfaceData(index=idx)
                    v = str(val) if is_str else int(val)
                    setattr(interfaces[idx], attr_name, v)
            except Exception as e:
                logger.debug("Walk %s failed: %s", base_oid, e)

        _walk_and_collect(OID_IF_NAME, "name", is_str=True)
        _walk_and_collect(OID_IF_SPEED, "speed")
        _walk_and_collect(OID_IF_IN_OCTETS, "in_octets")
        _walk_and_collect(OID_IF_OUT_OCTETS, "out_octets")
        _walk_and_collect(OID_IF_IN_UCAST, "in_packets")
        _walk_and_collect(OID_IF_OUT_UCAST, "out_packets")
        _walk_and_collect(OID_IF_IN_ERRORS, "in_errors")
        _walk_and_collect(OID_IF_OUT_ERRORS, "out_errors")
        _walk_and_collect(OID_IF_OPER_STATUS, "oper_status")

        return list(interfaces.values())
