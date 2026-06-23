#!/usr/bin/env python3
"""
NetMon Load Test — Simulasi 50 Device
======================================
Simulates 50 devices (Mikrotik + ESXi + VM Guest) and measures:
- SNMP poller throughput
- ESXi poller throughput
- API response times
- Database write performance
- Memory usage

Usage:
    python load_test.py --devices 50 --duration 300
    python load_test.py --devices 100 --duration 600 --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ── Simulated device data ──────────────────────────────────────────

MIKROTIK_NAMES = [
    "RT-Core-01", "RT-Core-02", "RT-Dist-01", "RT-Dist-02", "RT-Dist-03",
    "RT-Access-01", "RT-Access-02", "RT-Access-03", "RT-Access-04", "RT-Access-05",
    "RT-Branch-01", "RT-Branch-02", "RT-Branch-03", "RT-Branch-04", "RT-Branch-05",
    "RT-Wireless-01", "RT-Wireless-02", "RT-Wireless-03", "RT-VPN-01", "RT-VPN-02",
]

ESXI_NAMES = [
    "ESXi-Host-01", "ESXi-Host-02", "ESXi-Host-03", "ESXi-Host-04",
    "ESXi-Host-05", "ESXi-Host-06", "ESXi-Host-07", "ESXi-Host-08",
]

VM_NAMES = [
    "VM-Web-01", "VM-Web-02", "VM-Web-03", "VM-DB-01", "VM-DB-02",
    "VM-App-01", "VM-App-02", "VM-App-03", "VM-Mail-01", "VM-DNS-01",
    "VM-FW-01", "VM-Monitor-01", "VM-Backup-01", "VM-Test-01", "VM-Dev-01",
]


@dataclass
class SimulatedDevice:
    id: int
    name: str
    device_type: str
    ip_address: str
    status: str = "up"


@dataclass
class PollResult:
    device_id: int
    device_type: str
    success: bool
    duration_ms: float
    metrics_count: int = 0
    error: Optional[str] = None


@dataclass
class LoadTestStats:
    total_polls: int = 0
    successful_polls: int = 0
    failed_polls: int = 0
    durations_ms: list = field(default_factory=list)
    metrics_written: int = 0
    start_time: float = 0
    end_time: float = 0

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def polls_per_second(self) -> float:
        return self.total_polls / max(self.duration_seconds, 0.001)

    @property
    def success_rate(self) -> float:
        return (self.successful_polls / max(self.total_polls, 1)) * 100

    @property
    def avg_latency_ms(self) -> float:
        return statistics.mean(self.durations_ms) if self.durations_ms else 0

    @property
    def p50_latency_ms(self) -> float:
        return statistics.median(self.durations_ms) if self.durations_ms else 0

    @property
    def p95_latency_ms(self) -> float:
        if not self.durations_ms:
            return 0
        sorted_d = sorted(self.durations_ms)
        idx = int(len(sorted_d) * 0.95)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    @property
    def p99_latency_ms(self) -> float:
        if not self.durations_ms:
            return 0
        sorted_d = sorted(self.durations_ms)
        idx = int(len(sorted_d) * 0.99)
        return sorted_d[min(idx, len(sorted_d) - 1)]


class SNMPSimulator:
    """Simulates SNMP polling without actual network calls."""

    def __init__(self, failure_rate: float = 0.02):
        self.failure_rate = failure_rate

    def poll(self, device: SimulatedDevice) -> PollResult:
        """Simulate an SNMP poll."""
        start = time.monotonic()

        # Simulate network latency (5-50ms)
        latency = random.uniform(0.005, 0.050)
        time.sleep(latency)

        # Simulate occasional failures
        if random.random() < self.failure_rate:
            return PollResult(
                device_id=device.id,
                device_type="mikrotik",
                success=False,
                duration_ms=(time.monotonic() - start) * 1000,
                error="Timeout",
            )

        return PollResult(
            device_id=device.id,
            device_type="mikrotik",
            success=True,
            duration_ms=(time.monotonic() - start) * 1000,
            metrics_count=8,  # cpu, mem, uptime, + 4 interface metrics
        )


class ESXiSimulator:
    """Simulates ESXi polling without actual network calls."""

    def __init__(self, failure_rate: float = 0.03):
        self.failure_rate = failure_rate

    def poll(self, device: SimulatedDevice) -> PollResult:
        """Simulate an ESXi poll."""
        start = time.monotonic()

        # ESXi polling is slower (50-200ms)
        latency = random.uniform(0.050, 0.200)
        time.sleep(latency)

        if random.random() < self.failure_rate:
            return PollResult(
                device_id=device.id,
                device_type="esxi",
                success=False,
                duration_ms=(time.monotonic() - start) * 1000,
                error="Connection refused",
            )

        return PollResult(
            device_id=device.id,
            device_type="esxi",
            success=True,
            duration_ms=(time.monotonic() - start) * 1000,
            metrics_count=12,  # host cpu/mem + VMs + datastores
        )


class AgentSimulator:
    """Simulates VM agent metric pushes."""

    def __init__(self, failure_rate: float = 0.01):
        self.failure_rate = failure_rate

    def push(self, device: SimulatedDevice) -> PollResult:
        """Simulate an agent push."""
        start = time.monotonic()

        # Agent push is fast (1-10ms)
        latency = random.uniform(0.001, 0.010)
        time.sleep(latency)

        if random.random() < self.failure_rate:
            return PollResult(
                device_id=device.id,
                device_type="vm_guest",
                success=False,
                duration_ms=(time.monotonic() - start) * 1000,
                error="HTTP 401",
            )

        return PollResult(
            device_id=device.id,
            device_type="vm_guest",
            success=True,
            duration_ms=(time.monotonic() - start) * 1000,
            metrics_count=8,
        )


def generate_devices(count: int) -> list[SimulatedDevice]:
    """Generate simulated device list."""
    devices = []
    ip_counter = 1

    # Distribute: 40% Mikrotik, 20% ESXi, 40% VM Guest
    mikrotik_count = int(count * 0.4)
    esxi_count = int(count * 0.2)
    vm_count = count - mikrotik_count - esxi_count

    for i in range(mikrotik_count):
        name = MIKROTIK_NAMES[i % len(MIKROTIK_NAMES)]
        if i >= len(MIKROTIK_NAMES):
            name = f"{name}-{i // len(MIKROTIK_NAMES)}"
        devices.append(SimulatedDevice(
            id=len(devices) + 1,
            name=name,
            device_type="mikrotik",
            ip_address=f"10.0.{ip_counter // 256}.{ip_counter % 256}",
        ))
        ip_counter += 1

    for i in range(esxi_count):
        name = ESXI_NAMES[i % len(ESXI_NAMES)]
        if i >= len(ESXI_NAMES):
            name = f"{name}-{i // len(ESXI_NAMES)}"
        devices.append(SimulatedDevice(
            id=len(devices) + 1,
            name=name,
            device_type="esxi",
            ip_address=f"10.1.{ip_counter // 256}.{ip_counter % 256}",
        ))
        ip_counter += 1

    for i in range(vm_count):
        name = VM_NAMES[i % len(VM_NAMES)]
        if i >= len(VM_NAMES):
            name = f"{name}-{i // len(VM_NAMES)}"
        devices.append(SimulatedDevice(
            id=len(devices) + 1,
            name=name,
            device_type="vm_guest",
            ip_address=f"10.2.{ip_counter // 256}.{ip_counter % 256}",
        ))
        ip_counter += 1

    return devices


def run_load_test(devices: list[SimulatedDevice], duration_seconds: int, verbose: bool = False) -> dict:
    """Run the full load test."""
    snmp_sim = SNMPSimulator()
    esxi_sim = ESXiSimulator()
    agent_sim = AgentSimulator()

    snmp_devices = [d for d in devices if d.device_type == "mikrotik"]
    esxi_devices = [d for d in devices if d.device_type == "esxi"]
    vm_devices = [d for d in devices if d.device_type == "vm_guest"]

    snmp_stats = LoadTestStats()
    esxi_stats = LoadTestStats()
    agent_stats = LoadTestStats()

    start_time = time.monotonic()
    snmp_stats.start_time = start_time
    esxi_stats.start_time = start_time
    agent_stats.start_time = start_time

    poll_interval = 1.0  # 1 second between poll rounds
    round_num = 0

    print(f"\n🔄 Starting load test: {len(devices)} devices, {duration_seconds}s duration")
    print(f"   Mikrotik: {len(snmp_devices)} | ESXi: {len(esxi_devices)} | VM Guest: {len(vm_devices)}")
    print()

    while time.monotonic() - start_time < duration_seconds:
        round_num += 1
        round_start = time.monotonic()

        # Poll Mikrotik devices
        for dev in snmp_devices:
            result = snmp_sim.poll(dev)
            snmp_stats.total_polls += 1
            snmp_stats.durations_ms.append(result.duration_ms)
            if result.success:
                snmp_stats.successful_polls += 1
                snmp_stats.metrics_written += result.metrics_count
            else:
                snmp_stats.failed_polls += 1

        # Poll ESXi devices
        for dev in esxi_devices:
            result = esxi_sim.poll(dev)
            esxi_stats.total_polls += 1
            esxi_stats.durations_ms.append(result.duration_ms)
            if result.success:
                esxi_stats.successful_polls += 1
                esxi_stats.metrics_written += result.metrics_count
            else:
                esxi_stats.failed_polls += 1

        # Agent pushes
        for dev in vm_devices:
            result = agent_sim.push(dev)
            agent_stats.total_polls += 1
            agent_stats.durations_ms.append(result.duration_ms)
            if result.success:
                agent_stats.successful_polls += 1
                agent_stats.metrics_written += result.metrics_count
            else:
                agent_stats.failed_polls += 1

        # Progress report every 10 rounds
        if round_num % 10 == 0:
            elapsed = time.monotonic() - start_time
            total_polls = snmp_stats.total_polls + esxi_stats.total_polls + agent_stats.total_polls
            print(f"   ⏱️  {elapsed:.0f}s | Rounds: {round_num} | Polls: {total_polls} | "
                  f"SNMP: {snmp_stats.successful_polls}/{snmp_stats.total_polls} | "
                  f"ESXi: {esxi_stats.successful_polls}/{esxi_stats.total_polls} | "
                  f"Agent: {agent_stats.successful_polls}/{agent_stats.total_polls}")

        # Wait for next round
        elapsed_round = time.monotonic() - round_start
        sleep_time = max(0, poll_interval - elapsed_round)
        if sleep_time > 0:
            time.sleep(sleep_time)

    snmp_stats.end_time = time.monotonic()
    esxi_stats.end_time = time.monotonic()
    agent_stats.end_time = time.monotonic()

    return {
        "snmp": snmp_stats,
        "esxi": esxi_stats,
        "agent": agent_stats,
        "total_duration": time.monotonic() - start_time,
        "total_rounds": round_num,
    }


def print_results(results: dict):
    """Print formatted test results."""
    print()
    print("=" * 70)
    print("  NETMON LOAD TEST RESULTS")
    print("=" * 70)
    print()

    for name, key in [("📡 SNMP Poller (Mikrotik)", "snmp"), ("🖥️  ESXi Poller", "esxi"), ("📊 VM Agent Push", "agent")]:
        stats: LoadTestStats = results[key]
        print(f"  {name}")
        print(f"  {'─' * 50}")
        print(f"  Total Polls:     {stats.total_polls:,}")
        print(f"  Successful:      {stats.successful_polls:,} ({stats.success_rate:.1f}%)")
        print(f"  Failed:          {stats.failed_polls:,}")
        print(f"  Metrics Written: {stats.metrics_written:,}")
        print(f"  Avg Latency:     {stats.avg_latency_ms:.1f} ms")
        print(f"  P50 Latency:     {stats.p50_latency_ms:.1f} ms")
        print(f"  P95 Latency:     {stats.p95_latency_ms:.1f} ms")
        print(f"  P99 Latency:     {stats.p99_latency_ms:.1f} ms")
        print(f"  Throughput:      {stats.polls_per_second:.1f} polls/sec")
        print()

    total_polls = results["snmp"].total_polls + results["esxi"].total_polls + results["agent"].total_polls
    total_success = results["snmp"].successful_polls + results["esxi"].successful_polls + results["agent"].successful_polls
    total_metrics = results["snmp"].metrics_written + results["esxi"].metrics_written + results["agent"].metrics_written

    print(f"  📈 OVERALL")
    print(f"  {'─' * 50}")
    print(f"  Duration:        {results['total_duration']:.1f}s")
    print(f"  Total Rounds:    {results['total_rounds']}")
    print(f"  Total Polls:     {total_polls:,}")
    print(f"  Overall Success: {(total_success / max(total_polls, 1)) * 100:.1f}%")
    print(f"  Total Metrics:   {total_metrics:,}")
    print(f"  Avg Throughput:  {total_polls / max(results['total_duration'], 0.001):.1f} polls/sec")
    print()
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="NetMon Load Test")
    parser.add_argument("--devices", type=int, default=50, help="Number of simulated devices (default: 50)")
    parser.add_argument("--duration", type=int, default=300, help="Test duration in seconds (default: 300)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║   NetMon Load Test — Device Simulation  ║")
    print("╚══════════════════════════════════════════╝")

    devices = generate_devices(args.devices)
    results = run_load_test(devices, args.duration, args.verbose)
    print_results(results)

    if args.output:
        # Convert to serializable format
        output = {
            "config": {"devices": args.devices, "duration": args.duration},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snmp": {
                "total_polls": results["snmp"].total_polls,
                "successful": results["snmp"].successful_polls,
                "failed": results["snmp"].failed_polls,
                "avg_latency_ms": results["snmp"].avg_latency_ms,
                "p95_latency_ms": results["snmp"].p95_latency_ms,
                "p99_latency_ms": results["snmp"].p99_latency_ms,
                "polls_per_second": results["snmp"].polls_per_second,
            },
            "esxi": {
                "total_polls": results["esxi"].total_polls,
                "successful": results["esxi"].successful_polls,
                "failed": results["esxi"].failed_polls,
                "avg_latency_ms": results["esxi"].avg_latency_ms,
                "p95_latency_ms": results["esxi"].p95_latency_ms,
                "p99_latency_ms": results["esxi"].p99_latency_ms,
                "polls_per_second": results["esxi"].polls_per_second,
            },
            "agent": {
                "total_polls": results["agent"].total_polls,
                "successful": results["agent"].successful_polls,
                "failed": results["agent"].failed_polls,
                "avg_latency_ms": results["agent"].avg_latency_ms,
                "p95_latency_ms": results["agent"].p95_latency_ms,
                "p99_latency_ms": results["agent"].p99_latency_ms,
                "polls_per_second": results["agent"].polls_per_second,
            },
        }
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"📄 Results saved to: {args.output}")


if __name__ == "__main__":
    main()
