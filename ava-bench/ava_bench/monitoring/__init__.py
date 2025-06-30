# ava_bench/monitoring/__init__.py

from .core import StreamManager, MetricSample, TimeManager
from .collectors import SystemCollector, ProcessCollector, PerfCollector, SimplePerfCollector, MLMemoryIntegration

__all__ = [
    'StreamingMonitor', 'MetricSample', 'MonitorConfig', 'MLMemoryIntegration'
]


class MonitorConfig:
    """Configuration for streaming monitor. Explicit settings."""
    
    def __init__(self):
        self.system_sampling_hz = 10.0  # 10 samples per second
        self.process_sampling_hz = 20.0  # 20 samples per second  
        self.perf_sampling_hz = 5.0     # 5 samples per second (perf is slower)
        
        # What to collect
        self.collect_system_metrics = True
        self.collect_process_metrics = True
        self.collect_perf_metrics = True
        self.use_simple_perf = False  # Use SimplePerfCollector by default        
        self.target_pid = None
        
        # Custom perf counters (None = use defaults)
        self.perf_counters = None

        # Memory settings
        self.collect_memory_profiling = True      # Enable memory profiling
        self.memory_sampling_hz = 5.0            # Memory profiling sample rate
        self.enable_tracemalloc = True           # Use Python tracemalloc
        self.memory_spike_threshold_mb = 5.0     # Alert threshold for memory spikes
        self.memory_leak_window = 20             # Window size for leak detection

