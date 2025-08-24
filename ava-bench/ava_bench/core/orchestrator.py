<<<<<<< HEAD
from typing import Dict, Any, List
from ..benchmarks import BENCHMARKS
from ..benchmarks.base import UniBench

class Orchestrator:
  def __init__(self):
    self.benchmarks = BENCHMARKS
  
  def create_benchmark(self, benchmark_id: str, config: Dict[str, Any]) -> UniBench:
    if benchmark_id not in self.benchmarks:
      raise ValueError(f"Unknown benchmark: {benchmark_id}")
    
    benchmark_class = self.benchmarks[benchmark_id]
    benchmark = benchmark_class(config)
    
    if not benchmark.validate_config():
      raise ValueError(f"Invalid config for {benchmark_id}")
    
    return benchmark
  
  def list_benchmarks(self) -> List[str]:
    return list(self.benchmarks.keys())
  
  def get_benchmark_info(self, benchmark_id: str) -> Dict[str, Any]:
    if benchmark_id in self.benchmarks:
      cls = self.benchmarks[benchmark_id]
      return {"id": cls.BENCHMARK_ID, "description": cls.DESCRIPTION}
    return None
=======
from typing import Dict, Any, List, Optional
from ..runner import run_executable
from ..monitoring.core import StreamManager
from ..monitoring.collectors import SystemCollector


class Orchestrator:
    """Orchestrates executable runs with monitoring capabilities."""
    
    def __init__(self):
        self.stream_manager = None
        self.monitoring_enabled = True
    
    def setup_monitoring(self, sampling_rate_hz: float = 1.0) -> None:
        """Setup monitoring with collectors."""
        self.stream_manager = StreamManager()
        
        # Add system monitoring by default
        system_collector = SystemCollector(sampling_rate_hz, self.stream_manager)
        self.stream_manager.add_collector(system_collector)
    
    def run_executable(self, command: List[str], *, 
                      timeout: Optional[int] = None,
                      output_file: Optional[str] = None,
                      enable_monitoring: bool = True) -> Dict[str, Any]:
        """
        Run an executable with optional monitoring.
        
        Args:
            command: List of command and arguments
            timeout: Optional timeout in seconds
            output_file: Optional file to save results
            enable_monitoring: Whether to enable system monitoring
            
        Returns:
            Combined results dictionary
        """
        monitor = None
        
        if enable_monitoring and self.monitoring_enabled:
            if not self.stream_manager:
                self.setup_monitoring()
            monitor = self.stream_manager
        
        return run_executable(
            command=command,
            monitor=monitor,
            timeout=timeout,
            output_file=output_file
        )
    
    def list_available_commands(self) -> List[str]:
        """List some common executable commands that can be run."""
        return [
            "echo",
            "ls", 
            "pwd",
            "python",
            "node",
            # Add more as needed
        ]
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get basic system information."""
        import platform
        import psutil
        
        return {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "architecture": platform.architecture(),
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "python_version": platform.python_version()
        }
>>>>>>> main
