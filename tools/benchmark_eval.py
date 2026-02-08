#!/usr/bin/env python3
"""
Benchmarking & evaluation script: run collectors with synthetic load injection,
detect anomalies, align with ground truth, compute precision/recall/F1/AUC.

Usage:
  python tools/benchmark_eval.py \\
    --duration 120 \\
    --collectors cpu memory \\
    --spike-metric cpu.total \\
    --spike-times 30,60,90 \\
    --spike-duration 5 \\
    --outdir ./benchmark_results
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger("benchmark")

from ingestion.event_bus import EventBus
from ingestion.stream_processor import StreamProcessor
from ml.anomaly_detection import StackedAnomalyDetector

COLLECTOR_MAP = {
    'cpu': ('collectors.cpu', 'CPUCollector'),
    'memory': ('collectors.memory', 'MemoryCollector'),
    'disk': ('collectors.disk', 'DiskCollector'),
    'network': ('collectors.network', 'NetworkCollector'),
    'processes': ('collectors.processes', 'ProcessCollector'),
}


async def _create_collector(event_bus, name, interval=1.0):
    """Dynamically import and instantiate collector."""
    if name not in COLLECTOR_MAP:
        raise ValueError(f"Unknown collector: {name}")
    module_name, class_name = COLLECTOR_MAP[name]
    module = __import__(module_name, fromlist=[class_name])
    cls = getattr(module, class_name)
    return cls(event_bus, interval=interval)


async def inject_synthetic_spikes(spike_times, spike_duration, process_count=2):
    """
    Inject synthetic CPU spikes at specified times by spawning stress processes.
    
    Args:
        spike_times: list of absolute timestamps (seconds from epoch)
        spike_duration: duration of each spike in seconds
        process_count: number of stress processes
    """
    logger.info(f"Synthetic spike injector ready. Will spike at: {spike_times}")
    
    active_spike = None
    
    try:
        while True:
            now = time.time()
            
            # Check if we should start a spike
            if active_spike is None:
                for spike_time in spike_times:
                    if spike_time <= now < spike_time + spike_duration:
                        logger.info(f"🔥 STARTING SPIKE at {now}")
                        # Start stress-ng if available
                        try:
                            active_spike = {
                                'start_time': now,
                                'spike_time': spike_time,
                                'process': subprocess.Popen(
                                    ['stress-ng', '--cpu', str(process_count), 
                                     '--cpu-load', '100', '--timeout', f'{spike_duration}s'],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL
                                )
                            }
                        except FileNotFoundError:
                            logger.warning("stress-ng not found; skipping synthetic injection")
                            active_spike = None
                        break
            
            # Check if spike should end
            if active_spike and now >= active_spike['spike_time'] + spike_duration:
                try:
                    active_spike['process'].terminate()
                    active_spike['process'].wait(timeout=2)
                except:
                    pass
                logger.info(f"🔥 ENDING SPIKE at {now}")
                active_spike = None
            
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        if active_spike:
            try:
                active_spike['process'].terminate()
            except:
                pass


async def run_benchmark(duration, collector_names, spike_metric, spike_times, spike_duration, outdir, window_seconds):
    """
    Run collectors + spike injection + detection, save results.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Compute absolute spike times (relative to now)
    now = time.time()
    abs_spike_times = [now + t for t in spike_times]
    
    logger.info(f"Starting benchmark: {duration}s, spikes at {abs_spike_times}")

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

    # Start synthetic spike injector
    spike_task = asyncio.create_task(inject_synthetic_spikes(abs_spike_times, spike_duration))

    logger.info(f"Running benchmark for {duration}s...")
    try:
        await asyncio.sleep(duration)
    except asyncio.CancelledError:
        pass

    # Stop all tasks
    for c in collectors:
        try:
            await c.stop()
        except:
            pass
    
    spike_task.cancel()
    
    for t in collector_tasks:
        t.cancel()

    await stream_processor.stop()
    sp_task.cancel()

    await asyncio.sleep(0.5)

    # Export metrics
    metrics_out = outdir / 'metrics.json'
    dump = {}
    for key in stream_processor.get_metric_keys():
        window = stream_processor.get_window(key, seconds=duration + 5)
        dump[key] = window

    with open(metrics_out, 'w') as f:
        json.dump(dump, f)
    logger.info(f"Wrote {len(dump)} metrics to {metrics_out}")

    # Event bus stats
    stats_out = outdir / 'stats.json'
    with open(stats_out, 'w') as f:
        json.dump(event_bus.get_metrics(), f)

    # Ground truth: binary labels per timestamp (1 = inside a spike, 0 = normal)
    ground_truth = {}
    for key in stream_processor.get_metric_keys():
        values = stream_processor.get_window(key, seconds=duration + 5)
        labels = []
        # For each value, determine if it was collected during a spike
        # This is approximate; we map by sample index
        for i in range(len(values)):
            sample_time = now + (i / len(values)) * duration  # Rough estimate
            in_spike = any(t <= sample_time < t + spike_duration for t in abs_spike_times)
            labels.append(1 if in_spike else 0)
        ground_truth[key] = labels

    gt_out = outdir / 'ground_truth.json'
    with open(gt_out, 'w') as f:
        json.dump(ground_truth, f)

    # Run offline detection with sliding window
    detector = StackedAnomalyDetector()
    detections = []
    detection_scores = {}  # metric_key -> [scores]
    
    for key in stream_processor.get_metric_keys():
        values = stream_processor.get_window(key, seconds=duration + 5)
        detection_scores[key] = []
        
        if len(values) < 10:
            continue

        # Sliding window detection
        for i in range(10, len(values)):
            window = values[max(0, i - min(window_seconds, len(values))): i + 1]
            try:
                res = detector.detect(key, window)
                detection_scores[key].append({
                    'idx': i,
                    'is_anomaly': res.get('is_anomaly', False),
                    'confidence': res.get('confidence', 0.0),
                    'method': res.get('method', 'unknown')
                })
                if res.get('is_anomaly'):
                    detections.append({
                        'metric_key': key,
                        'index': i,
                        'timestamp': now + (i / len(values)) * duration,
                        'confidence': res['confidence'],
                        'method': res['method']
                    })
            except Exception as e:
                logger.debug(f"Detection failed for {key}[{i}]: {e}")

    det_out = outdir / 'detections.json'
    with open(det_out, 'w') as f:
        json.dump(detections, f)
    logger.info(f"Found {len(detections)} anomaly detections")

    # Compute evaluation metrics (precision, recall, F1, AUC) for primary spike metric
    evaluation = {}
    if spike_metric in ground_truth:
        gt_labels = ground_truth[spike_metric]
        
        # Align detection scores to ground truth (pad if needed)
        scores = [d['confidence'] for d in detection_scores.get(spike_metric, [])]
        if scores:
            # Pad scores to match ground truth length
            if len(scores) < len(gt_labels):
                scores.extend([0.0] * (len(gt_labels) - len(scores)))
            scores = scores[:len(gt_labels)]
            
            # Threshold at 0.5
            predictions = [1 if s >= 0.5 else 0 for s in scores]
            
            # Confusion matrix
            tp = sum(1 for i in range(len(gt_labels)) if gt_labels[i] == 1 and predictions[i] == 1)
            fp = sum(1 for i in range(len(gt_labels)) if gt_labels[i] == 0 and predictions[i] == 1)
            tn = sum(1 for i in range(len(gt_labels)) if gt_labels[i] == 0 and predictions[i] == 0)
            fn = sum(1 for i in range(len(gt_labels)) if gt_labels[i] == 1 and predictions[i] == 0)
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            
            # Rough AUC via ranking
            try:
                from sklearn.metrics import roc_auc_score
                auc = roc_auc_score(gt_labels, scores) if len(set(gt_labels)) > 1 else 0.5
            except:
                auc = None
            
            evaluation[spike_metric] = {
                'ground_truth_positives': sum(gt_labels),
                'predictions_positives': sum(predictions),
                'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
                'precision': float(precision),
                'recall': float(recall),
                'f1': float(f1),
                'auc': float(auc) if auc else None
            }

    eval_out = outdir / 'evaluation.json'
    with open(eval_out, 'w') as f:
        json.dump(evaluation, f, indent=2)

    # Summary report
    summary = {
        'duration_seconds': duration,
        'collectors_started': [c.__class__.__name__ for c in collectors],
        'spike_metric': spike_metric,
        'spike_times_absolute': abs_spike_times,
        'spike_duration': spike_duration,
        'metrics_collected': len(dump),
        'total_samples': sum(len(v) for v in dump.values()),
        'events_processed': event_bus.get_metrics()['total_events'],
        'detections_count': len(detections),
        'evaluation': evaluation
    }

    summary_out = outdir / 'summary.json'
    with open(summary_out, 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info(f"✅ Benchmark complete. Results in {outdir}/")
    logger.info(f"   - summary.json: {summary_out}")
    logger.info(f"   - evaluation.json: {eval_out}")
    
    if evaluation.get(spike_metric):
        ev = evaluation[spike_metric]
        logger.info(f"   📊 {spike_metric}:")
        logger.info(f"      Precision: {ev['precision']:.3f}, Recall: {ev['recall']:.3f}, F1: {ev['f1']:.3f}")
        if ev.get('auc'):
            logger.info(f"      AUC: {ev['auc']:.3f}")

    return summary


def main():
    parser = argparse.ArgumentParser(description='Run benchmark with synthetic spikes and evaluation')
    parser.add_argument('--duration', type=int, default=120, help='Collection duration (seconds)')
    parser.add_argument('--collectors', nargs='+', default=['cpu', 'memory'], help='Collectors to run')
    parser.add_argument('--spike-metric', type=str, default='cpu.total', help='Metric to evaluate (for precision/recall)')
    parser.add_argument('--spike-times', type=str, default='30,60,90', help='Spike start times (relative seconds, comma-sep)')
    parser.add_argument('--spike-duration', type=int, default=5, help='Duration of each spike (seconds)')
    parser.add_argument('--outdir', type=str, default='benchmark_results', help='Output directory')
    parser.add_argument('--window', type=int, default=60, help='Detection window seconds')

    args = parser.parse_args()

    spike_times = [int(t) for t in args.spike_times.split(',')]

    asyncio.run(run_benchmark(
        args.duration,
        args.collectors,
        args.spike_metric,
        spike_times,
        args.spike_duration,
        args.outdir,
        args.window
    ))


if __name__ == '__main__':
    main()
