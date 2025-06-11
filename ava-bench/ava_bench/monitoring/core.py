# ava_bench/monitoring/core.py

import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, Union, Optional
from collections import deque


@dataclass
class MetricSample:
    """A single timestamped measurement from a collector."""
    timestamp: float  # High-precision relative timestamp
    metric_type: str  # "cpu.usage", "memory.rss", "thermal.cpu_temp"
    value: Union[float, int, dict]  # The actual measurement
    source: str  # Which collector produced this
    metadata: Optional[Dict[str, Any]] = None  # Extra context


class TimeManager:
    """Manages synchronized timestamps across all collectors. No magic."""
    
    def __init__(self):
        # Record start time for relative timestamps
        self.start_time = time.perf_counter()
        self.reference_time = time.time()
    
    def get_timestamp(self) -> float:
        """Get high-precision timestamp relative to benchmark start."""
        return time.perf_counter() - self.start_time
    
    def to_absolute_time(self, relative_timestamp: float) -> float:
        """Convert relative timestamp to wall clock time."""
        return self.reference_time + relative_timestamp


class MetricStream:
    """Thread-safe stream of timestamped metrics. Simple ring buffer."""
    
    def __init__(self, metric_type: str, buffer_size: int = 10000):
        self.metric_type = metric_type
        self.buffer_size = buffer_size
        self._samples = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
    
    def add_sample(self, timestamp: float, value: Union[float, int, dict], 
                   source: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a new sample to the stream."""
        sample = MetricSample(
            timestamp=timestamp,
            metric_type=self.metric_type,
            value=value,
            source=source,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._samples.append(sample)
    
    def get_samples(self, since_timestamp: Optional[float] = None) -> List[MetricSample]:
        """Get all samples since a given timestamp."""
        with self._lock:
            if since_timestamp is None:
                return list(self._samples)
            
            return [s for s in self._samples if s.timestamp >= since_timestamp]
    
    def get_latest(self) -> Optional[MetricSample]:
        """Get the most recent sample."""
        with self._lock:
            return self._samples[-1] if self._samples else None
    
    def clear(self) -> None:
        """Clear all samples from the stream."""
        with self._lock:
            self._samples.clear()


class MetricCollector(ABC):
    """Base class for all metric collectors. Explicit interface."""
    
    def __init__(self, sampling_rate_hz: float, stream_manager: 'StreamManager'):
        self.sampling_rate_hz = sampling_rate_hz
        self.stream_manager = stream_manager
        self.time_manager = stream_manager.time_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    @abstractmethod
    def _collect_sample(self) -> Dict[str, Any]:
        """Collect metrics and return as dict. Override this."""
        pass
    
    @abstractmethod
    def get_collector_name(self) -> str:
        """Return name for this collector."""
        pass
    
    def start_collection(self) -> None:
        """Start collecting metrics in background thread."""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()
    
    def stop_collection(self) -> None:
        """Stop collecting metrics."""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
    
    def _collection_loop(self) -> None:
        """Main collection loop. Runs in background thread."""
        interval = 1.0 / self.sampling_rate_hz
        
        while self._running and not self._stop_event.is_set():
            try:
                # Collect samples
                timestamp = self.time_manager.get_timestamp()
                samples = self._collect_sample()
                
                # Send to stream manager
                for metric_type, value in samples.items():
                    self.stream_manager.add_sample(
                        metric_type=metric_type,
                        timestamp=timestamp,
                        value=value,
                        source=self.get_collector_name()
                    )
                
            except Exception as e:
                # Don't crash the collector on errors
                print(f"Error in {self.get_collector_name()}: {e}")
            
            # Wait for next sample
            self._stop_event.wait(interval)


class StreamManager:
    """Coordinates all metric collectors and streams. Central coordinator."""
    
    def __init__(self):
        self.time_manager = TimeManager()
        self.collectors: List[MetricCollector] = []
        self.streams: Dict[str, MetricStream] = {}
        self._lock = threading.Lock()
    
    def add_collector(self, collector: MetricCollector) -> None:
        """Add a metric collector."""
        self.collectors.append(collector)
    
    def add_sample(self, metric_type: str, timestamp: float, 
                   value: Union[float, int, dict], source: str, 
                   metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a sample to the appropriate stream."""
        with self._lock:
            # Create stream if it doesn't exist
            if metric_type not in self.streams:
                self.streams[metric_type] = MetricStream(metric_type)
            
            self.streams[metric_type].add_sample(timestamp, value, source, metadata)
    
    def start_collection(self) -> None:
        """Start all collectors."""
        for collector in self.collectors:
            collector.start_collection()
    
    def stop_collection(self) -> None:
        """Stop all collectors."""
        for collector in self.collectors:
            collector.stop_collection()
    
    def get_all_current_data(self) -> Dict[str, MetricSample]:
        """Get latest sample from each stream."""
        with self._lock:
            return {
                metric_type: stream.get_latest()
                for metric_type, stream in self.streams.items()
                if stream.get_latest() is not None
            }
    
    def get_stream(self, metric_type: str) -> Optional[MetricStream]:
        """Get a specific metric stream."""
        with self._lock:
            return self.streams.get(metric_type)
    
    def clear_all_streams(self) -> None:
        """Clear all metric streams."""
        with self._lock:
            for stream in self.streams.values():
                stream.clear()