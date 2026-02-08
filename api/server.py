# api/server.py
"""
FastAPI server for REST endpoints and real-time data streaming.
"""

import asyncio
import logging
from typing import Optional

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    raise ImportError("FastAPI not installed. Install via: pip install fastapi uvicorn")

from ingestion.event_bus import EventType

logger = logging.getLogger(__name__)


class APIServer:
    """FastAPI server for system monitoring"""
    
    def __init__(self, app: FastAPI, stream_processor, ml_pipeline: dict, host: str = "0.0.0.0", port: int = 8000):
        self.app = app
        self.stream_processor = stream_processor
        self.ml_pipeline = ml_pipeline
        self.host = host
        self.port = port
        self.server = None
        self.running = False
    
    async def start(self):
        """Start API server"""
        logger.info(f"Starting API server on {self.host}:{self.port}")
        self.running = True
        
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        self.server = uvicorn.Server(config)
        
        try:
            await self.server.serve()
        except asyncio.CancelledError:
            logger.info("API server cancelled")
    
    async def stop(self):
        """Stop API server"""
        self.running = False
        if self.server:
            self.server.should_exit = True


def create_api_server(stream_processor, ml_pipeline: dict, host: str = "0.0.0.0", port: int = 8000) -> APIServer:
    """Create and configure FastAPI server"""
    
    app = FastAPI(title="System Monitoring API", version="1.0.0")
    
    # =====================
    # REST ENDPOINTS
    # =====================
    
    @app.get("/")
    async def root():
        """API root"""
        return {
            "service": "System Monitoring Platform",
            "version": "1.0.0",
            "endpoints": [
                "/metrics/realtime",
                "/metrics/history",
                "/anomalies",
                "/trends",
                "/events",
                "/stats",
            ]
        }
    
    @app.get("/metrics/realtime")
    async def get_realtime_metrics():
        """Get current real-time metrics"""
        metric_keys = stream_processor.get_metric_keys()
        metrics = {}
        
        for key in metric_keys:
            stats = stream_processor.get_metric_stats(key)
            metrics[key] = stats
        
        return {
            "timestamp": asyncio.get_event_loop().time(),
            "metrics": metrics,
            "processor_stats": stream_processor.get_processor_stats(),
        }
    
    @app.get("/metrics/history")
    async def get_metric_history(metric_key: str, seconds: int = 300):
        """Get metric history"""
        points = stream_processor.query_metric(metric_key, seconds=seconds)
        
        return {
            "metric_key": metric_key,
            "window_seconds": seconds,
            "point_count": len(points),
            "points": [
                {
                    "timestamp": p.timestamp,
                    "value": p.value,
                    "metadata": p.metadata,
                }
                for p in points
            ]
        }
    
    @app.get("/anomalies")
    async def get_anomalies(limit: int = 50):
        """Get recent anomalies"""
        events = stream_processor.get_recent_events(
            event_type=EventType.ANOMALY,
            limit=limit
        )
        
        return {
            "anomalies": [e.to_dict() for e in events],
            "total": len(events),
        }
    
    @app.get("/trends")
    async def get_trends():
        """Get metric trends"""
        trends = ml_pipeline['trend'].get_trends()
        return {
            "trends": trends,
        }
    
    @app.get("/events")
    async def get_events(event_type: Optional[str] = None, limit: int = 100):
        """Get recent events"""
        event_type_obj = None
        if event_type:
            try:
                event_type_obj = EventType(event_type)
            except ValueError:
                return {"error": f"Invalid event type: {event_type}"}, 400
        
        events = stream_processor.get_recent_events(
            event_type=event_type_obj,
            limit=limit
        )
        
        return {
            "events": [e.to_dict() for e in events],
            "total": len(events),
        }
    
    @app.get("/stats")
    async def get_stats():
        """Get system statistics"""
        return {
            "event_bus": stream_processor.event_bus.get_metrics(),
            "processor": stream_processor.get_processor_stats(),
        }
    
    return APIServer(app, stream_processor, ml_pipeline, host, port)
