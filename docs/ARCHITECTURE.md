# ARCHITECTURE.md - Deep Dive

## System Design Overview

### Multi-Layer Monitoring Stack

```
┌─────────────────────────────────────────────────────────────────┐
│ Application Layer (REST API, Dashboards)                        │
│ ├─ FastAPI server (0.0.0.0:8000)                               │
│ ├─ Async endpoints: /metrics, /anomalies, /events              │
│ └─ JSON responses for integration with external tools          │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ Analytics & ML Layer                                             │
│ ├─ AnomalyDetectionPipeline (z-score + Isolation Forest)       │
│ ├─ TrendPredictionPipeline (linear regression)                 │
│ └─ Event classification and scoring                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ Stream Processing Layer                                          │
│ ├─ StreamProcessor: event normalization                         │
│ ├─ TimeSeriesBuffer: circular ring buffer per metric            │
│ ├─ Process enrichment cache                                     │
│ └─ Metric extraction and aggregation                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ Event Bus (Pub-Sub Router)                                       │
│ ├─ async.Queue[SystemEvent] per subscriber                     │
│ ├─ Backpressure: drop oldest on full                           │
│ ├─ Type-based filtering                                         │
│ └─ 10,000 event buffer                                          │
└──────┬──────────────────────────────────┬──────────────────────┘
       │                                  │
   ┌───▼────────────────────┐    ┌───────▼────────────────────┐
   │ Kernel-Space Data      │    │ User-Space Data             │
   ├─ eBPF Loaders:         │    ├─ Collectors:                │
   │  └─ Syscall tracer     │    │  └─ CPU, Memory, Disk,     │
   │  └─ Exec monitor       │    │     Network, Processes     │
   │  └─ IO monitor         │    │                             │
   │ (kprobes, tracepoints) │    │ (psutil-based)             │
   └───┬────────────────────┘    └───────┬────────────────────┘
       │                                  │
┌──────▼──────────────────────────────────▼──────────────────────┐
│ Kernel Space (Linux >= 5.15)                                    │
│ ├─ BPF programs compiled and loaded                            │
│ ├─ Ring buffer for event streaming                            │
│ ├─ Maps: syscall_times (latency), syscall_counts (frequency)  │
│ └─ Minimal CPU overhead (~1-2%)                                │
└─────────────────────────────────────────────────────────────────┘

> Note: In this repository the only implemented eBPF program is `syscall_trace.bpf.c`.
> References to an `exec_monitor` or `io_monitor` are design/extension points and
> templates in the documentation; those programs are not provided as compiled
> kernel programs in this release.
```

## Component Architecture

### 1. Event Bus (Foundation)

```python
EventBus (Pub-Sub Router)
├─ Subscribers: Dict[str, asyncio.Queue]
├─ Filters: Dict[str, Set[EventType]]
├─ Metrics: throughput, dropped events
└─ Methods:
   ├─ subscribe(id, event_types) → Queue
   ├─ publish(event) → broadcast to all queues
   ├─ unsubscribe(id)
   └─ get_metrics() → bus statistics
```

**Design Rationale:**
- Decouples event producers from consumers
- Async-first for non-blocking I/O
- Backpressure handling prevents memory overflow
- Event filtering reduces unnecessary processing

### 2. Stream Processor (Enrichment)

```python
StreamProcessor
├─ Time-Series Storage:
│  └─ metrics: Dict[str, TimeSeriesBuffer]
│     └─ buffer: deque(maxlen=1000 per metric)
├─ Event History:
│  └─ event_history: deque(maxlen=5000)
├─ Process Cache:
│  └─ process_cache: Dict[pid, process_info]
└─ Operations:
   ├─ _extract_metrics(event) → populate time-series
   ├─ _enrich_event(event) → add process context
   ├─ query_metric(key, seconds) → time-window query
   └─ get_metric_stats(key) → min/max/mean/count
```

**Design Rationale:**
- Circular buffers prevent unbounded memory growth
- Process cache avoids repeated `/proc` reads (expensive)
- Time-series storage enables ML feature extraction
- Enrichment adds context without modifying original event

### 3. eBPF Syscall Tracer

```c
// Kernel-Space (BPF Programs)
┌─ sys_enter tracepoint
│  └─ Record entry timestamp in BPF hash map
│     Key: (pid, tid, syscall_nr)
│     Value: ktime_get_ns()
│
└─ sys_exit tracepoint
   ├─ Lookup entry timestamp
   ├─ Calculate latency = exit_time - entry_time
   ├─ Construct syscall_event struct
   └─ Output to ring buffer
```

