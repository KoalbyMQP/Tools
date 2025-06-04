# ava_bench/benchmarks/mobilenet_v2/benchmark.py

# TODO: make this a more versatile and easily orchastratable test

from pathlib import Path
import time
import os
from typing import Dict, Any
from ..base import UniBench
from ...frameworks import get_framework_adapter

class MobileNetV2(UniBench):
    BENCHMARK_ID = "mobilenet_v2"
    DESCRIPTION = "MobileNetV2 image classification benchmark"
    MODEL_FILENAME = "mobilenet_v2.onnx"
    # FIXME: This should be a repo we maintain ourselves! 
    MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx"
   
    def _download_model(self) -> str:
        models_dir = Path("models")
        models_dir.mkdir(exist_ok=True)
        model_path = models_dir / self.MODEL_FILENAME
        
        if model_path.exists(): return str(model_path)
        
        print(f"Downloading MobileNetV2 model to {model_path}...")
        try:
            import urllib.request
            urllib.request.urlretrieve(self.MODEL_URL, model_path)
            print("✓ Download complete")
            return str(model_path)
        except Exception as e:
            raise RuntimeError(f"Failed to download model: {e}")
    
    def initialize(self) -> bool:
        try:
            self.framework = self.config.get("framework", "onnxruntime")
            self.model_path = self._download_model()
            self.iterations = self.config.get("iterations", 100)
            
            # MobileNetV2 defaults
            self.input_shape = self.config.get("input_shape", [1, 3, 224, 224])
            self.input_dtype = self.config.get("input_dtype", "float32")
            
            self.adapter = get_framework_adapter(self.framework, self.config)
            self.model = self.adapter.load_model(self.model_path)
            self.metadata = self.adapter.get_model_metadata(self.model)
            self.input_data = self.adapter.prepare_input(self.input_shape, self.input_dtype)
            
            return True
        except Exception as e:
            self.error = str(e)
            return False
    
    def test(self) -> Dict[str, Any]:
        # Warmup
        for _ in range(3):
            self.adapter.run_inference(self.model, self.input_data)
        
        # Measure inference times
        times = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            output = self.adapter.run_inference(self.model, self.input_data)
            times.append(time.perf_counter() - start)
        
        # Calculate stats
        mean_time = sum(times) / len(times)
        sorted_times = sorted(times)
        
        return {
            "model_path": self.model_path,
            "framework": self.framework,
            "iterations": self.iterations,
            "input_shape": self.input_shape,
            "output_shape": list(output.shape),
            "mean_inference_ms": mean_time * 1000,
            "min_inference_ms": min(times) * 1000,
            "max_inference_ms": max(times) * 1000,
            "p95_inference_ms": sorted_times[int(len(times) * 0.95)] * 1000,
            "throughput_fps": 1.0 / mean_time,
            "model_metadata": self.metadata
        }
    
    def cleanup(self):
        try:
            if hasattr(self, 'adapter') and hasattr(self, 'model'):
                self.adapter.release_model(self.model)
        except: pass