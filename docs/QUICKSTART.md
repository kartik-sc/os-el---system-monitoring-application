# QUICKSTART.md - Getting Started Guide

## 5-Minute Setup

### Step 1: Prerequisites Check

```bash
# Check Ubuntu version
lsb_release -a
# Should be Ubuntu 22.04 or later

# Check kernel version
uname -r
# Should be 5.15 or later

# Check eBPF support
cat /boot/config-$(uname -r) | grep CONFIG_BPF
# Output should show: CONFIG_BPF=y, CONFIG_BPF_SYSCALL=y
```

### Step 2: Install Dependencies

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install BCC and build tools
sudo apt-get install -y \
    bcc-tools \
    libbcc-examples \
    linux-headers-$(uname -r) \
    build-essential \
    clang \
    llvm \
    python3.10 \
    python3-pip \
    python3.10-venv

# Verify BCC installation
dpkg -l | grep bcc
```

### Step 3: Clone/Download Project

```bash
# Create workspace
mkdir -p ~/projects
cd ~/projects

# Download or git clone
git clone https://github.com/yourusername/system-monitoring-app.git
cd system-monitoring-app

# Or create structure manually:
# mkdir -p collectors ebpf/programs ebpf/loaders ingestion ml api config
```

### Step 4: Setup Python Environment

```bash
# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements.txt

# Verify
python3 -c "from bcc import BPF; print('✓ BCC available')"
python3 -c "import psutil; print('✓ psutil available')"
python3 -c "from fastapi import FastAPI; print('✓ FastAPI available')"
```

### Step 5: Run the Platform

```bash
# IMPORTANT: Must run as root for eBPF attachment
sudo python3 main.py

# Expected output:
# [2024-12-18 22:00:00] INFO [main] ============================================================
# [2024-12-18 22:00:00] INFO [main] Initializing System Monitoring Platform...
# [2024-12-18 22:00:00] INFO [main] ============================================================
# [2024-12-18 22:00:00] INFO [ingestion.event_bus] EventBus initialized with buffer_size=10000
# [2024-12-18 22:00:00] INFO [main] ✓ Event Bus initialized
# [2024-12-18 22:00:01] INFO [main] ✓ Stream Processor initialized
# [2024-12-18 22:00:01] INFO [main] ✓ Loaded 1 eBPF program (syscall tracer)
# [2024-12-18 22:00:01] INFO [main] ✓ Initialized 5 user-space collectors
# [2024-12-18 22:00:01] INFO [main] ✓ ML Pipelines initialized
# [2024-12-18 22:00:01] INFO [main] ✓ API Server configured (0.0.0.0:8000)
# [2024-12-18 22:00:01] INFO [main] ============================================================
# [2024-12-18 22:00:01] INFO [main] ✅ Platform initialization complete!
```

### Step 6: Test the API (New Terminal)

```bash
# In a new terminal
curl http://localhost:8000

# Should return:
# {
#   "service": "System Monitoring Platform",
#   "version": "1.0.0",
#   "endpoints": [...]
# }

# Get real-time metrics
curl http://localhost:8000/metrics/realtime | python3 -m json.tool

# Get anomalies
curl http://localhost:8000/anomalies | python3 -m json.tool

# Get trends
curl http://localhost:8000/trends | python3 -m json.tool
```

## File Organization

After setup, your directory should look like:

```
system-monitoring-app/
├── venv/                           # Python virtual environment
├── main.py                         # ✓ Start here
├── README.md                       # Documentation
├── QUICKSTART.md                   # This file
├── requirements.txt                # ✓ Dependencies
├── config/
│   └── monitoring.json             # Configuration
├── collectors/
│   ├── __init__.py
│   ├── cpu.py
│   ├── memory.py
│   ├── disk.py
│   ├── network.py
│   └── processes.py
├── ebpf/
│   ├── programs/
│   │   ├── __init__.py
│   │   ├── syscall_trace.bpf.c      # implemented
│   │   └── (templates)
│   │       # exec_monitor.bpf.c and io_monitor.bpf.c are referenced
│       # in the docs as extension templates and are not supplied
│       # as compiled kernel programs in this repository.
│   └── loaders/
│       ├── __init__.py
│       ├── syscall_loader.py
│       ├── exec_loader.py
│       └── io_loader.py
├── ingestion/
│   ├── __init__.py
│   ├── event_bus.py
│   └── stream_processor.py
├── ml/
│   ├── __init__.py
│   ├── anomaly_detection.py
│   └── trend_prediction.py
└── api/
    ├── __init__.py
    └── server.py
