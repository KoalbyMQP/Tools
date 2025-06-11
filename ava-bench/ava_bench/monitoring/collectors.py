# ava_bench/monitoring/collectors.py

import psutil
import platform
from .core import MetricCollector
import subprocess
import re
from typing import Dict, Any, Optional, List



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