# ingestion/stream_processor.py
"""
Stream processor for normalizing, enriching, and storing system events.
Maintains time-series buffers and provides query interfaces for:
- Dashboard (instantaneous values)
- ML pipelines (windowed statistics)
"""

import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Import after logger definition
try:
    import psutil
except ImportError:
    psutil = None


# =========================
# Time-series primitives
# =========================

@dataclass
class TimeSeriesPoint:
    """Single data point in time-series stream"""
    timestamp: float
    value: float
    metadata: Dict = None


class TimeSeriesBuffer:
    """Fixed-size circular buffer for time-series data"""

    def __init__(self, max_size: int = 1000):
        self.buffer = deque(maxlen=max_size)

    def append(self, point: TimeSeriesPoint):
        self.buffer.append(point)

    def get_all(self) -> List[TimeSeriesPoint]:
        return list(self.buffer)

    def get_recent(self, seconds: float) -> List[TimeSeriesPoint]:
        now = time.time()
        return [p for p in self.buffer if now - p.timestamp <= seconds]

    def get_latest(self) -> Optional[TimeSeriesPoint]:
        if not self.buffer:
            return None
        return self.buffer[-1]

    def get_stats(self) -> dict:
        if not self.buffer:
            return {
                "count": 0,
                "mean": 0.0,
                "min": 0.0,
                "max": 0.0,
                "latest": None,
            }

        values = [p.value for p in self.buffer]
        return {
            "count": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "latest": values[-1],
        }


# =========================
# Stream Processor
# =========================

class StreamProcessor:
    """
    Central metric authority.

    - Stores raw metric samples
    - Exposes instantaneous access for dashboard
    - Exposes windowed access for ML pipelines
    """

    def __init__(self, event_bus, history_size: int = 1000):
        self.event_bus = event_bus

        self.metrics: Dict[str, TimeSeriesBuffer] = defaultdict(
            lambda: TimeSeriesBuffer(history_size)
        )
        self.event_history = deque(maxlen=5000)
        self.process_cache = {}

        self.running = False
        self._subscriber_id = "stream_processor"
        self._subscription_queue = None

    # -------------------------
    # Lifecycle
    # -------------------------

    async def start(self):
        logger.info("Starting StreamProcessor...")

        self._subscription_queue = await self.event_bus.subscribe(
            self._subscriber_id,
            event_types=None,
        )

        self.running = True

        try:
            while self.running:
                try:
                    event = await asyncio.wait_for(
                        self._subscription_queue.get(), timeout=1.0
                    )
                    await self._process_event(event)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("StreamProcessor cancelled")
        finally:
            await self.event_bus.unsubscribe(self._subscriber_id)
            logger.info("StreamProcessor stopped")

    async def stop(self):
        self.running = False

    # -------------------------
    # Event processing
    # -------------------------

    async def _process_event(self, event):
        try:
            self.event_history.append(event)
            await self._extract_metrics(event)
            await self._enrich_event(event)
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)

    async def _extract_metrics(self, event):
        from ingestion.event_bus import EventType

        metric_key = None
        metric_value = None

        if event.event_type == EventType.CPU_METRIC:
            metric_key = f"cpu.{event.data.get('cpu_id', 'total')}"
            metric_value = event.data.get("percent")

        elif event.event_type == EventType.MEMORY_METRIC:
            metric_key = f"memory.{event.data.get('type', 'unknown')}"
            metric_value = event.data.get("percent")

        elif event.event_type == EventType.DISK_METRIC:
            device = event.data.get("device", "total")
            mtype = event.data.get("type", "read_bytes")
            metric_key = f"disk.{device}.{mtype}"
            metric_value = event.data.get("value")

        elif event.event_type == EventType.NETWORK_METRIC:
            mtype = event.data.get("type", "sent_bytes")
            metric_key = f"network.{mtype}"
            metric_value = event.data.get("bytes")

        elif event.event_type == EventType.IO_READ:
            metric_key = "io.read_latency_us"
            metric_value = event.data.get("latency_us")

        elif event.event_type == EventType.IO_WRITE:
            metric_key = "io.write_latency_us"
            metric_value = event.data.get("latency_us")

        if metric_key and metric_value is not None:
            point = TimeSeriesPoint(
                timestamp=event.timestamp,
                value=float(metric_value),
                metadata=event.data,
            )
            self.metrics[metric_key].append(point)

    async def _enrich_event(self, event):
        if event.pid and psutil:
            if event.pid not in self.process_cache:
                try:
                    proc = psutil.Process(event.pid)
                    self.process_cache[event.pid] = {
                        "name": proc.name(),
                        "exe": proc.exe(),
                        "cmdline": " ".join(proc.cmdline()),
                    }
                except Exception:
                    return

            event.metadata["process_info"] = self.process_cache.get(event.pid)

    # =========================
    # DASHBOARD ACCESS (LIVE)
    # =========================

    def get_latest_value(self, metric_key: str) -> Optional[float]:
        """
        Instantaneous metric value.
        Used ONLY by dashboard.
        """
        buffer = self.metrics.get(metric_key)
        if not buffer:
            return None

        latest = buffer.get_latest()
        return latest.value if latest else None

    # =========================
    # ML ACCESS (WINDOWED)
    # =========================

    def get_window(
        self, metric_key: str, seconds: float = 300
    ) -> List[float]:
        """
        Windowed metric values.
        Used by ML pipelines.
        """
        buffer = self.metrics.get(metric_key)
        if not buffer:
            return []

        return [p.value for p in buffer.get_recent(seconds)]

    # =========================
    # LEGACY / SUPPORT
    # =========================

    def get_metric_stats(self, metric_key: str) -> dict:
        """Statistical summary (ML / health views)."""
        buffer = self.metrics.get(metric_key)
        return buffer.get_stats() if buffer else {}

    def get_metric_keys(self) -> List[str]:
        return list(self.metrics.keys())

    def get_recent_events(self, event_type=None, limit: int = 100):
        events = list(self.event_history)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def get_processor_stats(self) -> dict:
        return {
            "total_events_processed": len(self.event_history),
            "active_metrics": len(self.metrics),
            "process_cache_size": len(self.process_cache),
            "event_history_size": len(self.event_history),
        }

    def export_metrics_csv(self, filepath: str, duration_seconds: int = 3600) -> None:
        """Export all metrics to CSV for training"""
        import csv
        import time
        from datetime import datetime
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'metric_key', 'value', 'pid', 'comm'])
            
            start_time = time.time()
            while time.time() - start_time < duration_seconds:
                for metric_key in self.get_metric_keys():
                    latest = self.get_latest_value(metric_key)
                    if latest is not None:
                        # Extract metadata for context
                        buffer = self.metrics.get(metric_key)
                        if buffer:
                            latest_point = buffer.get_latest()
                            metadata = getattr(latest_point, 'metadata', {})
                            pid = metadata.get('pid', 0)
                            comm = metadata.get('comm', '')
                            writer.writerow([
                                datetime.fromtimestamp(latest_point.timestamp).isoformat(),
                                metric_key,
                                latest,
                                pid,
                                comm
                            ])
                time.sleep(1)
        print(f"Exported {duration_seconds}s of data to {filepath}")