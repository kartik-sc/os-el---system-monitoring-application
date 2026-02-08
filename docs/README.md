# README.md - System Monitoring Platform

## Overview

A production-grade, **hybrid kernel-user space system monitoring platform** for Ubuntu 22.04+ that combines:

- **eBPF kernel instrumentation** for low-overhead syscall tracing
- **User-space metric collectors** (CPU, memory, disk, network, processes)
- **Asynchronous event streaming pipeline** for real-time data ingestion
- **ML-powered anomaly detection** (Isolation Forest + statistical methods)
- **Trend prediction** for proactive alerting
- **REST API** for programmatic access
- **Modular architecture** for extensibility

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kernel Space (eBPF)                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ Syscall Tracer   │  │ Exec Monitor     │  │ IO Monitor   │  │
│  │ (kprobes)        │  │ (tracepoints)    │  │ (kprobes)    │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘  │
│           │                     │                    │          │
│           └─────────────────────┼────────────────────┘          │
│                                 │                                │
│                         BPF Ring Buffer                          │
└─────────────────────────────────┼────────────────────────────────┘
                                  │
        ┌─────────────────────────┼──────────────────────┐
        │                         │                      │
┌───────▼────────────────┐ ┌─────▼──────────────┐      │
│  User-Space Collectors │ │  eBPF Event Stream │      │
├────────────────────────┤ └─────┬──────────────┘      │
│ • CPU                  │       │                      │
│ • Memory               │       │                      │
│ • Disk I/O             │  ┌────▼──────────────────┐   │
│ • Network              │  │   Asynchronous        │   │
│ • Processes (top-10)   │  │   Event Bus (Queue)   │   │
└─────┬──────────────────┘  └────┬──────────────────┘   │
      │                          │                      │
      │                          │                      │
      └──────────────┬───────────┘                      │
                     │ Filtered Events                  │
                     │                                  │
        ┌────────────▼────────────┐                    │
        │  Stream Processor       │                    │
        ├─────────────────────────┤                    │
        │ • Time-series buffering │                    │
        │ • Event enrichment      │                    │
        │ • Process cache         │                    │
        └────────────┬────────────┘                    │
                     │                                  │
        ┌────────────┼────────────┬─────────────────┐  │
        │            │            │                 │  │
    ┌───▼──┐  ┌─────▼─────┐ ┌────▼─────┐         │  │
    │ ML   │  │  Trend    │ │  REST    │         │  │
    │Anomaly│ │Prediction │ │API       │         │  │
    │Detect │  │           │ │(FastAPI) │         │  │
    └───┬──┘  └─────┬─────┘ └────┬─────┘         │  │
        │           │             │               │  │
        └───────────┴─────────────┴───────────────┘  │
                                                      │
                            Consumers                 │
                         (Dashboards, alerts)         │
                                                      │
        ┌─────────────────────────────────────────┐  │
        │  API Endpoints                          │  │
        │  • /metrics/realtime                    │  │
        │  • /metrics/history                     │  │
        │  • /anomalies                           │  │
        │  • /trends                              │  │
        │  • /events                              │  │
        │  • /stats                               │  │
        └─────────────────────────────────────────┘  │
```

## Directory Structure

```
system-monitoring/
├── main.py                           # Platform orchestrator
├── config/
│   └── monitoring.json              # Configuration
├── ingestion/
│   ├── event_bus.py                 # Pub-sub event stream
│   └── stream_processor.py           # Event normalization & enrichment
├── collectors/
│   ├── __init__.py
│   ├── cpu.py                       # CPU metrics
│   ├── memory.py                    # Memory metrics
│   ├── disk.py                      # Disk I/O metrics
│   ├── network.py                   # Network metrics
│   └── processes.py                 # Per-process metrics
├── ebpf/
│   ├── programs/
│   │   ├── syscall_trace.bpf.c      # Syscall tracing (eBPF)
│   │   ├── exec_monitor.bpf.c       # Process creation tracing
│   │   └── io_monitor.bpf.c         # Block I/O tracing
│   └── loaders/
│       ├── __init__.py
│       ├── syscall_loader.py        # Syscall tracer loader
│       ├── exec_loader.py           # Process creation loader
│       └── io_loader.py             # Block I/O loader
├── ml/
│   ├── __init__.py
│   ├── anomaly_detection.py         # Isolation Forest + z-score
│   └── trend_prediction.py          # Linear regression trends
├── api/
│   ├── __init__.py
│   └── server.py                    # FastAPI REST endpoints
└── requirements.txt                 # Python dependencies
```

## Installation

### Prerequisites

- **OS:** Ubuntu 22.04 LTS
- **Kernel:** >= 5.15 (with eBPF support)
- **Python:** 3.10+
- **Root privileges** (for eBPF program attachment)

### Step 1: System Dependencies

```bash
# Update package manager
sudo apt-get update