**Key Design Patterns:**

1. **Latency Measurement:**
   - Entry-exit pairing for accurate latency
   - Uses kernel nanosecond timer (bpf_ktime_get_ns)
   - Per-pid/tid tracking prevents cross-process interference

2. **Ring Buffer vs Perf Buffer:**
   - Ring buffer (BCC >= 5.8)
   - Single shared circular buffer (more efficient)
   - Automatic overflow handling

3. **Memory Safety:**
   - Fixed-size BPF maps prevent unbounded growth
   - Stack-only local variables (kernel memory)
   - Bounds checking on all array accesses

### 4. User-Space Collectors

```
CollectorBase (Abstract)
├─ start() → spawn collection loop
├─ _collect_metrics() → query system and publish
├─ stop() → graceful shutdown
└─ interval → configurable sampling period

CPUCollector
├─ per_cpu utilization via psutil.cpu_percent(percpu=True)
├─ aggregate utilization
├─ frequency information
└─ core count metadata

MemoryCollector
├─ virtual memory (total, available, used, free)
├─ swap memory metrics
└─ percent utilization

DiskCollector
├─ per-device I/O counters
├─ delta calculation (current - previous)
├─ read/write throughput and latency
└─ I/O operation counts

NetworkCollector
├─ bytes sent/received
├─ packet counts
├─ error and drop statistics
└─ per-interface breakdown (future)

ProcessCollector
├─ top-10 processes by CPU usage
├─ RSS, VMS memory
├─ thread count
└─ command line
```

**Design Rationale:**
- psutil provides OS-independent interface
- Async collection prevents blocking event loop
- Delta calculation provides throughput
- Configurable intervals balance precision vs overhead

### 5. ML Pipeline Architecture

#### Anomaly Detection

```python
AnomalyDetectionPipeline
├─ Input: Query metric from StreamProcessor
├─ Statistical Detection:
│  └─ z_score = |value - mean| / std_dev
│     └─ Anomaly if z_score > 3 (3-sigma rule)
├─ Machine Learning:
│  └─ IsolationForest:
│     ├─ Training: Last 100 points for metric
│     ├─ Prediction: New point classification (-1 = anomaly)
│     └─ Anomaly score: distance from normal space
└─ Output: ANOMALY events to event bus
```

**Detection Methods:**

1. **Z-Score (Statistical):**
   - Advantages: Fast, no training, interpretable
   - Disadvantages: Assumes normal distribution
   - Use case: Sudden spikes/drops

2. **Isolation Forest (ML):**
   - Advantages: Unsupervised, works with multivariate
   - Disadvantages: Requires training data
   - Use case: Complex patterns, behavioral anomalies

#### Trend Prediction

```python
TrendPredictionPipeline
├─ Input: Query metric from StreamProcessor (600-second window)
├─ Linear Regression:
│  └─ fit(timestamps, values)
│     └─ slope = trend magnitude
├─ Classification:
│  ├─ slope > 0 → "increasing"
│  └─ slope < 0 → "decreasing"
└─ Output: TREND events to event bus
```

**Predictions Include:**
- Slope (units/second)
- Direction (increasing/decreasing)
- Magnitude (absolute value)
- Current value (for context)

### 6. REST API Architecture

```
FastAPI Server
├─ GET / → API info
├─ GET /metrics/realtime → Current snapshot
│  └─ Returns: latest stats for all metrics
├─ GET /metrics/history → Time-series query
│  ├─ Query params: metric_key, seconds
│  └─ Returns: Array of (timestamp, value) pairs
├─ GET /anomalies → Recent anomalies
│  ├─ Query params: limit
│  └─ Returns: ANOMALY events from history
├─ GET /trends → Current trends
│  └─ Returns: slope, direction, magnitude per metric
├─ GET /events → Filter and query events
│  ├─ Query params: event_type, limit
│  └─ Returns: Event objects with full context
└─ GET /stats → Platform statistics
   ├─ Event bus metrics
   ├─ Processor statistics
   └─ Performance indicators
```

## Data Flow Example: CPU Spike Detection

