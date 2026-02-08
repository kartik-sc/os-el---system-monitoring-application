#!/usr/bin/env python3
"""
Quick metrics reporter: Parse benchmark results and display formatted summary.

Usage:
  python tools/report_metrics.py /path/to/benchmark_results
"""

import json
import sys
from pathlib import Path

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

def _print_table(data, headers):
    """Simple table printer (fallback if tabulate not installed)."""
    if HAS_TABULATE:
        return tabulate(data, headers=headers, tablefmt="simple")
    else:
        # Manual formatting
        col_widths = [max(len(str(h)), max(len(str(row[i])) for row in data)) 
                      for i, h in enumerate(headers)]
        header = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
        sep = "  ".join("-" * w for w in col_widths)
        rows = "\n".join("  ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths)) 
                        for row in data)
        return f"{header}\n{sep}\n{rows}"

def format_metrics(results_dir):
    """Load and format metrics from benchmark results directory."""
    
    results_dir = Path(results_dir)
    
    # Load files
    summary = json.load(open(results_dir / 'summary.json'))
    evaluation = json.load(open(results_dir / 'evaluation.json'))
    stats = json.load(open(results_dir / 'stats.json'))
    
    print("\n" + "="*70)
    print("BENCHMARK RESULTS SUMMARY".center(70))
    print("="*70)
    
    # Test configuration
    print("\n📋 TEST CONFIGURATION")
    print("-" * 70)
    print(f"Duration: {summary['duration_seconds']}s")
    print(f"Collectors: {', '.join(summary['collectors_started'])}")
    print(f"Spike Metric: {summary['spike_metric']}")
    print(f"Spike Duration: {summary['spike_duration']}s × {len(summary['spike_times_absolute'])} injections")
    
    # Collection stats
    print("\n📊 COLLECTION METRICS")
    print("-" * 70)
    collection_data = [
        ["Metrics Collected", summary['metrics_collected']],
        ["Total Samples", summary['total_samples']],
        ["Events Published", summary['events_processed']],
        ["Detections Found", summary['detections_count']],
    ]
    print(_print_table(collection_data, ["Metric", "Value"]))
    
    # EventBus stats
    print("\n🚌 EVENTBUS STATISTICS")
    print("-" * 70)
    eventbus_data = [
        ["Total Events", stats['total_events']],
        ["Dropped Events", stats['dropped_events']],
        ["Buffer Size", stats['buffer_size']],
        ["Active Subscribers", stats['active_subscribers']],
    ]
    print(_print_table(eventbus_data, ["Metric", "Value"]))
    
    # Evaluation metrics
    print("\n🎯 DETECTION QUALITY METRICS")
    print("-" * 70)
    for metric_name, metrics in evaluation.items():
        print(f"\nMetric: {metric_name}")
        eval_data = [
            ["Ground Truth Positives", metrics['ground_truth_positives']],
            ["Predicted Positives", metrics['predictions_positives']],
            ["True Positives (TP)", metrics['tp']],
            ["False Positives (FP)", metrics['fp']],
            ["True Negatives (TN)", metrics['tn']],
            ["False Negatives (FN)", metrics['fn']],
            ["Precision", f"{metrics['precision']:.4f}"],
            ["Recall", f"{metrics['recall']:.4f}"],
            ["F1-Score", f"{metrics['f1']:.4f}"],
        ]
        if metrics.get('auc'):
            eval_data.append(["ROC-AUC", f"{metrics['auc']:.4f}"])
        print(_print_table(eval_data, ["Metric", "Value"]))
    
    print("\n" + "="*70)
    print("✅ Benchmark complete. See above for detailed metrics.".center(70))
    print("="*70 + "\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python tools/report_metrics.py <results_dir>")
        sys.exit(1)
    
    try:
        format_metrics(sys.argv[1])
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
