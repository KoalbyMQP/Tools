# ava_bench/core/sweep.py

# DELETEME: Example config.yaml -> see /example/00_test_things

import itertools
from typing import Dict, List, Any

import yaml

class SweepConfig:
  def __init__(self, config: Dict[str, Any]):
    self.method = config.get('method', 'grid')
    self.parameters = config.get('parameters', {})
  
  @classmethod
  def load(cls, path: str): 
    # TODO: Make this a safer abstraction in utils (we dont want to directly load data in this class!)
    return cls(yaml.safe_load(open(path)))
  
  def generate_combinations(self) -> List[Dict[str, Any]]:
    if self.method == 'grid': return self._grid_search()
    if self.method == 'random': return self._random_search()
    raise ValueError(f"Unknown method: {self.method}")
  
  def _grid_search(self) -> List[Dict[str, Any]]:
    keys, values = [], []
    for k, v in self.parameters.items():
      keys.append(k)
      values.append(v['values'] if 'values' in v else [v['value']])
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]
  
  def _random_search(self) -> List[Dict[str, Any]]:
    # DELETEME: I am actually very sure we wont need this so this currently just lives here!
    count = self.parameters.pop('_count', 10)
    return [self._grid_search()[0] for _ in range(count)]  # simplified

class Sweep:
  def __init__(self, orchestrator):
    self.orchestrator = orchestrator
  
  def run(self, config_path: str):
    config = SweepConfig.load(config_path)
    combinations = config.generate_combinations()
    
    print(f"Running {len(combinations)} combinations...") # DELETEME: debug
    results = []
    
    for i, combo in enumerate(combinations):
      print(f"[{i+1}/{len(combinations)}] {combo}") # DELETEME: debug
      
      # Find benchmark type and create config
      benchmark_id = combo.pop('benchmark', 'simple_math') # FIXME: Handle inccorrect benchmark return better
      bench = self.orchestrator.create_benchmark(benchmark_id, combo)
      
      if bench.initialize():
        result = bench.test()
        bench.cleanup()
        results.append(result)
        print(f"  → {result}")
      else:
        print("  → Failed to initialize")
    
    return results