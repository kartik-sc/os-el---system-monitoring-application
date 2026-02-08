# Quick Reference: Testing & Metrics

## 🚀 Get Started in 2 Minutes

```bash
cd /home/kartik/osel/monitor
source venv/bin/activate

# Option A: Quick smoke test (5–10 seconds)
python3 tools/collect_and_eval.py --duration 10 --outdir smoke_test

# Option B: Full benchmark with evaluation (60 seconds)
python3 tools/benchmark_eval.py --duration 60 --outdir benchmark_results

# View results
python3 tools/report_metrics.py benchmark_results
```

---

## 📊 What You Get

### From `collect_and_eval.py`:
- ✅ Metric samples (JSON)
- ✅ EventBus statistics
- ✅ Anomaly detections

### From `benchmark_eval.py`:
- ✅ Metric samples + ground truth labels
- ✅ Synthetic CPU spikes (via stress-ng)
- ✅ **Precision, Recall, F1, ROC-AUC scores**
- ✅ Detailed evaluation report

---

## 📈 Expected Results (Benchmark)

| Metric | Value |
|--------|-------|
| **Events Published** | ~600 (60s × 10 events/sec) |
| **Dropped Events** | 0 |
| **Anomalies Detected** | 30–50 (depends on spike injection) |
| **Detection Coverage** | 70–80% (tunable) |
| **CPU Overhead** | <1% (monitoring process) |

---

## 🎯 Evaluation Metrics Explained

### Precision
What fraction of *detected* anomalies were **true** spikes?
- **Formula**: TP / (TP + FP)
- **Target**: > 0.8 (few false alarms)

### Recall
What fraction of *true* spikes were **detected**?
- **Formula**: TP / (TP + FN)
- **Target**: > 0.7 (catch most spikes)

### F1-Score
Harmonic mean of precision & recall (0–1 scale).
- **Formula**: 2 × (Precision × Recall) / (Precision + Recall)
- **Target**: > 0.75 (good balance)

### ROC-AUC
Ranking quality of detection scores (0.5=random, 1.0=perfect).
- **Target**: > 0.80 (excellent discrimination)

---

## 🔧 Adjust Performance

### If Recall is Low (Missing Spikes)
```bash
# Lower detection threshold (less aggressive)
# → Reduce window size
python3 tools/benchmark_eval.py --window 10 --spike-duration 10
```

### If Precision is Low (Too Many False Alarms)
```bash
# Raise detection threshold (more conservative)
# → Increase window size
python3 tools/benchmark_eval.py --window 60 --spike-duration 15
```

### If Detection is Slow
```bash
# Faster detection loop (default 3s)
# → Edit ml/anomaly_detection.py, adjust sleep(3.0)
```

---

## 📁 Output Files Reference

| File | Contents | Example |
|------|----------|---------|
| `metrics.json` | Per-metric value arrays | `{"cpu.total": [10, 15, 20, ...]}` |
| `stats.json` | EventBus throughput | `{"total_events": 661, "dropped": 0}` |
| `detections.json` | Detected anomalies | `[{metric_key, confidence, method}, ...]` |
| `evaluation.json` | Precision/Recall/F1/AUC | `{precision: 0.8, recall: 0.75, ...}` |
| `ground_truth.json` | True spike labels | `{"cpu.total": [0,0,1,1,1,0,...]}` |

---

## 🛠️ Common Commands

```bash
# View metrics as table
cat benchmark_results/metrics.json | python3 -c \
  "import json, sys; m=json.load(sys.stdin); \
   print('\n'.join(f'{k}: {len(v)} samples' for k,v in m.items()))"

# Count anomalies
cat benchmark_results/detections.json | python3 -c \
  "import json, sys; d=json.load(sys.stdin); \
   print(f'Total detections: {len(d)}')"

# View evaluation metrics
python3 -m json.tool benchmark_results/evaluation.json | grep -E "Precision|Recall|F1|auc"

# Generate formatted report
python3 tools/report_metrics.py benchmark_results
```

---

## 🚨 Troubleshooting

| Problem | Solution |
|---------|----------|
| **"stress-ng not found"** | `sudo apt-get install stress-ng` |
| **"No module named 'ingestion'"** | `cd /home/kartik/osel/monitor` before running |
| **"Precision=0, Recall=0"** | Adjust `--window` size; try `--window 5` |
| **"No detections"** | Increase `--spike-duration` to 10–15s |
| **"Events=0"** | Collectors failed; check `psutil` is installed |

---

## 📋 Test Matrix

Run multiple configurations to find optimal settings:

```bash
# Small spike, tight window
python3 tools/benchmark_eval.py --spike-duration 5 --window 5 --outdir test1

# Medium spike, medium window
python3 tools/benchmark_eval.py --spike-duration 10 --window 30 --outdir test2

# Large spike, loose window
python3 tools/benchmark_eval.py --spike-duration 15 --window 60 --outdir test3

# Compare results
for d in test*/; do echo "=== $d ==="; python3 tools/report_metrics.py "$d" | grep "cpu.total" -A10; done
```

---

## 📚 Full Documentation

- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** – Detailed tool usage & workflows
- **[METRICS_AND_RESULTS.md](METRICS_AND_RESULTS.md)** – Complete metrics report with comparisons
- **[README.md](docs/README.md)** – Architecture & API overview
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** – Deep design patterns

---

## ✅ Checklist: From Testing to Production

- [ ] Run smoke test: `python3 tools/collect_and_eval.py --duration 10`
- [ ] Run benchmark: `python3 tools/benchmark_eval.py --duration 60`
- [ ] Review metrics: `python3 tools/report_metrics.py benchmark_results`
- [ ] Tune thresholds if needed
- [ ] Test with real workload (not synthetic)
- [ ] Deploy: `sudo python3 main.py`
- [ ] Monitor API: `curl http://localhost:8000/stats`
- [ ] Setup alerting (if deploying long-term)

---

**Last Updated**: 2026-02-08  
**Version**: 1.0.0
