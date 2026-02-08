# collectors/memory.py
"""Memory metrics collection"""

import asyncio
import logging

try:
    import psutil
except ImportError:
    raise ImportError("psutil not installed")

from ingestion.event_bus import EventBus, SystemEvent, EventType

logger = logging.getLogger(__name__)


class MemoryCollector:
    """Collects memory metrics (RSS, VMS, swap, etc.)"""
    
    def __init__(self, event_bus: EventBus, interval: float = 1.0):
        self.event_bus = event_bus
        self.interval = interval
        self.running = False
    
    async def start(self):
        logger.info(f"MemoryCollector started (interval={self.interval}s)")
        self.running = True
        
        try:
            while self.running:
                await self._collect_metrics()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("MemoryCollector cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        self.running = False
    
    async def _collect_metrics(self):
        try:
            vmem = psutil.virtual_memory()
            event = SystemEvent(
                event_type=EventType.MEMORY_METRIC,
                source="collector::memory",
                data={
                    'type': 'virtual',
                    'total': vmem.total,
                    'available': vmem.available,
                    'used': vmem.used,
                    'free': vmem.free,
                    'percent': vmem.percent,
                }
            )
            await self.event_bus.publish(event)
            
            swap = psutil.swap_memory()
            event = SystemEvent(
                event_type=EventType.MEMORY_METRIC,
                source="collector::memory",
                data={
                    'type': 'swap',
                    'total': swap.total,
                    'used': swap.used,
                    'free': swap.free,
                    'percent': swap.percent,
                }
            )
            await self.event_bus.publish(event)
            
        except Exception as e:
            logger.error(f"Error collecting memory metrics: {e}")
