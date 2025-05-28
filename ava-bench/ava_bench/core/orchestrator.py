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