# ava_bench/monitoring/timeseries.py
# Extension to StreamingMonitor for real-time plotting data

from typing import Dict, List, Tuple, Optional, Any
from collections import deque
import time


class TimeseriesBuffer:
    """Rolling buffer for time-series data. No magic, just a deque with timestamps."""
    
    def __init__(self, max_samples: int = 200):
        self.max_samples = max_samples
        self.samples = deque(maxlen=max_samples)  # (timestamp, value) pairs
        self.metric_type = None
    
    def add_sample(self, timestamp: float, value: Any) -> None:
        """Add a timestamped sample."""
        self.samples.append((timestamp, value))
    
    def get_recent(self, window_seconds: float = 30.0) -> List[Tuple[float, Any]]:
        """Get samples from the last window_seconds."""
        if not self.samples:
            return []
        
        latest_time = self.samples[-1][0]
        cutoff_time = latest_time - window_seconds
        
        return [(t, v) for t, v in self.samples if t >= cutoff_time]
    
    def get_all(self) -> List[Tuple[float, Any]]:
        """Get all samples in buffer."""
        return list(self.samples)
    
    def get_latest(self) -> Optional[Tuple[float, Any]]:
        """Get most recent sample."""
        return self.samples[-1] if self.samples else None
    
    def clear(self) -> None:
        """Clear all samples."""
        self.samples.clear()


class EventDetector:
    """Detect performance events from streaming data. Explicit thresholds, no magic."""
    
    def __init__(self):
        self.inference_times = deque(maxlen=50)  # Keep recent inference times
        self.memory_values = deque(maxlen=50)    # Keep recent memory values
        self.events = deque(maxlen=100)          # Keep recent events
        
        # Explicit thresholds
        self.slow_inference_multiplier = 2.0    # 2x median = slow
        self.memory_spike_threshold_mb = 5.0    # 5MB change = spike
        self.min_samples_for_detection = 10     # Need baseline
    
    def add_inference_time(self, timestamp: float, inference_ms: float) -> Optional[Dict]:
        """Add inference time and check for slow inference events."""
        self.inference_times.append((timestamp, inference_ms))
        
        if len(self.inference_times) < self.min_samples_for_detection:
            return None
        
        # Calculate median of recent inference times
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
        """Add memory value and check for memory spike events."""
        if self.memory_values:
            last_timestamp, last_memory = self.memory_values[-1]
            memory_delta = memory_mb - last_memory
            time_delta = timestamp - last_timestamp
            
            # Check for significant memory spike
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
        """Get events from the last window_seconds."""
        if not self.events:
            return []
        
        latest_time = self.events[-1]['timestamp']
        cutoff_time = latest_time - window_seconds
        
        return [e for e in self.events if e['timestamp'] >= cutoff_time]


