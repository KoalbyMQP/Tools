# WARNING: this is just a basic class I create to get a feel for what the api for a basic system status monitor should look like
# this was soley made to ensure for a functional TUI and has no other purpose! 

import time
import psutil
import platform
from typing import Dict, Optional, Tuple, Any


class SystemMonitor:
    """Minimal, robust system monitor for Raspberry Pi - untested on hardware"""
    
    def __init__(self):
        # TODO: Test Pi model detection on actual hardware
        self.pi_model = self._detect_pi_model()
        self.cpu_count = psutil.cpu_count() or 4
        
    def _detect_pi_model(self) -> str:
        """Detect Raspberry Pi model - fallback gracefully"""
        try:
            # FIXME: Test this path exists on target Pi (/proc/cpuinfo)
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'Model' in line:
                        return line.split(':')[1].strip()
        except Exception:
            # TODO: Add logging when Pi detection fails
            pass
        return platform.machine() or "Unknown Pi Model"
    
    def get_cpu_usage(self) -> Dict[str, Any]:
        """Get CPU stats with safe fallbacks"""
        result = {
            'usage_percent': 0.0,
            'frequency_ghz': 0.0,
            'load_1min': 0.0,
            'core_count': self.cpu_count
        }
        
        try:
            result['usage_percent'] = float(psutil.cpu_percent(interval=0.1))
        except Exception:
            # FIXME: Handle psutil.cpu_percent() failures on Pi
            pass
            
        try:
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                result['frequency_ghz'] = float(cpu_freq.current / 1000)
        except Exception:
            # TODO: Add vcgencmd fallback for Pi frequency
            pass
            
        try:
            # FIXME: Verify getloadavg works on Pi OS
            if hasattr(psutil, 'getloadavg'):
                load_avg = psutil.getloadavg()
                result['load_1min'] = float(load_avg[0])
        except Exception:
            pass
        
        return result
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get memory stats with safe conversion"""
        # Safe defaults for typical Pi
        result = {
            'ram_used_gb': 0.0,
            'ram_total_gb': 4.0,
            'ram_percent': 0.0,
            'swap_used_gb': 0.0,
            'swap_total_gb': 0.0
        }
        
        try:
            memory = psutil.virtual_memory()
            result.update({
                'ram_used_gb': float(memory.used / (1024**3)),
                'ram_total_gb': float(memory.total / (1024**3)),
                'ram_percent': float(memory.percent)
            })
        except Exception:
            # FIXME: Handle memory detection failures gracefully
            pass
            
        try:
            swap = psutil.swap_memory()
            result.update({
                'swap_used_gb': float(swap.used / (1024**3)),
                'swap_total_gb': float(swap.total / (1024**3))
            })
        except Exception:
            # TODO: Swap might not be configured on Pi
            pass
        
        return result
    
    def get_temperature(self) -> Dict[str, Optional[float]]:
        """Get temperature with multiple fallback methods"""
        result = {'cpu_temp': None}
        
        # Method 1: Pi-specific thermal zone (most reliable on Pi)
        try:
            # TODO: Verify this path exists on target Pi hardware
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_raw = int(f.read().strip())
                result['cpu_temp'] = float(temp_raw / 1000.0)
                return result
        except Exception:
            # FIXME: This is the primary Pi temp method - needs testing
            pass
        
        # Method 2: vcgencmd (Pi-specific command)
        try:
            import subprocess
            # TODO: Test vcgencmd availability on Pi
            cmd_result = subprocess.run(['vcgencmd', 'measure_temp'], 
                                      capture_output=True, text=True, timeout=2)
            if cmd_result.returncode == 0:
                temp_str = cmd_result.stdout.strip()
                if 'temp=' in temp_str:
                    temp_val = temp_str.split('temp=')[1].replace("'C", "")
                    result['cpu_temp'] = float(temp_val)
                    return result
        except Exception:
            # FIXME: vcgencmd might not be available or in PATH
            pass
        
        # Method 3: psutil sensors (generic fallback)
        try:
            sensors = psutil.sensors_temperatures()
            for name, entries in sensors.items():
                if entries and entries[0].current:
                    result['cpu_temp'] = float(entries[0].current)
                    return result
        except Exception:
            # TODO: psutil sensors might not work on Pi
            pass
        
        return result
    
    def get_throttling_status(self) -> Dict[str, bool]:
        """Check Pi throttling status - Pi-specific feature"""
        default_status = {
            'is_throttled': False,
            'was_throttled': False,
            'is_undervolted': False,
            'was_undervolted': False
        }
        
        try:
            # FIXME: This path is Pi-specific - verify it exists
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
            # TODO: Add vcgencmd get_throttled as fallback
            pass
            
        return default_status
    
    def is_healthy(self) -> Tuple[bool, list]:
        """Basic health check with Pi-appropriate thresholds"""
        warnings = []
        
        try:
            # Temperature check
            temps = self.get_temperature()
            cpu_temp = temps.get('cpu_temp')
            if cpu_temp:
                # TODO: Adjust thresholds for specific Pi model (Pi 4 vs Pi 5)
                if cpu_temp > 80:  # Pi throttles at ~80C
                    warnings.append(f"Critical CPU temperature: {cpu_temp:.1f}°C")
                elif cpu_temp > 70:
                    warnings.append(f"High CPU temperature: {cpu_temp:.1f}°C")
            
            # Memory check
            memory = self.get_memory_usage()
            if memory['ram_percent'] > 90:  # More conservative for Pi
                warnings.append(f"Critical memory usage: {memory['ram_percent']:.1f}%")
            elif memory['ram_percent'] > 80:
                warnings.append(f"High memory usage: {memory['ram_percent']:.1f}%")
            
            # Throttling check (Pi-specific)
            throttle = self.get_throttling_status()
            if throttle['is_throttled']:
                warnings.append("System is currently throttled")
            if throttle['is_undervolted']:
                warnings.append("System is undervolted - check power supply")
            
            # Load check
            cpu = self.get_cpu_usage()
            # FIXME: Pi load thresholds need real-world testing
            high_load_threshold = self.cpu_count * 2.0  # More lenient for Pi
            if cpu['load_1min'] > high_load_threshold:
                warnings.append(f"High system load: {cpu['load_1min']:.1f}")
                
        except Exception as e:
            # TODO: Replace with proper logging system
            warnings.append(f"Health check failed: {str(e)}")
        
        return len(warnings) == 0, warnings
    
    def get_all_stats(self) -> Dict:
        """Get all system stats safely - never crash caller"""
        try:
            stats = {
                'pi_model': self.pi_model,
                'cpu': self.get_cpu_usage(),
                'memory': self.get_memory_usage(),
                'temperature': self.get_temperature(),
                'throttling': self.get_throttling_status(),
                'timestamp': time.time()
            }
            
            # Add health status
            is_healthy, warnings = self.is_healthy()
            stats['healthy'] = is_healthy
            stats['warnings'] = warnings
            
            return stats
            
        except Exception as e:
            # FIXME: This should never happen but ensure graceful failure
            return {
                'pi_model': self.pi_model or "Unknown",
                'cpu': {'usage_percent': 0, 'frequency_ghz': 0, 'load_1min': 0, 'core_count': self.cpu_count},
                'memory': {'ram_used_gb': 0, 'ram_total_gb': 4, 'ram_percent': 0, 'swap_used_gb': 0, 'swap_total_gb': 0},
                'temperature': {'cpu_temp': None},
                'throttling': {'is_throttled': False, 'was_throttled': False, 'is_undervolted': False, 'was_undervolted': False},
                'timestamp': time.time(),
                'healthy': False,
                'warnings': [f"Monitor system failure: {str(e)}"],
                'error': str(e)
            }