```

## Common Commands

### Start Monitoring

```bash
# Terminal 1: Start the platform (requires sudo)
sudo python3 main.py

# Terminal 2: Test API
curl http://localhost:8000/stats | jq .

# Terminal 3: Watch metrics in real-time
watch -n 1 'curl -s http://localhost:8000/metrics/realtime | python3 -m json.tool | head -30'
```

### Stop the Platform

```bash
# Press Ctrl+C in the terminal running main.py
# Or from another terminal:
sudo pkill -f "python3 main.py"
```

### Debug Issues

```bash
# Check logs
tail -f system_monitor.log

# Verify eBPF programs loaded
sudo bpftool prog list

# Check API is running
curl -v http://localhost:8000/

# Monitor system resources
watch -n 0.5 'ps aux | grep python3'
```

## API Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/metrics/realtime` | GET | Current metrics snapshot |
| `/metrics/history` | GET | Historical metric data |
| `/anomalies` | GET | Recent anomalies detected |
| `/trends` | GET | Current metric trends |
| `/events` | GET | System events (kernel + ML) |
| `/stats` | GET | Platform statistics |

## Example API Calls

### Get Current CPU Utilization

```bash
curl "http://localhost:8000/metrics/history?metric_key=cpu.total&seconds=60" | python3 -m json.tool
```

### Get Top 10 Anomalies

```bash
curl "http://localhost:8000/anomalies?limit=10" | python3 -m json.tool
```

### Get Process Metrics

```bash
curl "http://localhost:8000/events?event_type=process_metric&limit=5" | python3 -m json.tool
```

### Get Syscall Events

```bash
curl "http://localhost:8000/events?event_type=syscall&limit=10" | python3 -m json.tool
```

## Performance Tips

### Reduce Overhead

1. **Increase collection intervals** in `config/monitoring.json`:
   ```json
   "collectors": {
     "cpu_interval": 2.0,      // Was 1.0
     "memory_interval": 2.0,   // Was 1.0
     "disk_interval": 5.0,     // Was 2.0
     "network_interval": 5.0   // Was 2.0
   }
   ```

2. **Disable unnecessary eBPF programs**:
   ```json
   "ebpf": {
     "enable_syscall_trace": true,
     "enable_exec_monitor": false,   // Disabled
     "enable_io_monitor": false       // Disabled
   }
   ```

3. **Reduce ML frequency**: Edit `ml/anomaly_detection.py`:
   ```python
   await asyncio.sleep(10.0)  # Check every 10s instead of 5s
   ```

### Monitor System Load

```bash
# Check platform CPU usage
ps aux | grep "python3 main.py"

# Check total events processed
curl -s http://localhost:8000/stats | jq .processor.total_events_processed

# Check dropped events (indicates backpressure)
curl -s http://localhost:8000/stats | jq .event_bus.dropped_events
```

## Troubleshooting

### Error: "Permission denied" or "Operation not permitted"

```bash
# Solution: Run with sudo
sudo python3 main.py

# Or use sudo permanently (not recommended for security)
sudo -E python3 main.py
```

### Error: "BCC is not available"

```bash
# Solution: Install BCC
sudo apt-get install bcc-tools linux-headers-$(uname -r)

# Verify in venv
source venv/bin/activate
pip install bcc
```

### Error: "Ring buffer not available"

```bash
# Solution: Kernel doesn't support eBPF ring buffer (need 5.8+)
uname -r

# Update kernel if needed
sudo apt-get install linux-image-generic-hwe-22.04
```

### High CPU Usage from Collectors

```bash
# Solution: Increase intervals in config/monitoring.json
# or reduce metrics collection frequency
```

### API Port 8000 Already in Use

```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill it or use different port in config
"api": {
  "port": 8080  // Changed from 8000
}
```

## Next Steps

1. **Read full documentation**: `README.md`
2. **Explore API endpoints** at http://localhost:8000/docs (auto-generated by FastAPI)
3. **Configure for your needs**: Edit `config/monitoring.json`
4. **Add custom collectors**: Create new files in `collectors/`
5. **Integrate with dashboards**: Use REST API with Grafana, Prometheus, etc.

## Support

For issues or questions:
- Check logs: `tail -f system_monitor.log`
- Review architecture: See `README.md` Architecture section
- Test eBPF programs: `sudo bpftool prog list`
- Check kernel capabilities: `cat /boot/config-$(uname -r) | grep BPF`

---

**You're now ready to monitor your system at both kernel and user-space levels!** 🚀