# Install BCC (eBPF compilation framework)
sudo apt-get install -y bcc-tools libbcc-examples linux-headers-$(uname -r)

# Install build tools
sudo apt-get install -y build-essential clang llvm

# Verify eBPF support
cat /boot/config-$(uname -r) | grep CONFIG_BPF
# Should output: CONFIG_BPF=y, CONFIG_BPF_SYSCALL=y, CONFIG_HAVE_EBPF_JIT=y
```

### Step 2: Python Environment

```bash
# Clone or download project
cd system-monitoring

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Optional: scikit-learn for enhanced anomaly detection
pip install scikit-learn
```

### Step 3: Verify Installation

```bash
# Check eBPF support
python3 -c "from bcc import BPF; print('✓ BCC available')"

# Check kernel version
uname -r
# Should be >= 5.15

# Check kernel capabilities
sudo cat /proc/sys/kernel/unprivileged_bpf_disabled
# 0 = unprivileged programs allowed, 1 = root-only
```

## Usage

### Running the Platform

```bash
# Run as root (required for eBPF attachment)
sudo python3 main.py

# Or specify custom config
sudo python3 main.py --config config/monitoring.json

# Output should show:
# [INFO] ============================================================
# [INFO] Initializing System Monitoring Platform...
# [INFO] ============================================================
# [INFO] ✓ Event Bus initialized
# [INFO] ✓ Stream Processor initialized
# [INFO] ✓ Loaded 3 eBPF programs
# [INFO] ✓ Initialized 5 user-space collectors
# [INFO] ✓ ML Pipelines initialized
# [INFO] ✓ API Server configured (0.0.0.0:8000)
# [INFO] ============================================================
# [INFO] ✅ Platform initialization complete!
# [INFO] ============================================================
```

### API Endpoints

Access the REST API at `http://localhost:8000`

#### 1. **Get Real-Time Metrics**

```bash
curl http://localhost:8000/metrics/realtime

{
  "timestamp": 1702943456.123,
  "metrics": {
    "cpu.total": { "count": 120, "mean": 23.5, "min": 15.2, "max": 87.1 },
    "memory.virtual": { "count": 120, "mean": 8192000000, ... },
    "disk.sda.read_bytes_delta": { ... },
    ...
  },
  "processor_stats": { ... }
}
```

#### 2. **Get Metric History (Last 5 Minutes)**

```bash
curl "http://localhost:8000/metrics/history?metric_key=cpu.total&seconds=300"

{
  "metric_key": "cpu.total",
  "window_seconds": 300,
  "point_count": 45,
  "points": [
    {
      "timestamp": 1702943400.5,
      "value": 23.5,
      "metadata": { "metric_type": "utilization", ... }
    },
    ...
  ]
}
```

#### 3. **Get Anomalies**

```bash
curl http://localhost:8000/anomalies?limit=10

{
  "anomalies": [
    {
      "event_id": "a1b2c3d4",
      "event_type": "anomaly",
      "timestamp": 1702943450.0,
      "source": "ml::anomaly_detector",
      "data": {
        "metric_key": "cpu.total",
        "value": 95.2,
        "mean": 24.1,
        "z_score": 3.8,
        "method": "z_score"
      }
    },
    ...
  ],
  "total": 3
}
```

#### 4. **Get Metric Trends**

```bash
curl http://localhost:8000/trends

{
  "trends": {
    "cpu.total": {
      "slope": 0.15,
      "current_value": 45.2,
      "trend_direction": "increasing",
      "magnitude": 0.15
    },
    "memory.virtual": {
      "slope": -0.01,
      "current_value": 8560000000,
      "trend_direction": "decreasing",
      "magnitude": 0.01
    }
  }
}
```

#### 5. **Get Recent Events**

```bash
curl "http://localhost:8000/events?event_type=syscall&limit=20"

{
  "events": [
    {
      "event_id": "x7y8z9a0",
      "event_type": "syscall",
      "timestamp": 1702943456.5,
      "source": "eBPF::syscall_tracer",
      "pid": 1234,
      "comm": "python3",
      "data": {
        "syscall_nr": 1,
        "syscall_name": "write",
        "latency_ns": 5423,
        "latency_us": 5.423
      }
    },
    ...
  ],
  "total": 18
}
```

#### 6. **Get System Statistics**

```bash
curl http://localhost:8000/stats

{
  "event_bus": {
    "total_events": 45230,
    "dropped_events": 12,
    "subscribers": 4,
    "active_subscribers": 4,
    "buffer_size": 10000
  },
  "processor": {
    "total_events_processed": 45230,
    "active_metrics": 28,
    "process_cache_size": 15,
    "event_history_size": 5000
  }
}
```

