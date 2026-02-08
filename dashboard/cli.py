# dashboard/cli.py

"""
Terminal-based Rich dashboard for system monitoring.

Displays live metrics, anomaly scores, events, and system status in real-time.

Features:
- Live updating metrics with color-coded thresholds
- Anomaly score visualization (0-100 scale)
- Event stream with severity indicators
- System health overview
"""

import asyncio
import logging
from datetime import datetime
from collections import deque

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    from rich.align import Align
except ImportError as e:
    raise ImportError("Rich not installed. Install via: pip install rich") from e

logger = logging.getLogger(__name__)


class AnomalyScoreVisualizer:
    """Renders anomaly score as colored bar and percentage"""

    @staticmethod
    def get_color(score: float) -> str:
        if score < 20:
            return "green"
        elif score < 40:
            return "yellow"
        elif score < 60:
            return "bright_yellow"
        elif score < 80:
            return "red"
        else:
            return "bright_red"

    @staticmethod
    def get_label(score: float) -> str:
        if score < 20:
            return "🟢 Normal"
        elif score < 40:
            return "🟡 Low Risk"
        elif score < 60:
            return "🟠 Medium Risk"
        elif score < 80:
            return "🔴 High Risk"
        else:
            return "⛔ Critical"

    @staticmethod
    def render(score: float, width: int = 30) -> Text:
        filled = int(width * score / 100)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        color = AnomalyScoreVisualizer.get_color(score)
        return Text(f"{bar} {score:.1f}%", style=f"{color} bold")


