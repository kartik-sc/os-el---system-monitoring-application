# ingestion/event_bus.py
"""
Asynchronous event bus for kernel and user-space events.
Decouples event producers (eBPF, collectors) from consumers (processors, API).
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Enumeration of system events"""
    # Kernel events
    SYSCALL = "syscall"
    EXEC = "exec"
    EXIT = "exit"
    FILE_OPEN = "file_open"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    IO_READ = "io_read"
    IO_WRITE = "io_write"
    NETWORK_SEND = "network_send"
    NETWORK_RECV = "network_recv"
    
    # User-space metrics
    CPU_METRIC = "cpu_metric"
    MEMORY_METRIC = "memory_metric"
    DISK_METRIC = "disk_metric"
    NETWORK_METRIC = "network_metric"
    PROCESS_METRIC = "process_metric"
    
    # ML events
    ANOMALY = "anomaly"
    TREND = "trend"
    ALERT = "alert"


@dataclass
class SystemEvent:
    """
    Unified event schema for all system observations.
    Every event contains: ID, Type, Timestamp, Source, Data, Metadata
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: EventType = EventType.SYSCALL
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"
    pid: int = 0
    tid: int = 0
    comm: str = ""
    uid: int = 0
    gid: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert event to dictionary (JSON-serializable)"""
        event_dict = asdict(self)
        event_dict['event_type'] = self.event_type.value
        event_dict['timestamp_iso'] = datetime.fromtimestamp(self.timestamp).isoformat()
        return event_dict
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict(), default=str)
    
    @staticmethod
    def from_dict(data: dict) -> 'SystemEvent':
        """Reconstruct event from dictionary"""
        data = data.copy()
        if isinstance(data.get('event_type'), str):
            data['event_type'] = EventType(data['event_type'])
        return SystemEvent(**{k: v for k, v in data.items() if k in SystemEvent.__dataclass_fields__})


class EventBus:
    """
    Asynchronous pub-sub event bus for system monitoring.
    Features: multiple queues, backpressure handling, event filtering, metrics
    """
    
    def __init__(self, buffer_size: int = 10000):
        self.buffer_size = buffer_size
        self.subscribers: Dict[str, asyncio.Queue] = {}
        self.filters: Dict[str, set] = {}
        self.metrics = {
            'total_events': 0,
            'dropped_events': 0,
            'subscribers': 0,
            'last_event_timestamp': 0.0,
        }
        self._lock = asyncio.Lock()
        logger.info(f"EventBus initialized with buffer_size={buffer_size}")
    
    async def subscribe(self, 
                       subscriber_id: str, 
                       event_types: Optional[List[EventType]] = None) -> asyncio.Queue:
        """Subscribe to events"""
        async with self._lock:
            if subscriber_id in self.subscribers:
                logger.warning(f"Subscriber {subscriber_id} already exists, recreating")
            
            queue = asyncio.Queue(maxsize=self.buffer_size)
            self.subscribers[subscriber_id] = queue
            
            if event_types:
                self.filters[subscriber_id] = set(event_types)
            else:
                self.filters[subscriber_id] = set(EventType)
            
            self.metrics['subscribers'] = len(self.subscribers)
            logger.info(f"Subscriber '{subscriber_id}' registered")
            
            return queue
    
    async def unsubscribe(self, subscriber_id: str):
        """Unsubscribe and clean up"""
        async with self._lock:
            if subscriber_id in self.subscribers:
                del self.subscribers[subscriber_id]
                if subscriber_id in self.filters:
                    del self.filters[subscriber_id]
                self.metrics['subscribers'] = len(self.subscribers)
                logger.info(f"Subscriber '{subscriber_id}' unregistered")
    
    async def publish(self, event: SystemEvent):
        """Publish event to all subscribers with filtering"""
        async with self._lock:
            self.metrics['total_events'] += 1
            self.metrics['last_event_timestamp'] = event.timestamp
            
            for subscriber_id, queue in self.subscribers.items():
                if self.filters.get(subscriber_id) and \
                   event.event_type not in self.filters[subscriber_id]:
                    continue
                
                if queue.full():
                    try:
                        queue.get_nowait()
                        self.metrics['dropped_events'] += 1
                    except asyncio.QueueEmpty:
                        pass
                
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Event dropped for {subscriber_id}")
    
    def get_metrics(self) -> dict:
        """Return current metrics"""
        return {
            **self.metrics,
            'buffer_size': self.buffer_size,
            'active_subscribers': len(self.subscribers),
        }
    
    async def flush(self):
        """Clear all queues"""
        async with self._lock:
            for queue in self.subscribers.values():
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
