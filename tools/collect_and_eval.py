#!/usr/bin/env python3
"""
CLI tool to collect metrics from collectors via EventBus/StreamProcessor,
export data, run the stacked anomaly detector offline, and save results.

Usage examples:
  # Collect 120s using CPU+memory collectors and run detection
  python tools/collect_and_eval.py --duration 120 --collectors cpu memory --outdir output

  # Collect 60s, export CSV and JSON
  python tools/collect_and_eval.py --duration 60 --outdir output --export-csv

This script uses the project's `EventBus`, `StreamProcessor`, collector classes,
and `StackedAnomalyDetector` from `ml/anomaly_detection.py`.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
import logging

# Add parent directory to path so imports work from any cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("collect_and_eval")

# Local imports (project modules)
from ingestion.event_bus import EventBus
from ingestion.stream_processor import StreamProcessor
from ml.anomaly_detection import StackedAnomalyDetector

# Lazy import collectors mapping
COLLECTOR_MAP = {
    'cpu': ('collectors.cpu', 'CPUCollector'),
    'memory': ('collectors.memory', 'MemoryCollector'),
    'disk': ('collectors.disk', 'DiskCollector'),
    'network': ('collectors.network', 'NetworkCollector'),
    'processes': ('collectors.processes', 'ProcessCollector'),
}


async def _create_collector(event_bus, name, interval=1.0):
    """Dynamically import and instantiate collector by name."""
    if name not in COLLECTOR_MAP:
        raise ValueError(f"Unknown collector: {name}")
    module_name, class_name = COLLECTOR_MAP[name]
    module = __import__(module_name, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cls(event_bus, interval=interval)


async def run_collection(duration: int, collector_names, outdir: str, export_csv: bool, window_seconds: int):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    event_bus = EventBus(buffer_size=10000)
    stream_processor = StreamProcessor(event_bus, history_size=10000)

    # Start stream processor
    sp_task = asyncio.create_task(stream_processor.start())

    # Instantiate collectors
    collectors = []
    collector_tasks = []
    for name in collector_names:
        try:
            col = await _create_collector(event_bus, name)
            collectors.append(col)
            t = asyncio.create_task(col.start())
            collector_tasks.append(t)
            logger.info(f"Started collector: {name}")
        except Exception as e:
            logger.warning(f"Failed to start collector {name}: {e}")

    logger.info(f"Collecting for {duration}s...")
    start_ts = time.time()
    try:
        await asyncio.sleep(duration)
    except asyncio.CancelledError:
        pass

    # Stop collectors
    for c in collectors:
        try:
            await c.stop()
        except Exception:
            pass

    # Cancel collector tasks
    for t in collector_tasks:
        t.cancel()

    # Stop stream processor
    await stream_processor.stop()
    sp_task.cancel()

    # Wait briefly for tasks to settle
    await asyncio.sleep(0.5)

    # Save metrics as JSON per metric key
    metrics_out = outdir / 'metrics.json'
    dump = {}
    for key in stream_processor.get_metric_keys():
        window = stream_processor.get_window(key, seconds=duration + 5)
        dump[key] = window

    with open(metrics_out, 'w') as f:
        json.dump(dump, f)
    logger.info(f"Wrote metrics JSON to {metrics_out}")

    # Export CSV if requested
    if export_csv:
        csv_path = outdir / 'metrics_export.csv'
        try:
            stream_processor.export_metrics_csv(str(csv_path), duration_seconds=duration)
            logger.info(f"Exported CSV to {csv_path}")
        except Exception as e:
            logger.warning(f"CSV export failed: {e}")

    # Basic platform stats
    stats_out = outdir / 'stats.json'
    with open(stats_out, 'w') as f:
        json.dump(event_bus.get_metrics(), f)
    logger.info(f"Wrote event bus stats to {stats_out}")

    # Run offline anomaly detection over each metric (sliding windows)
    detector = StackedAnomalyDetector()
    detections = []
    for key in stream_processor.get_metric_keys():
        values = stream_processor.get_window(key, seconds=window_seconds)
        if len(values) < 10:
            continue
        # Sliding over values to produce detection points
        for i in range(10, len(values)):
            window = values[max(0, i - window_seconds): i + 1]
            try:
                res = detector.detect(key, window)
            except Exception as e:
                logger.debug(f"Detector failed for {key}: {e}")
                continue
            if res.get('is_anomaly'):
                res['timestamp'] = time.time()
                detections.append(res)

    detections_out = outdir / 'detections.json'
    with open(detections_out, 'w') as f:
        json.dump(detections, f)
    logger.info(f"Wrote detections to {detections_out} (count={len(detections)})")

    return {
        'metrics_file': str(metrics_out),
        'detections_file': str(detections_out),
        'stats_file': str(stats_out),
        'duration_seconds': duration,
        'collectors_started': [c.__class__.__name__ for c in collectors]
    }


def main():
    parser = argparse.ArgumentParser(description='Collect metrics and run offline anomaly detection')
    parser.add_argument('--duration', type=int, default=60, help='Collection duration in seconds')
    parser.add_argument('--collectors', nargs='+', default=['cpu','memory'], help='Collectors to run')
    parser.add_argument('--outdir', type=str, default='output', help='Output directory')
    parser.add_argument('--export-csv', action='store_true', help='Export CSV via StreamProcessor.export_metrics_csv')
    parser.add_argument('--window', type=int, default=300, help='Window seconds for detection')

    args = parser.parse_args()

    asyncio.run(run_collection(args.duration, args.collectors, args.outdir, args.export_csv, args.window))


if __name__ == '__main__':
    main()
