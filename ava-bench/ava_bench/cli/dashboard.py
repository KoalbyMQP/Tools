# ava_bench/cli/dashboard.py
# Enhanced dashboard with integrated real-time plotting support

from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.console import Group
from typing import Dict, List, Tuple, Optional, Any
from collections import deque
import time


def create_usage_bar(percent, width=20): 
    return "█" * int(width * percent / 100) + "░" * (width - int(width * percent / 100))


class TimeseriesBuffer:
    """Rolling buffer for time-series data. Simple deque with timestamps."""
    
    def __init__(self, max_samples: int = 200):
        self.max_samples = max_samples
        self.samples = deque(maxlen=max_samples)  # (timestamp, value) pairs
    
    def add_sample(self, timestamp: float, value: Any) -> None:
        self.samples.append((timestamp, value))
    
    def get_recent(self, window_seconds: float = 30.0) -> List[Tuple[float, Any]]:
        if not self.samples:
            return []
        latest_time = self.samples[-1][0]
        cutoff_time = latest_time - window_seconds
        return [(t, v) for t, v in self.samples if t >= cutoff_time]
    
    def get_latest(self) -> Optional[Tuple[float, Any]]:
        return self.samples[-1] if self.samples else None
    
    def clear(self) -> None:
        self.samples.clear()


