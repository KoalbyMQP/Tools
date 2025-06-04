from .simple_math import SimpleMathBenchmark
from .mobilenet_v2 import MobileNetV2

BENCHMARKS = {
  "simple_math": SimpleMathBenchmark,
  "mobilenet_v2": MobileNetV2,
}
