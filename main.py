# main.py
"""
Hybrid System Monitoring Platform with CLI Dashboard
Main orchestrator coordinating eBPF, collectors, ingestion, ML, and dashboard.
"""

import asyncio
import logging
import signal
import sys
import json
from pathlib import Path
from typing import Optional

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('system_monitor.log')
    ]
)
logger = logging.getLogger(__name__)


class SystemMonitoringPlatform:
    """Orchestrates the entire monitoring system lifecycle."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        use_api: bool = False,
        use_dashboard: bool = True,
    ):
        self.config = self._load_config(config_path)
        self.running = False

        self.event_bus = None
        self.stream_processor = None
        self.ebpf_loaders = []
        self.collectors = []
        self.ml_pipeline = {}
        self.api_server = None
        self.dashboard = None

        self.use_api = use_api
        self.use_dashboard = use_dashboard

    # -------------------------------------------------
    # Config
    # -------------------------------------------------
    def _load_config(self, config_path: Optional[str]) -> dict:
        default_config = {
            "ebpf": {
                "enable_syscall_trace": True,
                "enable_exec_monitor": True,
                "enable_io_monitor": True,
            },
            "collectors": {
                "cpu_interval": 1.0,
                "memory_interval": 1.0,
                "disk_interval": 2.0,
                "network_interval": 2.0,
                "process_interval": 3.0,
            },
            "ml": {
                "enable_trend_prediction": True,
            },
            "dashboard": {
                "enable": True,
            },
            "api": {
                "host": "0.0.0.0",
                "port": 8000,
            },
        }

        if config_path and Path(config_path).exists():
            try:
                with open(config_path) as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                logger.info(f"Loaded config from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}, using defaults")

        return default_config

    # -------------------------------------------------
    # Initialization
    # -------------------------------------------------
    async def initialize(self):
        logger.info("=" * 60)
        logger.info("Initializing System Monitoring Platform")
        logger.info("=" * 60)

        # Event bus
        from ingestion.event_bus import EventBus
        self.event_bus = EventBus(buffer_size=10000)
        logger.info("✓ Event Bus initialized")

        # Stream processor
        from ingestion.stream_processor import StreamProcessor
        self.stream_processor = StreamProcessor(self.event_bus)
        logger.info("✓ Stream Processor initialized")

        # eBPF loaders
        if self.config["ebpf"]["enable_syscall_trace"]:
            try:
                from ebpf.loaders.syscall_loader import SyscallLoader
                self.ebpf_loaders.append(SyscallLoader(self.event_bus))
            except Exception as e:
                logger.warning(f"Syscall loader disabled: {e}")

        if self.config["ebpf"]["enable_exec_monitor"]:
            try:
                from ebpf.loaders.exec_loader import ExecLoader
                self.ebpf_loaders.append(ExecLoader(self.event_bus))
            except Exception as e:
                logger.warning(f"Exec loader disabled: {e}")

        if self.config["ebpf"]["enable_io_monitor"]:
            try:
                from ebpf.loaders.io_loader import IOLoader
                self.ebpf_loaders.append(IOLoader(self.event_bus))
            except Exception as e:
                logger.warning(f"IO loader disabled: {e}")

        logger.info(f"✓ Loaded {len(self.ebpf_loaders)} eBPF loaders")

        # Collectors
        from collectors.cpu import CPUCollector
        from collectors.memory import MemoryCollector
        from collectors.disk import DiskCollector
        from collectors.network import NetworkCollector
        from collectors.processes import ProcessCollector

        self.collectors = [
            CPUCollector(self.event_bus, self.config["collectors"]["cpu_interval"]),
            MemoryCollector(self.event_bus, self.config["collectors"]["memory_interval"]),
            DiskCollector(self.event_bus, self.config["collectors"]["disk_interval"]),
            NetworkCollector(self.event_bus, self.config["collectors"]["network_interval"]),
            ProcessCollector(self.event_bus, self.config["collectors"]["process_interval"]),
        ]
        logger.info(f"✓ Initialized {len(self.collectors)} collectors")

        # ML pipelines (FIXED API)
        from ml.anomaly_detection import AnomalyDetectionPipeline
        from ml.trend_prediction import TrendPredictionPipeline

        self.ml_pipeline["anomaly"] = AnomalyDetectionPipeline(self.stream_processor)
        self.ml_pipeline["trend"] = TrendPredictionPipeline(
            self.stream_processor,
            enable=self.config["ml"]["enable_trend_prediction"],
        )
        logger.info("✓ ML pipelines initialized")

        # Dashboard
        if self.use_dashboard and self.config["dashboard"]["enable"]:
            from dashboard.cli import RichDashboard
            self.dashboard = RichDashboard(self.stream_processor, self.ml_pipeline)
            logger.info("✓ CLI Dashboard initialized")

        self.running = True
        logger.info("=" * 60)
        logger.info("✅ Initialization complete")
        logger.info("=" * 60)

    # -------------------------------------------------
    # Start / Stop
    # -------------------------------------------------
    async def start(self):
        if not self.running:
            await self.initialize()

        tasks = []

        for loader in self.ebpf_loaders:
            tasks.append(asyncio.create_task(loader.start()))

        for collector in self.collectors:
            tasks.append(asyncio.create_task(collector.start()))

        tasks.append(asyncio.create_task(self.stream_processor.start()))

        if "anomaly" in self.ml_pipeline:
            tasks.append(asyncio.create_task(self.ml_pipeline["anomaly"].start()))

        if "trend" in self.ml_pipeline:
            tasks.append(asyncio.create_task(self.ml_pipeline["trend"].start()))

        if self.dashboard:
            tasks.append(asyncio.create_task(self.dashboard.start()))

        logger.info(f"🚀 Started {len(tasks)} tasks")

        await asyncio.gather(*tasks)

    async def stop(self):
        logger.info("Stopping platform...")
        self.running = False

        if self.dashboard:
            await self.dashboard.stop()

        if "anomaly" in self.ml_pipeline:
            await self.ml_pipeline["anomaly"].stop()

        if "trend" in self.ml_pipeline:
            await self.ml_pipeline["trend"].stop()

        if self.stream_processor:
            await self.stream_processor.stop()

        for loader in self.ebpf_loaders:
            await loader.stop()

        for collector in self.collectors:
            await collector.stop()

        logger.info("✅ Platform stopped gracefully")

    async def run(self):
        def handle_signal(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        try:
            await self.start()
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            await self.stop()


# -------------------------------------------------
# Entry point
# -------------------------------------------------
async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/monitoring.json")
    parser.add_argument("--api", action="store_true")
    parser.add_argument("--no-dashboard", action="store_true")
    args = parser.parse_args()

    platform = SystemMonitoringPlatform(
        config_path=args.config,
        use_api=args.api,
        use_dashboard=not args.no_dashboard,
    )

    await platform.run()


if __name__ == "__main__":
    asyncio.run(main())

