from abc import ABC, abstractmethod
from typing import Dict, Any, List

class UniBench(ABC):
  BENCHMARK_ID: str = ""
  DESCRIPTION: str = ""
  
  def __init__(self, config: Dict[str, Any]):
    self.config = config
  
  @abstractmethod
  def initialize(self) -> bool: pass
  
  @abstractmethod
  def test(self) -> Dict[str, Any]: pass
  
  @abstractmethod
  def cleanup(self): pass
  
  def validate_config(self) -> bool: return True