class StreamingMonitor:
    """Main interface for streaming metric collection. Replaces SystemMonitor."""
    
    def __init__(self, config: MonitorConfig = None):
        self.config = config or MonitorConfig()
        self.stream_manager = StreamManager()
        self._setup_collectors()
    
    def _setup_collectors(self) -> None:
        """Setup collectors based on configuration."""
        
        if self.config.collect_system_metrics:
            system_collector = SystemCollector(
                sampling_rate_hz=self.config.system_sampling_hz,
                stream_manager=self.stream_manager
            )
            self.stream_manager.add_collector(system_collector)
        
        if self.config.collect_process_metrics:
            process_collector = ProcessCollector(
                sampling_rate_hz=self.config.process_sampling_hz,
                stream_manager=self.stream_manager,
                pid=self.config.target_pid
            )
            self.stream_manager.add_collector(process_collector)
        
        if self.config.collect_perf_metrics:
            if self.config.use_simple_perf:
                perf_collector = SimplePerfCollector(
                    sampling_rate_hz=self.config.perf_sampling_hz,
                    stream_manager=self.stream_manager,
                    pid=self.config.target_pid
                )
            else:
                perf_collector = PerfCollector(
                    sampling_rate_hz=self.config.perf_sampling_hz,
                    stream_manager=self.stream_manager,
                    pid=self.config.target_pid,
                    counters=self.config.perf_counters
                )
            self.stream_manager.add_collector(perf_collector)

        if self.config.collect_memory_profiling:
            self.memory_collectors = MLMemoryIntegration.add_memory_profiling(
                stream_manager=self.stream_manager,
                enable_tracemalloc=self.config.enable_tracemalloc,
                sampling_rate_hz=self.config.memory_sampling_hz
            )


    
    def start_monitoring(self) -> None:
        """Start all metric collection."""
        self.stream_manager.start_collection()
    
    def stop_monitoring(self) -> None:
        """Stop all metric collection."""
        self.stream_manager.stop_collection()
    
    def get_current_metrics(self) -> dict:
        """Get latest metrics from all streams. Compatible with old interface."""
        current_data = self.stream_manager.get_all_current_data()
        
        # Convert to format similar to old SystemMonitor.get_all_stats()
        stats = {
            'timestamp': self.stream_manager.time_manager.get_timestamp(),
            'cpu': {},
            'memory': {},
            'thermal': {},
            'process': {},
            'perf': {}
        }
        
        for metric_type, sample in current_data.items():
            if sample is None:
                continue
            
            # Route metrics to appropriate sections
            if metric_type.startswith('cpu.'):
                key = metric_type.replace('cpu.', '')
                stats['cpu'][key] = sample.value
            elif metric_type.startswith('memory.'):
                key = metric_type.replace('memory.', '')
                stats['memory'][key] = sample.value
            elif metric_type.startswith('thermal.'):
                key = metric_type.replace('thermal.', '')
                stats['thermal'][key] = sample.value
            elif metric_type.startswith('process.'):
                key = metric_type.replace('process.', '')
                stats['process'][key] = sample.value
            elif metric_type.startswith('perf.'):
                key = metric_type.replace('perf.', '')
                stats['perf'][key] = sample.value
        
        return stats
    
    def get_metric_history(self, metric_type: str, since_timestamp: float = None) -> list:
        """Get historical data for a specific metric."""
        stream = self.stream_manager.get_stream(metric_type)
        if not stream:
            return []
        
        samples = stream.get_samples(since_timestamp)
        return [(s.timestamp, s.value) for s in samples]
    
    def get_all_metric_types(self) -> list:
        """Get list of all available metric types."""
        return list(self.stream_manager.streams.keys())
    
    def clear_history(self) -> None:
        """Clear all historical data."""
        self.stream_manager.clear_all_streams()
    
    def export_data(self, start_time: float = None, end_time: float = None) -> dict:
        """Export all collected data in a structured format."""
        
        # First, collect all samples to determine the actual time range
        all_samples = []
        for stream in self.stream_manager.streams.values():
            samples = stream.get_samples()
            all_samples.extend(samples)
        
        # Calculate actual start and end times from collected data
        actual_start_time = start_time
        actual_end_time = end_time
        
        if all_samples:
            all_timestamps = [s.timestamp for s in all_samples]
            
            if actual_start_time is None:
                actual_start_time = min(all_timestamps)
            if actual_end_time is None:
                actual_end_time = max(all_timestamps)
        else:
            # No data collected
            if actual_start_time is None:
                actual_start_time = 0.0
            if actual_end_time is None:
                actual_end_time = 0.0
        
        data = {
            'start_time': actual_start_time,
            'end_time': actual_end_time,
            'collection_duration': actual_end_time - actual_start_time,
            'metrics': {}
        }
        
        # Now export metrics with proper filtering
        for metric_type, stream in self.stream_manager.streams.items():
            samples = stream.get_samples(start_time)
            
            # Filter by end time if specified
            if end_time is not None:
                samples = [s for s in samples if s.timestamp <= end_time]
            
            data['metrics'][metric_type] = [
                {
                    'timestamp': s.timestamp,
                    'value': s.value,
                    'source': s.source,
                    'metadata': s.metadata
                }
                for s in samples
            ]
        
        return data



# Compatibility function for existing code
def create_monitor(collect_perf: bool = False, target_pid: int = None, 
                   collect_memory: bool = True) -> StreamingMonitor:
    """Create a StreamingMonitor with simple configuration."""
    config = MonitorConfig()
    config.collect_perf_metrics = collect_perf
    config.target_pid = target_pid
    config.collect_memory_profiling = collect_memory
    return StreamingMonitor(config)

# Example usage patterns
if __name__ == "__main__":
    # Basic usage
    monitor = create_monitor()
    monitor.start_monitoring()
    
    import time
    time.sleep(2)  # Collect for 2 seconds
    
    current = monitor.get_current_metrics()
    print("Current CPU usage:", current['cpu'].get('usage_percent', 'N/A'))
    print("Current memory usage:", current['memory'].get('percent', 'N/A'))
    
    # Get CPU usage history
    cpu_history = monitor.get_metric_history('cpu.usage_percent')
    print(f"Collected {len(cpu_history)} CPU samples")
    
    monitor.stop_monitoring()