class EventDetector:
    """Detect performance events from streaming data. Explicit thresholds."""
    
    def __init__(self):
        self.inference_times = deque(maxlen=50)
        self.memory_values = deque(maxlen=50)
        self.events = deque(maxlen=100)
        
        # Explicit thresholds - no magic
        self.slow_inference_multiplier = 2.0
        self.memory_spike_threshold_mb = 5.0
        self.min_samples_for_detection = 10
    
    def add_inference_time(self, timestamp: float, inference_ms: float) -> Optional[Dict]:
        self.inference_times.append((timestamp, inference_ms))
        
        if len(self.inference_times) < self.min_samples_for_detection:
            return None
        
        # Calculate median
        recent_times = [t for _, t in self.inference_times]
        recent_times.sort()
        median_time = recent_times[len(recent_times) // 2]
        
        # Check if current inference is slow
        if inference_ms > median_time * self.slow_inference_multiplier:
            event = {
                'type': 'slow_inference',
                'timestamp': timestamp,
                'inference_ms': inference_ms,
                'median_ms': median_time,
                'slowdown_factor': inference_ms / median_time,
                'severity': 'warning' if inference_ms < median_time * 3 else 'critical'
            }
            self.events.append(event)
            return event
        
        return None
    
    def add_memory_value(self, timestamp: float, memory_mb: float) -> Optional[Dict]:
        if self.memory_values:
            last_timestamp, last_memory = self.memory_values[-1]
            memory_delta = memory_mb - last_memory
            time_delta = timestamp - last_timestamp
            
            if abs(memory_delta) > self.memory_spike_threshold_mb and time_delta < 1.0:
                event = {
                    'type': 'memory_spike',
                    'timestamp': timestamp,
                    'current_mb': memory_mb,
                    'previous_mb': last_memory,
                    'delta_mb': memory_delta,
                    'spike_direction': 'increase' if memory_delta > 0 else 'decrease',
                    'severity': 'warning' if abs(memory_delta) < 10 else 'critical'
                }
                self.events.append(event)
                return event
        
        self.memory_values.append((timestamp, memory_mb))
        return None
    
    def get_recent_events(self, window_seconds: float = 30.0) -> List[Dict]:
        if not self.events:
            return []
        latest_time = self.events[-1]['timestamp']
        cutoff_time = latest_time - window_seconds
        return [e for e in self.events if e['timestamp'] >= cutoff_time]


class PlotRenderer:
    """ASCII plot renderer for terminal display. Simple and explicit."""
    
    def create_ascii_plot(self, x_data: List[float], y_data: List[float], 
                         width: int = 50, height: int = 8, title: str = "") -> Panel:
        """Create ASCII plot for terminal display."""
        if not x_data or not y_data or len(x_data) != len(y_data):
            return Panel(Text("No data", style="dim"), title=title)
        
        if len(y_data) < 2:
            return Panel(Text("Insufficient data", style="dim"), title=title)
        
        # Normalize data
        y_min, y_max = min(y_data), max(y_data)
        if y_max == y_min:
            y_max = y_min + 1
        
        # Create ASCII plot
        lines = []
        for row in range(height):
            line = ""
            y_threshold = y_min + (y_max - y_min) * (height - row - 1) / (height - 1)
            
            for col in range(width):
                if col < len(y_data):
                    x_index = int(col * len(y_data) / width)
                    y_value = y_data[x_index]
                    
                    if abs(y_value - y_threshold) < (y_max - y_min) / height:
                        line += "█"
                    elif y_value > y_threshold:
                        line += "▀"
                    else:
                        line += " "
                else:
                    line += " "
            lines.append(line)
        
        # Add value labels
        plot_text = "\n".join(lines)
        if y_data:
            latest_value = y_data[-1]
            plot_text += f"\nCurrent: {latest_value:.1f}"
            plot_text += f" | Range: {y_min:.1f}-{y_max:.1f}"
        
        return Panel(Text(plot_text, style="bright_blue"), title=title, border_style="blue")


class InferenceTimelinePlot:
    """Real-time inference timing plot."""
    
    def __init__(self, renderer: PlotRenderer):
        self.renderer = renderer
        self.max_samples = 100
    
    def create_plot(self, inference_data: List[Tuple[float, float]]) -> Panel:
        if not inference_data:
            return Panel(Text("Waiting for inference data...", style="dim"), title="Inference Timeline")
        
        timestamps = [t for t, _ in inference_data[-self.max_samples:]]
        inference_times = [ms for _, ms in inference_data[-self.max_samples:]]
        
        return self.renderer.create_ascii_plot(
            timestamps, inference_times, width=40, height=6, title="Inference Timeline (ms)"
        )


class MemoryTimelinePlot:
    """Real-time memory usage plot."""
    
    def __init__(self, renderer: PlotRenderer):
        self.renderer = renderer
        self.max_samples = 100
    
    def create_plot(self, memory_data: List[Tuple[float, float]]) -> Panel:
        if not memory_data:
            return Panel(Text("Waiting for memory data...", style="dim"), title="Memory Usage")
        
        timestamps = [t for t, _ in memory_data[-self.max_samples:]]
        memory_values = [mb for _, mb in memory_data[-self.max_samples:]]
        
        return self.renderer.create_ascii_plot(
            timestamps, memory_values, width=40, height=6, title="Memory Usage (MB)"
        )


class SystemCorrelationPlot:
    """System metrics correlation display."""
    
    def create_plot(self, correlation_data: Dict[str, List[Tuple[float, float]]]) -> Panel:
        cpu_data = correlation_data.get('cpu', [])
        memory_data = correlation_data.get('memory', [])
        
        if not cpu_data or not memory_data:
            return Panel(Text("Waiting for correlation data...", style="dim"), title="System Correlation")
        
        latest_cpu = cpu_data[-1][1] if cpu_data else 0
        latest_memory = memory_data[-1][1] if memory_data else 0
        
        correlation_text = f"CPU: {latest_cpu:.1f}%\n"
        correlation_text += f"Memory: {latest_memory:.1f}MB\n"
        
        # Simple correlation indicator
        if latest_cpu > 70 and latest_memory > 50:
            correlation_text += "Status: High Load"
            style = "red"
        elif latest_cpu > 50 or latest_memory > 40:
            correlation_text += "Status: Medium Load"
            style = "yellow"
        else:
            correlation_text += "Status: Low Load"
            style = "green"
        
        return Panel(Text(correlation_text, style=style), title="System Load", border_style=style)


class EventTimelinePlot:
    """Event timeline display."""
    
    def create_plot(self, events: List[Dict]) -> Panel:
        if not events:
            return Panel(Text("No recent events", style="dim green"), title="Event Timeline")
        
        recent_events = events[-5:]  # Show last 5 events
        event_text = ""
        
        for event in recent_events:
            timestamp = event.get('timestamp', 0)
            event_type = event.get('type', 'unknown')
            severity = event.get('severity', 'info')
            
            # Color code by severity
            if severity == 'critical':
                style = "red bold"
            elif severity == 'warning':
                style = "yellow"
            else:
                style = "white"
            
            # Format event
            if event_type == 'slow_inference':
                factor = event.get('slowdown_factor', 1)
                event_text += f"{timestamp:.1f}s: Slow inference ({factor:.1f}x)\n"
            elif event_type == 'memory_spike':
                delta = event.get('delta_mb', 0)
                direction = event.get('spike_direction', 'unknown')
                event_text += f"{timestamp:.1f}s: Memory {direction} {abs(delta):.1f}MB\n"
            else:
                event_text += f"{timestamp:.1f}s: {event_type}\n"
        
        if not event_text:
            event_text = "No events"
        
        return Panel(Text(event_text.strip(), style="bright_white"), 
                    title=f"Events ({len(recent_events)})", border_style="cyan")


# ===== ENHANCED DASHBOARD INTEGRATION =====

class DashboardTimeseriesExtension:
    """Extension to add timeseries support to existing dashboard."""
    
    def __init__(self, stream_manager):
        self.stream_manager = stream_manager
        self.timeseries_buffers: Dict[str, TimeseriesBuffer] = {}
        self.event_detector = EventDetector()
        
        # Plot metrics we track
        self.plot_metrics = {
            'process.memory.rss_mb', 'memory_profiler.rss_mb', 
            'cpu.usage_percent', 'memory.percent', 'thermal.cpu_temp'
        }
        
        # Initialize buffers
        for metric in self.plot_metrics:
            self.timeseries_buffers[metric] = TimeseriesBuffer(max_samples=200)
    
    def update_timeseries_buffers(self) -> None:
        """Update timeseries buffers with latest data."""
        current_data = self.stream_manager.get_all_current_data()
        
        for metric_type, sample in current_data.items():
            if sample is None:
                continue
            
            # Add to buffer
            if metric_type in self.timeseries_buffers:
                self.timeseries_buffers[metric_type].add_sample(sample.timestamp, sample.value)
            
            # Feed to event detector
            if metric_type in ['process.memory.rss_mb', 'memory_profiler.rss_mb']:
                self.event_detector.add_memory_value(sample.timestamp, sample.value)
    
    def add_inference_timing(self, inference_ms: float) -> Optional[Dict]:
        """Add inference timing and detect events."""
        current_time = self.stream_manager.time_manager.get_timestamp()
        return self.event_detector.add_inference_time(current_time, inference_ms)
    
    def get_plot_data(self, metric_type: str, window_seconds: float = 30.0) -> List[Tuple[float, Any]]:
        """Get time-series data for plotting."""
        if metric_type not in self.timeseries_buffers:
            return []
        return self.timeseries_buffers[metric_type].get_recent(window_seconds)
    
    def get_inference_timeline(self) -> List[Tuple[float, float]]:
        return list(self.event_detector.inference_times)
    
    def get_memory_timeline(self, window_seconds: float = 30.0) -> List[Tuple[float, float]]:
        # Try memory profiler first, fall back to process memory
        memory_data = self.get_plot_data('memory_profiler.rss_mb', window_seconds)
        if not memory_data:
            memory_data = self.get_plot_data('process.memory.rss_mb', window_seconds)
        return memory_data
    
    def get_cpu_timeline(self, window_seconds: float = 30.0) -> List[Tuple[float, float]]:
        return self.get_plot_data('cpu.usage_percent', window_seconds)
    
    def get_events_timeline(self, window_seconds: float = 30.0) -> List[Dict]:
        return self.event_detector.get_recent_events(window_seconds)
    
    def get_system_correlation_data(self, window_seconds: float = 30.0) -> Dict:
        return {
            'cpu': self.get_cpu_timeline(window_seconds),
            'memory': self.get_memory_timeline(window_seconds)
        }


class DashboardLayout:
    """Enhanced dashboard that combines existing gauges with optional real-time plots."""
    
    def __init__(self, console, enable_plots: bool = False):
        self.console = console
        self.enable_plots = enable_plots
        
        # Store dashboard data (existing functionality)
        self.header_text = "AVA-Bench Dashboard"
        self.cpu_data = {}
        self.memory_data = {}  
        self.thermal_data = {}
        self.progress_data = {}
        self.results_data = {}
        self.footer_text = "Ready"
        
        # Plot components (new functionality)
        if enable_plots:
            self.plot_renderer = PlotRenderer()
            self.inference_plot = InferenceTimelinePlot(self.plot_renderer)
            self.memory_plot = MemoryTimelinePlot(self.plot_renderer)
            self.correlation_plot = SystemCorrelationPlot()
            self.event_plot = EventTimelinePlot()
            self.timeseries_extension = None
        
        self.last_event_notification = ""
    
    def set_streaming_monitor(self, monitor) -> None:
        """Set streaming monitor for plot data (only if plots enabled)."""
        if self.enable_plots and hasattr(monitor, 'stream_manager'):
            self.timeseries_extension = DashboardTimeseriesExtension(monitor.stream_manager)
    
    def update_header(self, title="AVA-Bench Dashboard"):
        """Update header."""
        self.header_text = title
    
    def update_system_tiles(self, stats):
        """Update system monitoring data (existing functionality)."""
        cpu = stats.get('cpu', {})
        memory = stats.get('memory', {})
        temps = stats.get('thermal', {})
        
        self.cpu_data = {
            'usage': cpu.get('usage_percent', 0) or 0,
            'freq': cpu.get('frequency_ghz', 0) or 0,
            'load': cpu.get('load_1min', 0) or 0,
            'cores': cpu.get('core_count', 4) or 4
        }
        
        self.memory_data = {
            'used': memory.get('used_gb', 0) or 0,
            'total': memory.get('total_gb', 8) or 8,
            'percent': memory.get('percent', 0) or 0,
            'swap': memory.get('swap_used_gb', 0) or 0
        }
        
        cpu_temp = temps.get('cpu_temp', 0) or 0
        is_throttled = temps.get('is_throttled', False)
        
        self.thermal_data = {
            'temp': cpu_temp,
            'throttled': is_throttled,
            'color': "green" if cpu_temp < 60 else "yellow" if cpu_temp < 75 else "red",
            'status': "Cool" if cpu_temp < 60 else "Warm" if cpu_temp < 75 else "Hot"
        }
        
        # Update timeseries if plots enabled
        if self.enable_plots and self.timeseries_extension:
            self.timeseries_extension.update_timeseries_buffers()
    
    def update_progress(self, current_stage, percent=0, past_stages=None, future_stages=None):
        """Update progress data."""
        self.progress_data = {
            'current': current_stage,
            'percent': percent,
            'past': past_stages or [],
            'future': future_stages or []
        }
    
    def update_results(self, results=None):
        """Update results data."""
        if not results:
            self.results_data = {'status': 'waiting'}
            return
            
        duration = results.get('duration_seconds', 0)
        throughput = results.get('ops_per_second', 0)
        
        if duration < 5 and throughput > 1000: 
            status, color = "Excellent", "green"
        elif duration < 10: 
            status, color = "Good", "bright_green"  
        elif duration < 30: 
            status, color = "Fair", "yellow"
        else: 
            status, color = "Poor", "red"
        
        self.results_data = {
            'duration': duration,
            'throughput': throughput,
            'status': status,
            'color': color
        }
    
    def update_footer(self, message="Ready"):
        """Update footer message."""
        self.footer_text = message
    
    def add_inference_timing(self, inference_ms: float) -> None:
        """Add inference timing for real-time event detection."""
        if self.enable_plots and self.timeseries_extension:
            event = self.timeseries_extension.add_inference_timing(inference_ms)
            if event:
                event_type = event.get('type', 'unknown')
                if event_type == 'slow_inference':
                    factor = event.get('slowdown_factor', 1)
                    self.last_event_notification = f"⚠️  Slow inference: {factor:.1f}x slower"
                elif event_type == 'memory_spike':
                    delta = event.get('delta_mb', 0)
                    self.last_event_notification = f"📈 Memory spike: {abs(delta):.1f}MB"
    
    def render(self):
        """Render dashboard (existing functionality + optional plots)."""
        components = []
        
        # Header
        header = Panel(Text(self.header_text, style="bold cyan", justify="center"), border_style="cyan")
        components.append(header)
        
        # System tiles (always present)
        system_row = self._render_system_tiles()
        components.append(system_row)
        
        # Plots section (optional)
        if self.enable_plots and self.timeseries_extension:
            plots_section = self._render_plots_section()
            if plots_section:
                components.append(plots_section)
        
        # Progress section
        progress_panel = self._render_progress_panel()
        components.append(progress_panel)
        
        # Results section
        results_panel = self._render_results_panel()
        components.append(results_panel)
        
        # Footer (with event notifications)
        footer_text = self.footer_text
        if self.last_event_notification:
            footer_text = self.last_event_notification
            self.last_event_notification = ""  # Clear after showing
        
        footer = Panel(Text(footer_text, style="bright_white", justify="center"), border_style="white")
        components.append(footer)
        
        return Group(*components)
    
    def _render_system_tiles(self):
        """Render system monitoring tiles (existing functionality)."""
        # CPU tile
        cpu_text = Text()
        cpu_text.append(f"CPU: {create_usage_bar(self.cpu_data.get('usage', 0))}\n", style="bright_blue")
        cpu_text.append(f"{self.cpu_data.get('usage', 0):.0f}%\n", style="bright_blue")
        cpu_text.append(f"Load: {self.cpu_data.get('load', 0):.1f}/{self.cpu_data.get('cores', 4)}\n", style="white")
        cpu_text.append(f"Freq: {self.cpu_data.get('freq', 0):.1f}GHz", style="dim white")
        cpu_tile = Panel(cpu_text, title="System", border_style="blue", width=25)
        
        # Memory tile
        memory_text = Text()
        memory_text.append(f"RAM: {create_usage_bar(self.memory_data.get('percent', 0))}\n", style="bright_green")
        memory_text.append(f"{self.memory_data.get('percent', 0):.0f}%\n", style="bright_green")
        memory_text.append(f"{self.memory_data.get('used', 0):.1f}GB / {self.memory_data.get('total', 8):.1f}GB\n", style="white")
        memory_text.append(f"Swap: {self.memory_data.get('swap', 0):.1f}GB", style="dim white")
        memory_tile = Panel(memory_text, title="Memory", border_style="green", width=25)
        
        # Thermal tile
        thermal_color = self.thermal_data.get('color', 'white')
        thermal_text = Text()
        thermal_text.append(f"CPU: {self.thermal_data.get('temp', 0):.0f}C\n", style=thermal_color)
        thermal_text.append(f"Status: {self.thermal_data.get('status', 'Normal')}\n", style=thermal_color)
        thermal_text.append("Throttled\n" if self.thermal_data.get('throttled') else "Normal\n", 
                          style="red" if self.thermal_data.get('throttled') else "white")
        thermal_text.append("Stable", style="dim white")
        thermal_tile = Panel(thermal_text, title="Thermal", border_style=thermal_color, width=25)
        
        return Columns([cpu_tile, memory_tile, thermal_tile], equal=True)
    
    def _render_plots_section(self):
        """Render real-time plots section (new functionality)."""
        try:
            # Get data for plots
            inference_data = self.timeseries_extension.get_inference_timeline()
            memory_data = self.timeseries_extension.get_memory_timeline(window_seconds=30)
            events = self.timeseries_extension.get_events_timeline(window_seconds=30)
            correlation_data = self.timeseries_extension.get_system_correlation_data(window_seconds=30)
            
            # Create plots
            inference_plot = self.inference_plot.create_plot(inference_data)
            memory_plot = self.memory_plot.create_plot(memory_data)
            correlation_plot = self.correlation_plot.create_plot(correlation_data)
            event_plot = self.event_plot.create_plot(events)
            
            # Arrange in 2x2 grid
            top_row = Columns([inference_plot, memory_plot], equal=True)
            bottom_row = Columns([correlation_plot, event_plot], equal=True)
            
            return Group(top_row, bottom_row)
            
        except Exception as e:
            # Graceful degradation
            return Panel(Text(f"Plot error: {str(e)}", style="red dim"), 
                        title="Plot Error", border_style="red")
    
    def _render_progress_panel(self):
        """Render progress panel (existing functionality)."""
        progress_text = Text()
        if self.progress_data.get('past'):
            past_str = " -> ".join(self.progress_data['past'][-2:])
            progress_text.append(f"Past: {past_str}\n", style="dim white")
        
        current = self.progress_data.get('current', 'waiting')
        percent = self.progress_data.get('percent', 0)
        progress_bar = create_usage_bar(percent, 30)
        progress_text.append(f"Current: {current}\n", style="bold bright_cyan")
        progress_text.append(f"{progress_bar} {percent:.0f}%\n", style="bright_cyan")
        
        if self.progress_data.get('future'):
            future_str = " -> ".join(self.progress_data['future'][:2])
            progress_text.append(f"Next: {future_str}", style="dim cyan")
        
        return Panel(progress_text, title="Progress", border_style="cyan")
    
    def _render_results_panel(self):
        """Render results panel (existing functionality)."""
        if self.results_data.get('status') == 'waiting':
            results_text = Text("Waiting for results...", style="dim white")
            return Panel(results_text, title="Results", border_style="white")
        else:
            results_text = Text()
            results_text.append(f"Duration: {self.results_data.get('duration', 0):.3f}s  |  ", style="white")
            results_text.append(f"Throughput: {self.results_data.get('throughput', 0):,.0f} ops/sec  |  ", style="white")
            results_text.append(f"Status: {self.results_data.get('status', 'Unknown')}", 
                              style=self.results_data.get('color', 'white'))
            return Panel(results_text, title="Live Results", 
                        border_style=self.results_data.get('color', 'white'))


# ===== INTEGRATION HELPERS =====

def create_enhanced_dashboard(console, enable_plots: bool = True):
    """Create dashboard with optional real-time plots."""
    return DashboardLayout(console, enable_plots=enable_plots)


def add_timeseries_support_to_monitor(streaming_monitor):
    """Add timeseries plotting support to existing StreamingMonitor."""
    # This function would be called from the commands to enhance existing monitors
    streaming_monitor._timeseries_enabled = True
    return streaming_monitor