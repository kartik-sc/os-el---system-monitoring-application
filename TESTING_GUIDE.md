# Testing & Evaluation Tools

This guide explains the CLI tools available to test and evaluate the hybrid monitoring platform.

## Quick Start

```bash
cd /home/kartik/osel/monitor
source venv/bin/activate

# Option 1: Smoke test (10s, basic collection)
python3 tools/collect_and_eval.py --duration 10 --outdir smoke_test

# Option 2: Full benchmark (60s, synthetic spikes, evaluation metrics)
python3 tools/benchmark_eval.py --duration 60 --outdir benchmark_results

# Option 3: View formatted report
python3 tools/report_metrics.py benchmark_results
```

---

## Tool 1: `collect_and_eval.py` – Basic Data Collection

Collects metrics from configured collectors via `EventBus` and `StreamProcessor`, exports as JSON.

### Usage

```bash
python3 tools/collect_and_eval.py \
  --duration 60 \
  --collectors cpu memory disk network \
  --outdir output_dir \
  --export-csv \
  --window 300
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--duration` | 60 | Collection duration in seconds |
| `--collectors` | cpu memory | Space-separated list: cpu, memory, disk, network, processes |
| `--outdir` | output | Output directory for results |
| `--export-csv` | (flag) | Export metrics to CSV via StreamProcessor |
| `--window` | 300 | Detection window seconds (for anomaly detector) |

### Output Files

```
output_dir/
├── metrics.json           # Per-metric value arrays
│                          # Format: {"metric_key": [val1, val2, ...], ...}
├── stats.json             # EventBus statistics
│                          # {total_events, dropped_events, buffer_size, ...}
├── detections.json        # Anomalies found by ensemble detector
│                          # [{metric_key, confidence, method, ...}, ...]
└── metrics_export.csv     # (if --export-csv) CSV time-series
```

### Example

```bash
# Collect CPU+memory for 30s
python3 tools/collect_and_eval.py --duration 30 --collectors cpu memory --outdir test1

# Inspect results
cat test1/metrics.json | python3 -m json.tool | head -30
cat test1/stats.json | python3 -m json.tool
```

---

## Tool 2: `benchmark_eval.py` – Full Evaluation with Synthetic Load

Runs collectors with synthetic CPU spikes (via `stress-ng`), detects anomalies, computes precision/recall/F1/AUC.

### Prerequisites

```bash
# Install stress-ng for synthetic load injection
sudo apt-get install stress-ng

# Or the benchmark will run without synthetic spikes (collector data only)
```

### Usage

```bash
python3 tools/benchmark_eval.py \
  --duration 120 \
  --collectors cpu memory \
  --spike-metric cpu.total \
  --spike-times 20,50,80 \
  --spike-duration 10 \
  --outdir benchmark_results \
  --window 30
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--duration` | 120 | Total run duration (seconds) |
| `--collectors` | cpu memory | Collectors to start |
| `--spike-metric` | cpu.total | Primary metric for precision/recall evaluation |
| `--spike-times` | 30,60,90 | Spike start times (relative seconds, comma-sep) |
| `--spike-duration` | 5 | Duration of each spike (seconds) |
| `--outdir` | benchmark_results | Output directory |
| `--window` | 60 | Detection window for sliding-window analysis |

### Output Files

```
benchmark_results/
├── summary.json           # Test config + high-level results
├── evaluation.json        # Precision, Recall, F1, AUC per metric
├── detections.json        # Timestamped anomaly detections
├── ground_truth.json      # Binary labels (0=normal, 1=spike)
├── metrics.json           # Raw collected metric values
└── stats.json             # EventBus statistics
```

### Example: Realistic Scenario

```bash
# 3-minute test with spikes at 30s, 90s, 150s (5s each)
python3 tools/benchmark_eval.py \
  --duration 180 \
  --collectors cpu memory disk network \
  --spike-metric cpu.total \
  --spike-times 30,90,150 \
  --spike-duration 5 \
  --window 30 \
  --outdir realistic_benchmark
```

### Interpreting Results

**Summary metrics:**
- `total_samples`: Number of collected data points
- `events_processed`: EventBus throughput
- `detections_count`: Anomalies flagged by ensemble

**Evaluation metrics (per spike_metric):**
- **Precision**: Of detected anomalies, how many were true spikes? (TP / (TP+FP))
- **Recall**: Of true spikes, how many were detected? (TP / (TP+FN))
- **F1**: Harmonic mean (balance precision & recall)
- **AUC**: Ranking quality (0.5=random, 1.0=perfect)

---

