# FILE_MANIFEST.md - Complete Project File List

## Overview

This document lists all downloadable files for the Hybrid System Monitoring Platform.

## File Organization

### Core Entry Point

| File | Type | Purpose |
|------|------|---------|
| `main.py` | Python | Platform orchestrator, lifecycle management |

### Configuration

| File | Type | Purpose |
|------|------|---------|
| `config/monitoring.json` | JSON | System configuration (collectors, eBPF, ML, API) |
| `requirements.txt` | Text | Python package dependencies |

### Ingestion Pipeline (Real-Time Streaming)

| File | Type | Purpose |
|------|------|---------|
| `ingestion/event_bus.py` | Python | Async pub-sub event router, backpressure handling |
| `ingestion/stream_processor.py` | Python | Event normalization, enrichment, time-series buffering |
| `ingestion/__init__.py` | Python | Package marker |

### User-Space Collectors (System Metrics)

| File | Type | Purpose |
|------|------|---------|
| `collectors/__init__.py` | Python | Package marker |
| `collectors/cpu.py` | Python | CPU utilization, per-core + aggregate |
| `collectors/memory.py` | Python | Virtual memory, swap, percent utilization |
| `collectors/disk.py` | Python | Disk I/O throughput, latency, per-device |
| `collectors/network.py` | Python | Network I/O, packets, errors, drops |
| `collectors/processes.py` | Python | Top-10 processes by CPU/memory |

### eBPF Kernel Instrumentation

#### Programs (C)

| File | Type | Purpose |
|------|------|---------|
| `ebpf/programs/__init__.py` | Python | Package marker |
| `ebpf/programs/syscall_trace.bpf.c` | C/eBPF | Syscall tracing (entry/exit, latency) |
| `ebpf/programs/exec_monitor.bpf.c` | C/eBPF | Process creation monitoring (placeholder) |
| `ebpf/programs/io_monitor.bpf.c` | C/eBPF | Block I/O monitoring (placeholder) |

#### Loaders (Python)

| File | Type | Purpose |
|------|------|---------|
| `ebpf/loaders/__init__.py` | Python | Package marker |
| `ebpf/loaders/syscall_loader.py` | Python | Compiles & attaches syscall tracer, reads ring buffer |
| `ebpf/loaders/exec_loader.py` | Python | Process creation loader (placeholder) |
| `ebpf/loaders/io_loader.py` | Python | Block I/O loader (placeholder) |

### Machine Learning (Anomaly Detection & Trends)

| File | Type | Purpose |
|------|------|---------|
| `ml/__init__.py` | Python | Package marker |
| `ml/anomaly_detection.py` | Python | Z-score + Isolation Forest anomaly detection |
| `ml/trend_prediction.py` | Python | Linear regression trend prediction |

### REST API (FastAPI Server)

| File | Type | Purpose |
|------|------|---------|
| `api/__init__.py` | Python | Package marker |
| `api/server.py` | Python | FastAPI endpoints for metrics, anomalies, trends, events |

### Documentation

| File | Type | Purpose |
|------|------|---------|
| `README.md` | Markdown | Complete documentation, features, installation, usage |
| `QUICKSTART.md` | Markdown | 5-minute setup guide, common commands |
| `ARCHITECTURE.md` | Markdown | Deep-dive architecture, design patterns, scalability |
| `FILE_MANIFEST.md` | Markdown | This file - complete file listing |

### Package Initialization

| File | Type | Purpose |
|------|------|---------|
| `__init__.py` | Python | Package marker + docstrings for all modules |

## Total File Count

- **Python files:** 18
- **eBPF C files:** 3
- **Configuration:** 1
- **Documentation:** 4
- **Package markers:** 6

**Total: 32 files**

## Quick File Reference

### To Run the Platform

```bash
1. Install: requirements.txt
2. Configure: config/monitoring.json
3. Execute: python3 main.py
```

### To Understand Architecture

```bash
1. Start: README.md (overview)
2. Setup: QUICKSTART.md (steps)
3. Deep-dive: ARCHITECTURE.md (design)
```