class MetricDisplay:
    """Manages metric display with thresholds and formatting"""

    THRESHOLDS = {
        "cpu.total": {"warning": 70, "critical": 90},
        "cpu.": {"warning": 70, "critical": 90},
        "memory.virtual": {"warning": 75, "critical": 90},
        "disk": {"warning": 75, "critical": 90},
    }

    @staticmethod
    def get_metric_color(metric_key: str, value: float) -> str:
        for threshold_key, thresholds in MetricDisplay.THRESHOLDS.items():
            if threshold_key in metric_key:
                if value >= thresholds["critical"]:
                    return "bright_red"
                elif value >= thresholds["warning"]:
                    return "bright_yellow"
                return "green"
        return "white"

    @staticmethod
    def format_bytes(bytes_val: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_val < 1024:
                return f"{bytes_val:.2f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.2f}PB"

    @staticmethod
    def format_value(metric_key: str, value: float) -> str:
        if "cpu" in metric_key or "percent" in metric_key:
            return f"{value:.1f}%"
        elif "bytes" in metric_key or "rss" in metric_key or "vms" in metric_key:
            return MetricDisplay.format_bytes(value)
        elif "latency" in metric_key:
            return f"{value:.2f}µs" if value < 1000 else f"{value / 1000:.2f}ms"
        else:
            return f"{value:.2f}"


class RichDashboard:
    """Terminal UI dashboard using Rich library"""

    def __init__(self, stream_processor, ml_pipeline: dict):
        self.stream_processor = stream_processor
        self.ml_pipeline = ml_pipeline
        self.console = Console()
        self.metric_history = {}
        self.event_buffer = deque(maxlen=100)
        self.anomaly_scores = {}
        self.running = False
        self.selected_tab = 0

    # ---------- HEADER ----------

    def _create_header(self) -> Panel:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        processor_stats = self.stream_processor.get_processor_stats()

        header_text = Text()
        header_text.append("🖥️ System Monitoring Dashboard", style="bold bright_cyan")
        header_text.append(f" | {now}", style="dim white")
        header_text.append(
            f" | Events: {processor_stats['total_events_processed']}",
            style="dim yellow",
        )

        return Panel(header_text, style="bright_cyan", padding=(0, 1))

    # ---------- MAIN METRICS TABLE ----------

    def _create_metrics_table(self) -> Table:
        table = Table(
            title="📊 System Metrics",
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Metric", style="cyan", ratio=2, overflow="ellipsis")
        table.add_column("Value", style="white", ratio=1)
        table.add_column("Status", ratio=1)

        metrics = self.stream_processor.get_metric_keys()

        for metric_key in sorted(metrics)[:15]:
            stats = self.stream_processor.get_metric_stats(metric_key)
            if not stats or stats.get("count", 0) == 0:
                continue

            value = self.stream_processor.get_latest_value(metric_key)
            value = value if value is not None else 0.0

            color = MetricDisplay.get_metric_color(metric_key, value)
            formatted_value = MetricDisplay.format_value(metric_key, value)
            status = "✓" if color == "green" else "⚠" if color == "bright_yellow" else "✗"

            table.add_row(
                metric_key[:40],
                Text(formatted_value, style=color),
                Text(status, style=color),
            )

        return table

    # ---------- ANOMALY PANEL ----------

    def _create_anomaly_panel(self) -> Panel:
        from ingestion.event_bus import EventType
        import time

        anomaly_events = self.stream_processor.get_recent_events(limit=100)
        recent_anomalies = [
            e for e in anomaly_events if e.event_type == EventType.ANOMALY
        ]

        # Weighted score based on recency (recent anomalies count more)
        now = time.time()
        weights = []
        for e in recent_anomalies:
            age = now - e.timestamp  # seconds ago
            # Decay over 5 minutes: recent = 1.0, 5min old = 0.0
            weight = max(0.0, 1.0 - (age / 300.0))
            weights.append(weight)

        raw_score = sum(weights) * 25.0  # 25x multiplier for visibility
        anomaly_score = max(0, min(100, raw_score))

        content = Text()
        content.append("Overall Anomaly Score\n\n", style="bold cyan")
        content.append(AnomalyScoreVisualizer.render(anomaly_score, width=30))
        content.append(
            f"\n{AnomalyScoreVisualizer.get_label(anomaly_score)}\n\n",
            style="bold",
        )

        # Show recent count AND score components
        recent_count = len([w for w in weights if w > 0.1])  # count "fresh" ones
        content.append(f"Recent Anomalies: {recent_count} ", style="yellow")
        content.append(f"(Score: {anomaly_score:.1f}%)\n", style="bold yellow")

        if recent_anomalies:
            # FIXED: Access data fields correctly
            newest = recent_anomalies[-1]  # most recent
            metric_key = getattr(newest.data, 'metric_key', 'unknown') or getattr(newest, 'metric_key', 'unknown')
            value = getattr(newest.data, 'value', 0.0) or getattr(newest, 'value', 0.0)
            content.append(
                f"Latest: {metric_key} ({value:.1f}) ",
                style="bright_yellow",
            )
        else:
            content.append("No anomalies detected ✓", style="green")

        return Panel(
            content,
            title="🚨 Anomaly Status",
            style=AnomalyScoreVisualizer.get_color(anomaly_score),
            padding=(1, 1),
        )




    # ---------- EVENTS TABLE ----------

    def _create_events_table(self) -> Table:
        table = Table(
            title="📋 Recent Events",
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Time", style="dim white", width=10, no_wrap=True)
        table.add_column("Type", style="cyan", width=15, no_wrap=True)
        table.add_column("Details", overflow="fold")

        events = self.stream_processor.get_recent_events(limit=15)

        for event in reversed(events[-15:]):
            timestamp = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
            event_type = (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            )
            details = str(event.data)[:80]
            table.add_row(timestamp, event_type, details)

        return table

    # ---------- SYSTEM HEALTH PANEL ----------

    def _create_system_health(self) -> Panel:
        processor_stats = self.stream_processor.get_processor_stats()
        event_bus_stats = self.stream_processor.event_bus.get_metrics()

        content = Text()
        content.append("Event Processing\n", style="bold cyan")
        content.append(
            f"Total Events: {processor_stats.get('total_events_processed', 0)}\n"
        )
        content.append(
            f"Active Metrics: {processor_stats.get('active_metrics', 0)}\n"
        )
        content.append(f"Dropped Events: {event_bus_stats.get('dropped_events', 0)}\n")
        content.append(f"Subscribers: {event_bus_stats.get('subscribers', 0)}\n")

        return Panel(content, title="💊 System Health", padding=(1, 1))

    # ---------- FOOTER ----------

    def _create_footer(self) -> Panel:
        """Status/help bar in the footer."""
        footer_text = Text()
        footer_text.append("q", style="bold yellow")
        footer_text.append(" to quit  ", style="dim white")
        footer_text.append("CTRL+C", style="bold yellow")
        footer_text.append(" to exit dashboard", style="dim white")

        rendered = Align.center(footer_text, vertical="middle")
        # NOTE: no box=None here – use default box to avoid NoneType error
        return Panel(
            rendered,
            padding=(0, 1),
            style=Style(color="white", bgcolor="grey15"),
        )

    # ---------- LAYOUT ----------

    def _create_layout(self) -> Layout:
        layout = Layout(name="root")

        # Top-level: header, body, footer
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Body: main (left) + side (right)
        layout["body"].split_row(
            Layout(name="main"),
            Layout(name="side", size=40),
        )

        # Main area: metrics (top) + events (bottom)
        layout["main"].split_column(
            Layout(name="metrics"),
            Layout(name="events", size=10),
        )

        # Populate regions
        layout["header"].update(self._create_header())
        layout["metrics"].update(self._create_metrics_table())
        layout["events"].update(self._create_events_table())
        layout["side"].update(self._create_anomaly_panel())
        layout["footer"].update(self._create_footer())

        return layout

    # ---------- RUN LOOP ----------

    async def start(self):
        logger.info("Starting Rich CLI Dashboard...")
        self.running = True

        try:
            with Live(self._create_layout(), refresh_per_second=1, screen=True) as live:
                while self.running:
                    live.update(self._create_layout())
                    await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Dashboard interrupted")
        finally:
            self.running = False
            logger.info("Dashboard stopped")

    async def stop(self):
        self.running = False