# ava_bench/monitoring/collectors.py

import psutil
import platform
from .core import MetricCollector
import subprocess
import re
from typing import Dict, Any, Optional, List
import tracemalloc
import gc
import time
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, deque
from ..monitoring.core import MetricCollector


class SystemCollector(MetricCollector):
    """Streams system-level metrics. Replaces the old SystemMonitor."""
    
    def __init__(self, sampling_rate_hz: float, stream_manager):
        super().__init__(sampling_rate_hz, stream_manager)
        self.pi_model = self._detect_pi_model()
        self.cpu_count = psutil.cpu_count() or 4
    
    def get_collector_name(self) -> str:
        return "system"
    
    def _detect_pi_model(self) -> str:
        """Detect Raspberry Pi model. Simple, no magic."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'Model' in line:
                        return line.split(':')[1].strip()
        except Exception:
            pass
        return platform.machine() or "Unknown"
    
    def _collect_sample(self) -> Dict[str, Any]:
        """Collect all system metrics in one go."""
        samples = {}
        
        # CPU metrics
        try:
            cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
            samples['cpu.usage_percent'] = float(cpu_percent)
        except Exception:
            samples['cpu.usage_percent'] = 0.0
        
        try:
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                samples['cpu.frequency_ghz'] = float(cpu_freq.current / 1000)
        except Exception:
            samples['cpu.frequency_ghz'] = 0.0
        
        try:
            if hasattr(psutil, 'getloadavg'):
                load_avg = psutil.getloadavg()
                samples['cpu.load_1min'] = float(load_avg[0])
        except Exception:
            samples['cpu.load_1min'] = 0.0
        
        # Memory metrics
        try:
            memory = psutil.virtual_memory()
            samples['memory.used_gb'] = float(memory.used / (1024**3))
            samples['memory.total_gb'] = float(memory.total / (1024**3))
            samples['memory.percent'] = float(memory.percent)
        except Exception:
            samples['memory.used_gb'] = 0.0
            samples['memory.total_gb'] = 4.0
            samples['memory.percent'] = 0.0
        
        try:
            swap = psutil.swap_memory()
            samples['memory.swap_used_gb'] = float(swap.used / (1024**3))
            samples['memory.swap_total_gb'] = float(swap.total / (1024**3))
        except Exception:
            samples['memory.swap_used_gb'] = 0.0
            samples['memory.swap_total_gb'] = 0.0
        
        # Thermal metrics
        temp = self._get_cpu_temperature()
        if temp is not None:
            samples['thermal.cpu_temp'] = float(temp)
        
        # Pi-specific throttling
        throttle_status = self._get_throttling_status()
        samples['thermal.is_throttled'] = throttle_status['is_throttled']
        samples['thermal.is_undervolted'] = throttle_status['is_undervolted']
        
        return samples
    
    def _get_cpu_temperature(self) -> float:
        """Get CPU temperature. Try Pi-specific methods first."""
        # Method 1: Pi thermal zone
        # CAUTION: NOT TESTED
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_raw = int(f.read().strip())
                return float(temp_raw / 1000.0)
        except Exception:
            pass
        
        # Method 2: vcgencmd (Pi command)
        # CAUTION: NOT TESTED
        try:
            import subprocess
            result = subprocess.run(['vcgencmd', 'measure_temp'], 
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                temp_str = result.stdout.strip()
                if 'temp=' in temp_str:
                    temp_val = temp_str.split('temp=')[1].replace("'C", "")
                    return float(temp_val)
        except Exception:
            pass
        
        # Method 3: psutil sensors (generic)
        try:
            sensors = psutil.sensors_temperatures()
            for name, entries in sensors.items():
                if entries and entries[0].current:
                    return float(entries[0].current)
        except Exception:
            pass
        
        return None
    
    def _get_throttling_status(self) -> Dict[str, bool]:
        """Check Pi throttling status."""
        default = {
            'is_throttled': False,
            'was_throttled': False,
            'is_undervolted': False,
            'was_undervolted': False
        }
        
        try:
            with open('/sys/devices/platform/soc/soc:firmware/get_throttled', 'r') as f:
                throttle_hex = f.read().strip()
                throttle_int = int(throttle_hex, 16)
                
                return {
                    'is_throttled': bool(throttle_int & 0x1),
                    'is_undervolted': bool(throttle_int & 0x10000),
                    'was_throttled': bool(throttle_int & 0x2),
                    'was_undervolted': bool(throttle_int & 0x20000)
                }
        except Exception:
            pass
        
        return default

class ProcessCollector(MetricCollector):
    """Streams metrics for a specific process (the benchmark process)."""
    
    def __init__(self, sampling_rate_hz: float, stream_manager, pid: int = None):
        super().__init__(sampling_rate_hz, stream_manager)
        self.pid = pid or psutil.Process().pid
        try:
            self.process = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            self.process = None
    
    def get_collector_name(self) -> str:
        return f"process_{self.pid}"
    
    def _collect_sample(self) -> Dict[str, Any]:
        """Collect process-specific metrics."""
        if not self.process:
            return {}
        
        samples = {}
        
        try:
            # Memory info
            memory_info = self.process.memory_info()
            samples['process.memory.rss_mb'] = float(memory_info.rss / (1024 * 1024))
            samples['process.memory.vms_mb'] = float(memory_info.vms / (1024 * 1024))
            
            # CPU usage
            cpu_percent = self.process.cpu_percent(interval=None)
            samples['process.cpu.percent'] = float(cpu_percent)
            
            # Thread count
            num_threads = self.process.num_threads()
            samples['process.threads.count'] = int(num_threads)
            
            # File descriptors
            try:
                num_fds = self.process.num_fds()
                samples['process.files.open_count'] = int(num_fds)
            except AttributeError:
                # Not available on all platforms
                pass
            
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process might have ended or we lost access
            self.process = None
        
        return samples
    
class PerfCollector(MetricCollector):
    """Collect hardware performance counters via Linux perf. No magic."""
    
    # Hardware counters we care about for ML workloads
    DEFAULT_COUNTERS = [
        'cpu-cycles',
        'instructions', 
        'cache-references',
        'cache-misses',
        'branch-instructions',
        'branch-misses',
        'L1-dcache-loads',
        'L1-dcache-load-misses',
        'LLC-loads',
        'LLC-load-misses'
    ]
    
    def __init__(self, sampling_rate_hz: float, stream_manager, 
                 pid: Optional[int] = None, counters: Optional[List[str]] = None):
        super().__init__(sampling_rate_hz, stream_manager)
        self.pid = pid  # If None, monitor whole system
        self.counters = counters or self.DEFAULT_COUNTERS
        self.perf_process: Optional[subprocess.Popen] = None
        self._baseline_values: Dict[str, int] = {}
        self._last_values: Dict[str, int] = {}
        
        # Check if perf is available
        self.perf_available = self._check_perf_available()
    
    def get_collector_name(self) -> str:
        if self.pid:
            return f"perf_pid_{self.pid}"
        return "perf_system"
    
    def _check_perf_available(self) -> bool:
        """Check if perf is available and we have permissions."""
        try:
            # Try to run perf stat --version
            result = subprocess.run(['perf', 'stat', '--version'], 
                                  capture_output=True, timeout=2)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def start_collection(self) -> None:
        """Start perf stat process and begin collecting."""
        if not self.perf_available:
            print(f"Warning: perf not available for {self.get_collector_name()}")
            return
        
        # Get baseline readings first
        self._get_baseline_counters()
        
        super().start_collection()
    
    def stop_collection(self) -> None:
        """Stop collection and clean up perf process."""
        super().stop_collection()
        
        if self.perf_process:
            try:
                self.perf_process.terminate()
                self.perf_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.perf_process.kill()
            self.perf_process = None
    
    def _get_baseline_counters(self) -> None:
        """Get initial counter values to calculate deltas."""
        counters = self._read_perf_counters_once()
        self._baseline_values = counters.copy()
        self._last_values = counters.copy()
    
    def _read_perf_counters_once(self) -> Dict[str, int]:
        """Read perf counters once and return values."""
        if not self.perf_available:
            return {}
        
        # Build perf stat command
        cmd = ['perf', 'stat', '-x', ',']  # CSV output
        
        # Add counters
        for counter in self.counters:
            cmd.extend(['-e', counter])
        
        # Add target (process or system)
        if self.pid:
            cmd.extend(['-p', str(self.pid)])
        else:
            cmd.append('-a')  # All CPUs
        
        # Run for a short time to get readings
        cmd.extend(['sleep', '0.01'])  # 10ms sample
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
            return self._parse_perf_output(result.stderr)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return {}
    
    def _parse_perf_output(self, output: str) -> Dict[str, int]:
        """Parse perf stat CSV output into counter values."""
        counters = {}
        
        for line in output.strip().split('\n'):
            if not line or line.startswith('#'):
                continue
            
            # CSV format: value,unit,event,running,ratio
            parts = line.split(',')
            if len(parts) < 3:
                continue
            
            try:
                value_str = parts[0].strip()
                event_name = parts[2].strip()
                
                # Handle <not counted> or <not supported>
                if '<not' in value_str:
                    continue
                
                # Remove any formatting (commas, etc.)
                value_str = re.sub(r'[,\s]', '', value_str)
                value = int(value_str)
                
                counters[event_name] = value
                
            except (ValueError, IndexError):
                continue
        
        return counters
    
    def _collect_sample(self) -> Dict[str, Any]:
        """Collect performance counter deltas since last sample."""
        if not self.perf_available:
            return {}
        
        # Get current counter values
        current_counters = self._read_perf_counters_once()
        if not current_counters:
            return {}
        
        samples = {}
        
        # Calculate deltas since last sample
        for counter, current_value in current_counters.items():
            last_value = self._last_values.get(counter, 0)
            delta = current_value - last_value
            
            # Store both absolute and rate
            samples[f'perf.{counter}.total'] = current_value
            samples[f'perf.{counter}.delta'] = delta
            samples[f'perf.{counter}.rate'] = delta * self.sampling_rate_hz
        
        # Calculate derived metrics
        if 'instructions' in current_counters and 'cpu-cycles' in current_counters:
            instructions = current_counters['instructions'] - self._last_values.get('instructions', 0)
            cycles = current_counters['cpu-cycles'] - self._last_values.get('cpu-cycles', 0)
            
            if cycles > 0:
                ipc = instructions / cycles
                samples['perf.ipc'] = float(ipc)
        
        if 'cache-references' in current_counters and 'cache-misses' in current_counters:
            refs = current_counters['cache-references'] - self._last_values.get('cache-references', 0)
            misses = current_counters['cache-misses'] - self._last_values.get('cache-misses', 0)
            
            if refs > 0:
                hit_rate = (refs - misses) / refs
                samples['perf.cache_hit_rate'] = float(hit_rate)
        
        # Update last values
        self._last_values = current_counters
        
        return samples

class SimplePerfCollector(MetricCollector):
    """Simplified perf collector that just runs perf stat periodically."""
    
    def __init__(self, sampling_rate_hz: float, stream_manager, pid: Optional[int] = None):
        super().__init__(sampling_rate_hz, stream_manager)
        self.pid = pid
        self.perf_available = self._check_perf_available()
    
    def get_collector_name(self) -> str:
        return f"simple_perf_{self.pid}" if self.pid else "simple_perf_system"
    
    def _check_perf_available(self) -> bool:
        """Check if perf is available."""
        try:
            result = subprocess.run(['which', 'perf'], capture_output=True, timeout=1)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _collect_sample(self) -> Dict[str, Any]:
        """Run perf stat for one sampling interval."""
        if not self.perf_available:
            return {}
        
        interval = 1.0 / self.sampling_rate_hz
        
        # Simple perf stat command
        cmd = [
            'perf', 'stat',
            '-e', 'cycles,instructions,cache-references,cache-misses',
            '-x', ','  # CSV output
        ]
        
        if self.pid:
            cmd.extend(['-p', str(self.pid)])
        else:
            cmd.append('-a')
        
        cmd.extend(['sleep', str(interval * 0.8)])  # Sample for most of interval
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=interval)
            return self._parse_simple_output(result.stderr)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return {}
    
    def _parse_simple_output(self, output: str) -> Dict[str, Any]:
        """Parse simple perf output."""
        samples = {}
        
        for line in output.strip().split('\n'):
            if not line or line.startswith('#'):
                continue
            
            parts = line.split(',')
            if len(parts) < 3:
                continue
            
            try:
                value_str = parts[0].strip()
                event_name = parts[2].strip()
                
                if '<not' in value_str:
                    continue
                
                value_str = re.sub(r'[,\s]', '', value_str)
                value = int(value_str)
                
                samples[f'perf.{event_name}'] = value
                
            except (ValueError, IndexError):
                continue
        
        return samples
    
class MemoryProfilerCollector(MetricCollector):
    """Profile Python memory allocations during ML inference using tracemalloc."""
    
    def __init__(self, sampling_rate_hz: float, stream_manager, enable_tracemalloc: bool = True):
        super().__init__(sampling_rate_hz, stream_manager)
        self.enable_tracemalloc = enable_tracemalloc
        self.tracemalloc_started = False
        self.baseline_memory = 0
        self.peak_memory = 0
        self.allocation_history = deque(maxlen=1000)  # Keep last 1000 snapshots
        
        # Track memory by category
        self.framework_memory = defaultdict(int)
        self.ml_frameworks = ['numpy', 'onnx', 'tensorflow', 'torch', 'cv2']
        
    def get_collector_name(self) -> str:
        return "memory_profiler"
    
    def start_collection(self) -> None:
        """Start memory profiling with tracemalloc if enabled."""
        if self.enable_tracemalloc and not tracemalloc.is_tracing():
            try:
                tracemalloc.start(10)  # Keep 10 frames of traceback
                self.tracemalloc_started = True
                
                # Get baseline memory usage
                current, peak = tracemalloc.get_traced_memory()
                self.baseline_memory = current
                self.peak_memory = peak
                
            except Exception as e:
                print(f"Warning: Could not start tracemalloc: {e}")
                self.tracemalloc_started = False
        
        super().start_collection()
    
    def stop_collection(self) -> None:
        """Stop memory profiling and tracemalloc."""
        super().stop_collection()
        
        if self.tracemalloc_started and tracemalloc.is_tracing():
            tracemalloc.stop()
            self.tracemalloc_started = False
    
    def _collect_sample(self) -> Dict[str, Any]:
        """Collect memory profiling data."""
        samples = {}
        
        # Basic memory info from psutil (always available)
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            samples['memory_profiler.rss_mb'] = float(memory_info.rss / (1024 * 1024))
            samples['memory_profiler.vms_mb'] = float(memory_info.vms / (1024 * 1024))
            
            # Memory percentage of system
            system_memory = psutil.virtual_memory()
            samples['memory_profiler.system_percent'] = float(system_memory.percent)
            
        except Exception:
            pass
        
        # Tracemalloc data (if available)
        if self.tracemalloc_started and tracemalloc.is_tracing():
            try:
                current, peak = tracemalloc.get_traced_memory()
                
                samples['memory_profiler.traced_current_mb'] = float(current / (1024 * 1024))
                samples['memory_profiler.traced_peak_mb'] = float(peak / (1024 * 1024))
                
                # Calculate relative to baseline
                current_delta = current - self.baseline_memory
                samples['memory_profiler.traced_delta_mb'] = float(current_delta / (1024 * 1024))
                
                # Update peak tracking
                if peak > self.peak_memory:
                    self.peak_memory = peak
                    samples['memory_profiler.new_peak_detected'] = True
                
                # Analyze current allocations by framework
                self._analyze_allocations(samples)
                
            except Exception as e:
                samples['memory_profiler.tracemalloc_error'] = str(e)
        
        # Garbage collection stats
        try:
            gc_stats = gc.get_stats()
            if gc_stats:
                # Focus on generation 2 (long-lived objects)
                gen2 = gc_stats[2] if len(gc_stats) > 2 else {}
                samples['memory_profiler.gc_collections'] = gen2.get('collections', 0)
                samples['memory_profiler.gc_collected'] = gen2.get('collected', 0)
                samples['memory_profiler.gc_uncollectable'] = gen2.get('uncollectable', 0)
        except Exception:
            pass
        
        return samples
    
    def _analyze_allocations(self, samples: Dict[str, Any]) -> None:
        """Analyze current allocations by framework/module."""
        try:
            snapshot = tracemalloc.take_snapshot()
            
            # Group allocations by module/framework
            framework_allocations = defaultdict(int)
            total_size = 0
            
            for stat in snapshot.statistics('filename'):
                size_mb = stat.size / (1024 * 1024)
                total_size += size_mb
                
                # Try to identify ML framework from filename
                filename = stat.traceback.format()[0] if stat.traceback.format() else ""
                
                for framework in self.ml_frameworks:
                    if framework in filename.lower():
                        framework_allocations[framework] += size_mb
                        break
                else:
                    framework_allocations['other'] += size_mb
            
            # Add framework-specific allocations to samples
            for framework, size_mb in framework_allocations.items():
                if size_mb > 0:  # Only report non-zero allocations
                    samples[f'memory_profiler.{framework}_mb'] = float(size_mb)
            
            samples['memory_profiler.total_traced_mb'] = float(total_size)
            
        except Exception as e:
            samples['memory_profiler.allocation_analysis_error'] = str(e)

class MemoryEventDetector(MetricCollector):
    """Detect memory events and patterns during ML inference."""
    
    def __init__(self, sampling_rate_hz: float, stream_manager, 
                 spike_threshold_mb: float = 10.0, leak_window: int = 50):
        super().__init__(sampling_rate_hz, stream_manager)
        self.spike_threshold_mb = spike_threshold_mb
        self.leak_window = leak_window
        
        # Track memory over time for pattern detection
        self.memory_history = deque(maxlen=leak_window)
        self.baseline_memory = None
        self.last_spike_time = 0
        self.spike_count = 0
        
    def get_collector_name(self) -> str:
        return "memory_events"
    
    def _collect_sample(self) -> Dict[str, Any]:
        """Detect memory events and patterns."""
        samples = {}
        current_time = self.time_manager.get_timestamp()
        
        # Get current memory usage from other streams
        current_memory = self._get_current_memory_usage()
        if current_memory is None:
            return samples
        
        # Add to history
        self.memory_history.append((current_time, current_memory))
        
        # Set baseline if not set
        if self.baseline_memory is None:
            self.baseline_memory = current_memory
            samples['memory_events.baseline_set'] = True
            samples['memory_events.baseline_mb'] = self.baseline_memory
        
        # Detect memory spikes
        memory_delta = current_memory - self.baseline_memory
        if memory_delta > self.spike_threshold_mb:
            time_since_last_spike = current_time - self.last_spike_time
            if time_since_last_spike > 1.0:  # Don't report spikes more than once per second
                self.spike_count += 1
                self.last_spike_time = current_time
                
                samples['memory_events.spike_detected'] = True
                samples['memory_events.spike_size_mb'] = memory_delta
                samples['memory_events.total_spikes'] = self.spike_count
        
        # Detect memory leaks (growing trend)
        if len(self.memory_history) >= self.leak_window:
            leak_detected, leak_rate = self._detect_memory_leak()
            if leak_detected:
                samples['memory_events.leak_detected'] = True
                samples['memory_events.leak_rate_mb_per_sec'] = leak_rate
        
        # Calculate memory statistics
        if len(self.memory_history) > 1:
            recent_memories = [mem for _, mem in self.memory_history]
            samples['memory_events.current_mb'] = current_memory
            samples['memory_events.min_mb'] = min(recent_memories)
            samples['memory_events.max_mb'] = max(recent_memories)
            samples['memory_events.mean_mb'] = sum(recent_memories) / len(recent_memories)
            
            # Memory volatility (standard deviation)
            mean = samples['memory_events.mean_mb']
            variance = sum((mem - mean) ** 2 for mem in recent_memories) / len(recent_memories)
            samples['memory_events.volatility_mb'] = variance ** 0.5
        
        return samples
    
    def _get_current_memory_usage(self) -> Optional[float]:
        """Get current memory usage from system monitor."""
        try:
            # Try to get from memory profiler first
            profiler_stream = self.stream_manager.get_stream('memory_profiler.rss_mb')
            if profiler_stream:
                latest = profiler_stream.get_latest()
                if latest:
                    return latest.value
            
            # Fallback to process stream
            process_stream = self.stream_manager.get_stream('process.memory.rss_mb')
            if process_stream:
                latest = process_stream.get_latest()
                if latest:
                    return latest.value
            
            return None
            
        except Exception:
            return None
    
    def _detect_memory_leak(self) -> Tuple[bool, float]:
        """Detect if memory is consistently growing (potential leak)."""
        if len(self.memory_history) < self.leak_window:
            return False, 0.0
        
        # Calculate linear trend over the window
        times = [t for t, _ in self.memory_history]
        memories = [m for _, m in self.memory_history]
        
        # Simple linear regression
        n = len(times)
        sum_t = sum(times)
        sum_m = sum(memories)
        sum_tm = sum(t * m for t, m in zip(times, memories))
        sum_t2 = sum(t * t for t in times)
        
        # Slope (memory change per second)
        denominator = n * sum_t2 - sum_t * sum_t
        if denominator == 0:
            return False, 0.0
        
        slope = (n * sum_tm - sum_t * sum_m) / denominator
        
        # Consider it a leak if memory grows consistently > 1MB per minute
        leak_threshold = 1.0 / 60.0  # 1MB per minute = ~0.017 MB/sec
        
        return slope > leak_threshold, slope

class MLMemoryIntegration:
    """Integration helpers for adding memory profiling to existing monitoring."""
    
    @staticmethod
    def add_memory_profiling(stream_manager, enable_tracemalloc: bool = True, 
                           sampling_rate_hz: float = 5.0) -> List[MetricCollector]:
        """Add memory profiling collectors to existing stream manager."""
        collectors = []
        
        # Add memory profiler
        memory_profiler = MemoryProfilerCollector(
            sampling_rate_hz=sampling_rate_hz,
            stream_manager=stream_manager,
            enable_tracemalloc=enable_tracemalloc
        )
        collectors.append(memory_profiler)
        stream_manager.add_collector(memory_profiler)
                
        # Add memory event detector
        event_detector = MemoryEventDetector(
            sampling_rate_hz=sampling_rate_hz,
            stream_manager=stream_manager,
            spike_threshold_mb=5.0,  # 5MB spike threshold
            leak_window=20  # 20 samples for leak detection
        )
        collectors.append(event_detector)
        stream_manager.add_collector(event_detector)
        
        return collectors
    
    @staticmethod
    def create_memory_aware_monitor(enable_tracemalloc: bool = True):
        """Create a StreamingMonitor with memory profiling enabled."""
        from ..monitoring import StreamingMonitor, MonitorConfig
        
        config = MonitorConfig()
        config.collect_system_metrics = True
        config.collect_process_metrics = True
        config.collect_perf_metrics = False  # Focus on memory for now
        
        monitor = StreamingMonitor(config)
        
        # Add memory profiling
        MLMemoryIntegration.add_memory_profiling(
            monitor.stream_manager,
            enable_tracemalloc=enable_tracemalloc
        )
        
        return monitor