```
1. User-space (CPUCollector):
   cpu% = psutil.cpu_percent() = 92.5%
   → Create CPU_METRIC event
   → Publish to EventBus

2. Event Bus:
   → Route to all subscribers
   → StreamProcessor subscriber receives event

3. Stream Processor:
   → Extract metric: cpu.total = 92.5
   → Store in TimeSeriesBuffer
   → Enrich with process context

4. ML Pipeline (AnomalyDetectionPipeline):
   → Query metric: cpu.total (last 300 seconds)
   → Calculate z-score: |92.5 - 25.0| / 15.0 = 4.5
   → Decision: z-score > 3 → ANOMALY

5. Event Bus:
   → Publish ANOMALY event
   → REST API subscriber (for /anomalies endpoint)
   → Dashboards, alerting systems

6. API Client:
   curl http://localhost:8000/anomalies
   → Returns ANOMALY event with:
      - metric_key: "cpu.total"
      - value: 92.5
      - z_score: 4.5
      - timestamp: 1702943456.5
```

## Performance Characteristics

### Throughput

| Component | Events/sec | Latency |
|-----------|-----------|---------|
| Syscall Tracer | 100K+ | <1ms (ring buffer) |
| Event Bus | 10K+ | <100µs (in-memory queue) |
| Stream Processor | 5K+ | <1ms (enrichment) |
| ML Anomaly | 100 (batch) | 5-50ms (per metric) |

### Memory Usage

| Component | Memory |
|-----------|--------|
| eBPF Programs | ~200KB |
| Event Bus (10K buffer) | ~50MB |
| Stream Processor (1K per metric) | ~50MB (avg) |
| Process Cache | ~1-5MB |
| Time-Series Buffers | Configurable |
| **Total** | **~150-200MB** |

### CPU Overhead

| Source | Overhead |
|--------|----------|
| Syscall Tracing | 1-2% |
| Collectors (5 tasks) | 0.5-1% |
| Stream Processor | 0.2-0.5% |
| ML Pipeline | 0.2-0.3% |
| API Server (idle) | <0.1% |
| **Total (baseline)** | **~2-4%** |

## Scalability Considerations

### Horizontal Scaling

1. **Multiple instances per host:** Not recommended (kernel resource contention)
2. **Multi-host federation:** Use REST API to aggregate
3. **Database backend:** Replace in-memory buffers with time-series DB (InfluxDB, Prometheus)

### Vertical Scaling

1. **Increase buffer sizes:** Modify `buffer_size` in config
2. **Add collectors:** Implement new collector classes
3. **Custom eBPF programs:** Add to `ebpf/programs/` and loaders
4. **ML models:** Extend `ml/` with additional detection methods

## Extension Points

### Adding a New Metric Collector

```python
# collectors/new_metric.py
from ingestion.event_bus import EventBus, SystemEvent, EventType

class NewMetricCollector:
    def __init__(self, event_bus: EventBus, interval: float = 1.0):
        self.event_bus = event_bus
        self.interval = interval
        self.running = False
    
    async def start(self):
        self.running = True
        while self.running:
            # 1. Gather data
            data = self._gather_data()
            # 2. Create event
            event = SystemEvent(
                event_type=EventType.NEW_METRIC,
                source="collector::new_metric",
                data=data
            )
            # 3. Publish
            await self.event_bus.publish(event)
            await asyncio.sleep(self.interval)
    
    async def stop(self):
        self.running = False
```

### Adding New eBPF Program

1. Write `ebpf/programs/new_program.bpf.c`
2. Create `ebpf/loaders/new_loader.py` with BCC compilation
3. Register in `main.py` initialization
4. Events automatically streamed via ring buffer

### Adding Custom ML Model

1. Extend `ml/base_pipeline.py` (create if needed)
2. Implement `start()`, `stop()`, analysis methods
3. Subscribe to relevant events
4. Publish model outputs to event bus

## Security Considerations

1. **eBPF Restrictions:**
   - Programs run in kernel with restricted syscalls
   - Memory access checked by verifier
   - Ring buffer output rate-limited

2. **Process Isolation:**
   - Python process runs as root (required for eBPF)
   - Consider containerization for production
   - Use LSM/AppArmor for policy enforcement

3. **API Security:**
   - Add authentication layer (FastAPI supports JWT)
   - Use HTTPS in production
   - Rate limiting on endpoints (can add with slowapi)

4. **Data Privacy:**
   - Process names/cmdlines logged (consider sanitization)
   - Implement log rotation
   - Consider data retention policies

## References

- [BPF Architecture](https://www.kernel.org/doc/html/latest/bpf/)
- [BCC Documentation](https://github.com/iovisor/bcc)
- [Linux Kernel Observability](https://www.brendangregg.com/ebpf.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Time-Series Databases](https://en.wikipedia.org/wiki/Time_series_database)

---

Last Updated: 2024-12-18
Kernel Support: Linux 5.15+
Python: 3.10+
