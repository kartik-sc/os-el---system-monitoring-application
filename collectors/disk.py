# collectors/disk.py
"""Disk I/O metrics collection"""

import asyncio
import logging

try:
    import psutil
except ImportError:
    raise ImportError("psutil not installed")

from ingestion.event_bus import EventBus, SystemEvent, EventType

logger = logging.getLogger(__name__)


class DiskCollector:
    """Collects disk I/O metrics (throughput, latency)"""
    
    def __init__(self, event_bus: EventBus, interval: float = 2.0):
        self.event_bus = event_bus
        self.interval = interval
        self.running = False
        self.last_io_counters = None
    
    async def start(self):
        logger.info(f"DiskCollector started (interval={self.interval}s)")
        self.running = True
        self.last_io_counters = psutil.disk_io_counters(perdisk=True)
        
        try:
            while self.running:
                await self._collect_metrics()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("DiskCollector cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        self.running = False
    
    async def _collect_metrics(self):
        try:
            current_counters = psutil.disk_io_counters(perdisk=True)
            
            if self.last_io_counters:
                for disk, current in current_counters.items():
                    last = self.last_io_counters.get(disk)
                    if not last:
                        continue
                    
                    read_bytes = current.read_bytes - last.read_bytes
                    write_bytes = current.write_bytes - last.write_bytes
                    
                    event = SystemEvent(
                        event_type=EventType.DISK_METRIC,
                        source="collector::disk",
                        data={
                            'device': disk,
                            'read_bytes_delta': read_bytes,
                            'write_bytes_delta': write_bytes,
                            'read_time_ms': current.read_time - last.read_time,
                            'write_time_ms': current.write_time - last.write_time,
                            'read_count': current.read_count - last.read_count,
                            'write_count': current.write_count - last.write_count,
                        }
                    )
                    await self.event_bus.publish(event)
            
            self.last_io_counters = current_counters
            
        except Exception as e:
            logger.error(f"Error collecting disk metrics: {e}")