## Tool 3: `report_metrics.py` – Formatted Results Display

Parses benchmark results and prints a formatted summary.

### Usage

```bash
python3 tools/report_metrics.py /path/to/benchmark_results
```

### Output Example

```
======================================================================
                      BENCHMARK RESULTS SUMMARY                       
======================================================================

📋 TEST CONFIGURATION
Duration: 60s
Collectors: CPUCollector, MemoryCollector
Spike Metric: cpu.total
Spike Duration: 5s × 3 injections

📊 COLLECTION METRICS
Metrics Collected  11   
Total Samples      606  
Events Published   661  
Detections Found   43   

🚌 EVENTBUS STATISTICS
Total Events       661  
Dropped Events     0    
Buffer Size        10000
Active Subscribers 0    

🎯 DETECTION QUALITY METRICS
Metric: cpu.total
...Precision/Recall/F1/AUC...
```

---

## Workflows & Examples

### Smoke Test (Verify Installation)

```bash
python3 tools/collect_and_eval.py --duration 5 --collectors cpu --outdir /tmp/smoke
echo "Events published: $(jq '.total_events' /tmp/smoke/stats.json)"
```

### Quick 1-Minute Collection

```bash
python3 tools/collect_and_eval.py --duration 60 --collectors cpu memory --outdir quick_test
python3 tools/report_metrics.py quick_test
```

### Production Benchmark (5-minute test, all collectors)

```bash
python3 tools/benchmark_eval.py \
  --duration 300 \
  --collectors cpu memory disk network processes \
  --spike-metric cpu.total \
  --spike-times 60,120,180,240 \
  --spike-duration 15 \
  --window 30 \
  --outdir prod_benchmark

python3 tools/report_metrics.py prod_benchmark
```

### Offline Analysis (Existing Results)

```bash
# View raw metrics
cat benchmark_results/metrics.json | python3 -m json.tool | head -50

# View detections
cat benchmark_results/detections.json | python3 -m json.tool

# View evaluation
cat benchmark_results/evaluation.json | python3 -m json.tool

# Generate report
python3 tools/report_metrics.py benchmark_results
```

---

## Interpreting Metrics

### EventBus Health

| Metric | Healthy | Warning |
|--------|---------|---------|
| `total_events` | > 10 | Should increase over time |
| `dropped_events` | = 0 | >0 indicates backpressure |
| `buffer_size` | 10,000 | Adjust if hitting limits |
| `active_subscribers` | > 0 | Should have StreamProcessor |

### Collection Quality

| Metric | Expected |
|--------|----------|
| `Samples per metric` | ~1 Hz × duration (e.g., 60 samples for 60s) |
| `Total events` | 50-100 per second (5 collectors) |
| `Event loss` | 0 (no dropped events) |

### Detection Quality (Benchmark)

| Metric | Good | Acceptable |
|--------|------|-----------|
| **Precision** | > 0.8 | > 0.7 |
| **Recall** | > 0.7 | > 0.6 |
| **F1-Score** | > 0.75 | > 0.65 |
| **ROC-AUC** | > 0.85 | > 0.75 |

Note: Adjust `--window` and `--spike-duration` for better alignment.

---

## Troubleshooting

### "stress-ng not found"
```bash
sudo apt-get install stress-ng
# Or benchmark will run without synthetic spikes
```

### "ModuleNotFoundError: No module named..."
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Low detection metrics (Precision=0, Recall=0)
- **Cause**: Window size too large or spike duration too short
- **Fix**: Try `--window 5 --spike-duration 10` (larger spikes, smaller windows)

### Zero events in stats
- **Cause**: Collectors failed to start
- **Fix**: Check logs, verify psutil installed: `pip install psutil`

---

## Advanced: Batch Testing

Run multiple benchmarks with different configurations:

```bash
#!/bin/bash

for window in 5 10 30 60; do
  echo "Testing window=$window"
  python3 tools/benchmark_eval.py \
    --duration 120 \
    --window $window \
    --outdir "results_window_${window}"
  
  echo "Results for window=$window:"
  python3 tools/report_metrics.py "results_window_${window}" | grep -A5 "Detection Quality"
done
```

---

## Next Steps

1. **Run smoke test**: Verify collectors start and data flows
2. **Run basic benchmark**: Test with default spikes
3. **Adjust thresholds**: Fine-tune detection for your workload
4. **Monitor metrics**: Track precision/recall/AUC over time
5. **Deploy & integrate**: Use results to configure production

---

**Last Updated**: 2026-02-08  
**Tools Version**: 1.0.0
