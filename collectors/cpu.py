# collectors/cpu.py
"""
Collects per-core and aggregate CPU utilization metrics.
Uses psutil for user-space metric gathering.
"""

import asyncio
import logging
import time

try:
    import psutil
except ImportError:
    raise ImportError("psutil not installed. Install via: pip install psutil")

from ingestion.event_bus import EventBus, SystemEvent, EventType

logger = logging.getLogger(__name__)


class CPUCollector:
    """Collects CPU metrics (utilization, frequency, topology)."""

    def __init__(self, event_bus: EventBus, interval: float = 1.0):
        self.event_bus = event_bus
        self.interval = interval
        self.running = False
        self._cpu_topology_sent = False

    async def start(self):
        """Start periodic CPU metric collection."""
        logger.info(f"CPUCollector started (interval={self.interval}s)")
        self.running = True

        try:
            while self.running:
                await self._collect_metrics()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("CPUCollector cancelled")
        finally:
            self.running = False

    async def stop(self):
        """Stop metric collection."""
        self.running = False

    async def _collect_metrics(self):
        """Collect and publish CPU metrics (async-safe, correct sampling)."""
        try:
            # --------------------------------------------------
            # 1. Warm-up call (DO NOT publish this value)
            # --------------------------------------------------
            psutil.cpu_percent(interval=None, percpu=True)

            # Yield control instead of blocking
            await asyncio.sleep(0.1)

            # --------------------------------------------------
            # 2. Real CPU sample (single instant)
            # --------------------------------------------------
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            total_cpu = sum(per_cpu) / len(per_cpu) if per_cpu else 0.0

            timestamp = time.time()

            # --------------------------------------------------
            # 3. Publish per-core CPU utilization
            # --------------------------------------------------
            for core_id, percent in enumerate(per_cpu):
                event = SystemEvent(
                    event_type=EventType.CPU_METRIC,
                    source="collector::cpu",
                    timestamp=timestamp,
                    data={
                        "cpu_id": core_id,
                        "percent": percent,
                        "metric_type": "utilization",
                    },
                )
                await self.event_bus.publish(event)

            # --------------------------------------------------
            # 4. Publish total CPU utilization
            # --------------------------------------------------
            event = SystemEvent(
                event_type=EventType.CPU_METRIC,
                source="collector::cpu",
                timestamp=timestamp,
                data={
                    "cpu_id": "total",
                    "percent": total_cpu,
                    "metric_type": "utilization",
                },
            )
            await self.event_bus.publish(event)

            # --------------------------------------------------
            # 5. CPU frequency (slow-changing metric)
            # --------------------------------------------------
            freq = psutil.cpu_freq()
            if freq:
                event = SystemEvent(
                    event_type=EventType.CPU_METRIC,
                    source="collector::cpu",
                    timestamp=timestamp,
                    data={
                        "metric_type": "frequency",
                        "current_mhz": freq.current,
                        "min_mhz": freq.min,
                        "max_mhz": freq.max,
                    },
                )
                await self.event_bus.publish(event)

            # --------------------------------------------------
            # 6. CPU topology (publish once)
            # --------------------------------------------------
            if not self._cpu_topology_sent:
                event = SystemEvent(
                    event_type=EventType.CPU_METRIC,
                    source="collector::cpu",
                    timestamp=timestamp,
                    data={
                        "metric_type": "count",
                        "physical_cores": psutil.cpu_count(logical=False),
                        "logical_cores": psutil.cpu_count(logical=True),
                    },
                )
                await self.event_bus.publish(event)
                self._cpu_topology_sent = True

        except Exception as e:
            logger.error(f"CPU collector failed: {e}", exc_info=True)