### Core Python Modules

```
Event Flow:
  collectors/* → event_bus.py → stream_processor.py

Data Processing:
  stream_processor.py → ml/anomaly_detection.py
  stream_processor.py → ml/trend_prediction.py

Output:
  api/server.py (REST endpoints)
```

### eBPF Kernel Programs

```
ebpf/programs/syscall_trace.bpf.c → ebpf/loaders/syscall_loader.py → event_bus.py
```

## File Dependencies

### Import Graph

```
main.py
├─ ingestion/event_bus.py
├─ ingestion/stream_processor.py
│  └─ ingestion/event_bus.py
├─ collectors/
│  ├─ cpu.py → event_bus.py
│  ├─ memory.py → event_bus.py
│  ├─ disk.py → event_bus.py
│  ├─ network.py → event_bus.py
│  └─ processes.py → event_bus.py
├─ ebpf/loaders/
│  ├─ syscall_loader.py → event_bus.py
│  ├─ exec_loader.py → event_bus.py
│  └─ io_loader.py → event_bus.py
├─ ml/
│  ├─ anomaly_detection.py → stream_processor.py
│  └─ trend_prediction.py → stream_processor.py
└─ api/server.py → stream_processor.py, event_bus.py
```

## External Dependencies

### System-Level (apt)

- bcc-tools
- libbcc-examples
- linux-headers-$(uname -r)
- build-essential
- clang, llvm
- python3.10, python3-pip

### Python Packages (pip)

See `requirements.txt` for complete list:
- psutil (system metrics)
- bcc (eBPF framework)
- fastapi, uvicorn (REST API)
- numpy (numerical computing)
- scikit-learn (ML algorithms)
- asyncio (built-in, async)

## File Sizes (Approximate)

| Category | Files | Size |
|----------|-------|------|
| Core Python | 13 | 200KB |
| eBPF Programs | 3 | 50KB |
| Documentation | 4 | 300KB |
| Configuration | 1 | 1KB |
| **Total** | **21** | **551KB** |

## Download/Installation Steps

### Option 1: Manual Download

1. Create directory structure:
```bash
mkdir -p system-monitoring/{config,collectors,ebpf/programs,ebpf/loaders,ingestion,ml,api}
cd system-monitoring
```

2. Download all `.py`, `.c`, `.json`, `.md`, `.txt` files to respective directories

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run:
```bash
sudo python3 main.py
```

### Option 2: Git Clone

```bash
git clone https://github.com/yourusername/system-monitoring-app.git
cd system-monitoring-app
pip install -r requirements.txt
sudo python3 main.py
```

## Verification Checklist

After download, verify all files are present:

### Essential Files (Must Have)

- [ ] main.py
- [ ] requirements.txt
- [ ] config/monitoring.json
- [ ] ingestion/event_bus.py
- [ ] ingestion/stream_processor.py
- [ ] collectors/cpu.py, memory.py, disk.py, network.py, processes.py
- [ ] ebpf/loaders/syscall_loader.py
- [ ] api/server.py
- [ ] ml/anomaly_detection.py
- [ ] ml/trend_prediction.py

### Documentation Files (Recommended)

- [ ] README.md
- [ ] QUICKSTART.md
- [ ] ARCHITECTURE.md

### eBPF Programs (For Full Features)

- [ ] ebpf/programs/syscall_trace.bpf.c

## Getting Started

1. **Read:** README.md (5 min)
2. **Setup:** QUICKSTART.md (10 min)
3. **Run:** `sudo python3 main.py`
4. **Test:** `curl http://localhost:8000/metrics/realtime`

## Support

For issues with specific files:
- **Installation:** QUICKSTART.md → "Troubleshooting"
- **Architecture:** ARCHITECTURE.md → "Components"
- **API:** README.md → "API Endpoints"

---

**File Manifest Version:** 1.0
**Last Updated:** 2024-12-18
**Kernel Requirement:** 5.15+
**Python Version:** 3.10+