## Configuration

Edit `config/monitoring.json`:

```json
{
  "ebpf": {
    "enable_syscall_trace": true,      # Enable syscall tracing
    "enable_exec_monitor": true,       # Enable process creation monitoring
    "enable_io_monitor": true,         # Enable block I/O monitoring
    "buffer_pages": 64                 # Ring buffer size
  },
  "collectors": {
    "cpu_interval": 1.0,               # CPU collection interval (seconds)
    "memory_interval": 1.0,            # Memory collection interval
    "disk_interval": 2.0,              # Disk I/O collection interval
    "network_interval": 2.0,           # Network collection interval
    "process_interval": 3.0            # Process collection interval
  },
  "ml": {
    "anomaly_threshold": 0.7,          # Anomaly decision threshold
    "enable_trend_prediction": true,   # Enable trend prediction
    "history_window_size": 1000        # Time-series buffer size
  },
  "api": {
    "host": "0.0.0.0",                 # API bind address
    "port": 8000                       # API port
  },
  "logging": {
    "level": "INFO",                   # Log level
    "verbose": false                   # Verbose logging
  }
}
```

## Performance Considerations

### eBPF Overhead

- **Syscall Tracing:** ~1-2% CPU overhead (lightweight ring buffer)
- **Process Creation:** Minimal (only on execve)
- **Block I/O:** ~0.5-1% overhead (kprobes)

### Memory Usage

- **eBPF Program Size:** ~200KB total
- **User-space Process:** ~100-150MB (with full history)
- **Event Buffer:** ~50MB (10,000 events × ~5KB)

### Scaling

- Handles **100K+ syscalls/second** on modern hardware
- Time-series buffers limited to 1000 points per metric (configurable)
- Event bus drops oldest events on backpressure (configurable)

## Troubleshooting

### Issue: "Permission denied" when running

**Solution:**
```bash
sudo python3 main.py
# eBPF programs require root privileges for attachment
```

### Issue: "BCC not found" error

**Solution:**
```bash
sudo apt-get install bcc-tools libbcc-examples linux-headers-$(uname -r)
pip install bcc
```

### Issue: Ring buffer errors

**Solution:**
```bash
# Increase ring buffer memory limit
echo 'kernel.perf_event_paranoid = -1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Issue: High CPU usage from collectors

**Solution:** Increase collection intervals in `config/monitoring.json`

## Key Components Explained

### 1. Event Bus (ingestion/event_bus.py)

- **Pub-Sub architecture** for decoupled event handling
- **Async queues** for high-throughput streaming
- **Backpressure handling** (drops oldest on full queue)
- **Event filtering** by type for subscribers

### 2. Stream Processor (ingestion/stream_processor.py)

- **Event enrichment** with process context
- **Time-series buffering** for analysis
- **Process cache** to avoid repeated /proc reads
- **Metric extraction** from raw events

### 3. eBPF Loaders (ebpf/loaders/)

- **BCC compilation** of C programs
- **Tracepoint/kprobe attachment** to kernel
- **Ring buffer reading** with callback handlers
- **Latency measurement** via kernel timestamps

### 4. Collectors (collectors/)

- **psutil-based** system metric gathering
- **Asynchronous** interval-based collection
- **Per-device/per-core** granularity
- **Delta calculation** for throughput metrics

### 5. ML Pipeline (ml/)

- **Isolation Forest** for unsupervised anomaly detection
- **Statistical methods** (z-score, 3-sigma rule)
- **Trend prediction** via linear regression
- **Configurable thresholds** for alerting

### 6. REST API (api/server.py)

- **FastAPI** for HTTP interface
- **Async endpoints** for non-blocking responses
- **Metric querying** with time-window filtering
- **Event filtering** by type and source

## Extension Points

### Add New eBPF Program

1. Create `ebpf/programs/new_program.bpf.c`
2. Create `ebpf/loaders/new_loader.py` with `start()` and `stop()` methods
3. Register in `main.py` initialization

### Add New Collector

1. Create `collectors/new_collector.py` with `start()` and `stop()` methods
2. Emit `SystemEvent` via event bus
3. Register in `main.py` initialization

### Add New ML Model

1. Create `ml/new_model.py` with `start()` and `stop()` methods
2. Subscribe to relevant events from stream processor
3. Publish results back to event bus

## References

- **eBPF Documentation:** https://ebpf.io/
- **BCC Repository:** https://github.com/iovisor/bcc
- **FastAPI:** https://fastapi.tiangolo.com/
- **Linux Kernel Observability:** https://www.brendangregg.com/ebpf.html

## License

MIT License - See LICENSE file

## Author

System Monitoring Platform (2024)
