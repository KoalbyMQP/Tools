import time
import math
from typing import Dict, Any
from ..base import UniBench

class SimpleMathBenchmark(UniBench):
  BENCHMARK_ID = "simple_math"
  DESCRIPTION = "Simple CPU math operations benchmark"
  
  def validate_config(self) -> bool:
    return "iterations" in self.config and self.config["iterations"] > 0
  
  def initialize(self) -> bool:
    self.iterations = self.config.get("iterations", 1000)
    return True
  
  def test(self) -> Dict[str, Any]:
    start_time = time.time()
    result = 0
    
    for i in range(self.iterations):
      result += math.sqrt(i * 3.14159) + math.sin(i) + math.cos(i)
    
    end_time = time.time()
    duration = end_time - start_time
    
    return {
      "duration_seconds": duration,
      "iterations": self.iterations,
      "ops_per_second": self.iterations / duration,
      "final_result": result
    }
  
  def cleanup(self): pass