class StreamingTimeseriesExtension:
    """Extension to StreamingMonitor for real-time plotting support."""
    
    def __init__(self, stream_manager):
        self.stream_manager = stream_manager
        self.timeseries_buffers: Dict[str, TimeseriesBuffer] = {}
        self.event_detector = EventDetector()
        self.benchmark_start_time = None
        
        # Metrics we want to track for plotting
        self.plot_metrics = {
            'process.memory.rss_mb',
            'memory_profiler.rss_mb', 
            'cpu.usage_percent',
            'memory.percent',
            'thermal.cpu_temp',
            'memory_events.spike_detected',
            'memory_profiler.traced_delta_mb'
        }
    
    def start_timeseries_tracking(self) -> None:
        """Initialize timeseries buffers for plot metrics."""
        self.benchmark_start_time = time.time()
        
        # Create buffers for metrics we want to plot
        for metric in self.plot_metrics:
            self.timeseries_buffers[metric] = TimeseriesBuffer(max_samples=200)
    
    def update_timeseries_buffers(self) -> None:
        """Update timeseries buffers with latest data from streams."""
        current_data = self.stream_manager.get_all_current_data()
        
        for metric_type, sample in current_data.items():
            if sample is None:
                continue
            
            # Add to buffer if we're tracking this metric
            if metric_type in self.timeseries_buffers:
                self.timeseries_buffers[metric_type].add_sample(
                    sample.timestamp, sample.value
                )
            
            # Feed to event detector
            if metric_type == 'process.memory.rss_mb' or metric_type == 'memory_profiler.rss_mb':
                self.event_detector.add_memory_value(sample.timestamp, sample.value)
    
    def add_inference_timing(self, inference_ms: float) -> Optional[Dict]:
        """Add inference timing data and detect slow inference events."""
        if self.benchmark_start_time is None:
            return None
        
        current_time = self.stream_manager.time_manager.get_timestamp()
        return self.event_detector.add_inference_time(current_time, inference_ms)
    
    def get_plot_data(self, metric_type: str, window_seconds: float = 30.0) -> List[Tuple[float, Any]]:
        """Get time-series data for plotting a specific metric."""
        if metric_type not in self.timeseries_buffers:
            return []
        
        return self.timeseries_buffers[metric_type].get_recent(window_seconds)
    
    def get_inference_timeline(self, window_seconds: float = 30.0) -> List[Tuple[float, float]]:
        """Get recent inference timings for timeline plot."""
        # This will be fed from benchmark execution
        return self.event_detector.inference_times
    
    def get_memory_timeline(self, window_seconds: float = 30.0) -> List[Tuple[float, float]]:
        """Get memory usage timeline."""
        # Try memory profiler first, fall back to process memory
        memory_data = self.get_plot_data('memory_profiler.rss_mb', window_seconds)
        if not memory_data:
            memory_data = self.get_plot_data('process.memory.rss_mb', window_seconds)
        return memory_data
    
    def get_cpu_timeline(self, window_seconds: float = 30.0) -> List[Tuple[float, float]]:
        """Get CPU usage timeline."""
        return self.get_plot_data('cpu.usage_percent', window_seconds)
    
    def get_events_timeline(self, window_seconds: float = 30.0) -> List[Dict]:
        """Get recent events for timeline markers."""
        return self.event_detector.get_recent_events(window_seconds)
    
    def get_system_correlation_data(self, window_seconds: float = 30.0) -> Dict[str, List[Tuple[float, float]]]:
        """Get data for system correlation plot (CPU vs Memory vs Performance)."""
        return {
            'cpu': self.get_cpu_timeline(window_seconds),
            'memory': self.get_memory_timeline(window_seconds),
            'events': self.get_events_timeline(window_seconds)
        }
    
    def clear_timeseries_data(self) -> None:
        """Clear all timeseries buffers."""
        for buffer in self.timeseries_buffers.values():
            buffer.clear()
        self.event_detector = EventDetector()


# Extension method to add to StreamingMonitor
def add_timeseries_support(streaming_monitor):
    """Add timeseries plotting support to existing StreamingMonitor."""
    
    # Create timeseries extension
    ts_extension = StreamingTimeseriesExtension(streaming_monitor.stream_manager)
    streaming_monitor.timeseries = ts_extension
    
    # Override start/stop to include timeseries tracking
    original_start = streaming_monitor.start_monitoring
    original_stop = streaming_monitor.stop_monitoring
    
    def start_with_timeseries():
        original_start()
        ts_extension.start_timeseries_tracking()
    
    def stop_with_timeseries():
        original_stop()
        # Keep timeseries data for post-analysis
    
    streaming_monitor.start_monitoring = start_with_timeseries
    streaming_monitor.stop_monitoring = stop_with_timeseries
    
    # Add convenience methods
    streaming_monitor.update_timeseries = ts_extension.update_timeseries_buffers
    streaming_monitor.add_inference_timing = ts_extension.add_inference_timing
    streaming_monitor.get_plot_data = ts_extension.get_plot_data
    streaming_monitor.get_inference_timeline = ts_extension.get_inference_timeline
    streaming_monitor.get_memory_timeline = ts_extension.get_memory_timeline
    streaming_monitor.get_cpu_timeline = ts_extension.get_cpu_timeline
    streaming_monitor.get_events_timeline = ts_extension.get_events_timeline
    streaming_monitor.get_system_correlation_data = ts_extension.get_system_correlation_data
    
    return streaming_monitor
