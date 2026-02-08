# collectors/processes.py
"""Per-process metrics collection"""

import asyncio
import logging

try:
    import psutil
except ImportError:
    raise ImportError("psutil not installed")

from ingestion.event_bus import EventBus, SystemEvent, EventType

logger = logging.getLogger(__name__)


class ProcessCollector:
    """Collects per-process metrics"""
    
    def __init__(self, event_bus: EventBus, interval: float = 3.0):
        self.event_bus = event_bus
        self.interval = interval
        self.running = False
    
    async def start(self):
        logger.info(f"ProcessCollector started (interval={self.interval}s)")
        self.running = True
        
        try:
            while self.running:
                await self._collect_metrics()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("ProcessCollector cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        self.running = False
    
    async def _collect_metrics(self):
        """Collect and publish process metrics (top 10 by CPU/memory)"""
        try:
            processes = psutil.process_iter(
                ['pid', 'name', 'ppid', 'cmdline', 'num_threads', 'memory_info', 'cpu_percent']
            )
            
            top_processes = sorted(
                [p for p in processes if p.info['memory_info']],
                key=lambda x: x.info['cpu_percent'],
                reverse=True
            )[:10]
            
            for proc in top_processes:
                try:
                    mem = proc.info['memory_info']
                    event = SystemEvent(
                        event_type=EventType.PROCESS_METRIC,
                        source="collector::processes",
                        pid=proc.info['pid'],
                        comm=proc.info['name'],
                        data={
                            'ppid': proc.info['ppid'],
                            'rss_bytes': mem.rss,
                            'vms_bytes': mem.vms,
                            'cpu_percent': proc.info['cpu_percent'],
                            'num_threads': proc.info['num_threads'],
                            'cmdline': ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else '',
                        }
                    )
                    await self.event_bus.publish(event)
                except (psutil.NoSuchProcess, Exception):
                    pass
            
        except Exception as e:
            logger.error(f"Error collecting process metrics: {e}")
