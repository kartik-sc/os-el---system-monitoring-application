# collectors/network.py
"""Network I/O metrics collection"""

import asyncio
import logging

try:
    import psutil
except ImportError:
    raise ImportError("psutil not installed")

from ingestion.event_bus import EventBus, SystemEvent, EventType

logger = logging.getLogger(__name__)


class NetworkCollector:
    """Collects network I/O metrics"""
    
    def __init__(self, event_bus: EventBus, interval: float = 2.0):
        self.event_bus = event_bus
        self.interval = interval
        self.running = False
        self.last_net_io = None
    
    async def start(self):
        logger.info(f"NetworkCollector started (interval={self.interval}s)")
        self.running = True
        self.last_net_io = psutil.net_io_counters()
        
        try:
            while self.running:
                await self._collect_metrics()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("NetworkCollector cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        self.running = False
    
    async def _collect_metrics(self):
        try:
            current = psutil.net_io_counters()
            
            if self.last_net_io:
                bytes_sent = current.bytes_sent - self.last_net_io.bytes_sent
                bytes_recv = current.bytes_recv - self.last_net_io.bytes_recv
                
                event = SystemEvent(
                    event_type=EventType.NETWORK_METRIC,
                    source="collector::network",
                    data={
                        'bytes_sent_delta': bytes_sent,
                        'bytes_recv_delta': bytes_recv,
                        'packets_sent': current.packets_sent - self.last_net_io.packets_sent,
                        'packets_recv': current.packets_recv - self.last_net_io.packets_recv,
                        'errin': current.errin,
                        'errout': current.errout,
                        'dropin': current.dropin,
                        'dropout': current.dropout,
                    }
                )
                await self.event_bus.publish(event)
            
            self.last_net_io = current
            
        except Exception as e:
            logger.error(f"Error collecting network metrics: {e}")
