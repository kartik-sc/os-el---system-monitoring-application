# ebpf/loaders/exec_loader.py
"""
Placeholder exec process monitoring eBPF loader.
Monitors process creation (execve syscall).
"""

import logging
import asyncio

from ingestion.event_bus import EventBus, SystemEvent, EventType

logger = logging.getLogger(__name__)


class ExecLoader:
    """Monitors process execution"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.running = False
    
    async def start(self):
        """Start exec monitoring"""
        logger.info("ExecLoader started")
        self.running = True
        
        # Placeholder implementation
        # In production, this would attach eBPF probes to execve syscall
        
        try:
            while self.running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("ExecLoader cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        """Stop exec monitoring"""
        self.running = False
        logger.info("ExecLoader stopped")
