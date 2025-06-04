from abc import ABC, abstractmethod
from typing import Dict, Any, List
import numpy as np

__all__ = ["FrameworkAdapter", "get_framework_adapter", "list_frameworks", "get_all_framework_info", "check_framework_availability"]

class FrameworkAdapter(ABC):
    FRAMEWORK_ID: str = ""
    FRAMEWORK_NAME: str = ""
    REQUIRED_PACKAGES: List[str] = []
    MODEL_FILENAME: str = ""
    
    def __init__(self, config: Dict[str, Any]): self.config = config
    
    @abstractmethod
    def is_available(self) -> bool: pass
    @abstractmethod
    def get_detection_info(self) -> Dict[str, Any]: pass
    @abstractmethod
    def load_model(self, model_path: str, **kwargs) -> Any: pass
    @abstractmethod
    def prepare_input(self, shape: List[int], dtype: str = "float32") -> np.ndarray: pass
    @abstractmethod
    def run_inference(self, model: Any, input_data: np.ndarray) -> np.ndarray: pass
    @abstractmethod
    def get_model_metadata(self, model: Any) -> Dict[str, Any]: pass
    @abstractmethod
    def release_model(self, model: Any) -> None: pass
    
    def get_framework_info(self) -> Dict[str, Any]:
        return {"id": self.FRAMEWORK_ID, "name": self.FRAMEWORK_NAME, "required_packages": self.REQUIRED_PACKAGES, "available": self.is_available()}

class ONNXRuntime(FrameworkAdapter):
    FRAMEWORK_ID = "onnxruntime"
    FRAMEWORK_NAME = "ONNX Runtime"
    REQUIRED_PACKAGES = ["onnxruntime"]
    
    def is_available(self) -> bool:
        try:
            import onnxruntime as ort
            ort.get_available_providers()
            return True
        except: return False
    
    def get_detection_info(self) -> Dict[str, Any]:
        info = {"framework_id": self.FRAMEWORK_ID, "available": False, "version": None, "error": None, 
                "install_suggestion": "pip install onnxruntime>=1.20.1", "providers": [], "device_support": {}}
        
        try:
            import onnxruntime as ort
            info["version"] = ort.__version__
            providers = ort.get_available_providers()
            info["providers"] = providers
            info["device_support"] = {"cpu": "CPUExecutionProvider" in providers, "gpu": "CUDAExecutionProvider" in providers,
                                    "directml": "DmlExecutionProvider" in providers, "coreml": "CoreMLExecutionProvider" in providers}
            info["available"] = True
        except ImportError as e: info["error"] = f"Import failed: {str(e)}"
        except Exception as e: info["error"] = f"ONNX Runtime check failed: {str(e)}"
        
        return info
    
    def load_model(self, model_path: str, **kwargs) -> Any:
        try:
            import onnxruntime as ort
            onnx_config = self.config.get('onnxruntime', {})
            session_options = ort.SessionOptions()
            
            if 'inter_op_num_threads' in onnx_config: session_options.inter_op_num_threads = onnx_config['inter_op_num_threads']
            if 'intra_op_num_threads' in onnx_config: session_options.intra_op_num_threads = onnx_config['intra_op_num_threads']
            
            optimization_level = onnx_config.get('optimization_level', 'all')
            opt_map = {'all': ort.GraphOptimizationLevel.ORT_ENABLE_ALL, 'basic': ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
                      'extended': ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED}
            session_options.graph_optimization_level = opt_map.get(optimization_level, ort.GraphOptimizationLevel.ORT_DISABLE_ALL)
            
            providers = onnx_config.get('providers', ['CPUExecutionProvider'])
            return ort.InferenceSession(model_path, sess_options=session_options, providers=providers)
            
        except ImportError: raise RuntimeError("ONNX Runtime not available. Install with: pip install onnxruntime")
        except Exception as e: raise RuntimeError(f"Failed to load ONNX model '{model_path}': {str(e)}")
    
    def prepare_input(self, shape: List[int], dtype: str = "float32") -> np.ndarray:
        try:
            np_dtype = getattr(np, dtype)
            if dtype.startswith('float'): return np.random.random(shape).astype(np_dtype)
            elif dtype.startswith('int'): return np.random.randint(0, 255, shape, dtype=np_dtype)
            else: return np.random.random(shape).astype(np_dtype)
        except Exception as e: raise RuntimeError(f"Failed to prepare input tensor: {str(e)}")
    
    def run_inference(self, model: Any, input_data: np.ndarray) -> np.ndarray:
        try:
            input_name = model.get_inputs()[0].name
            result = model.run(None, {input_name: input_data})
            return result[0]
        except Exception as e: raise RuntimeError(f"Inference failed: {str(e)}")
    
    def get_model_metadata(self, model: Any) -> Dict[str, Any]:
        try:
            inputs, outputs = model.get_inputs(), model.get_outputs()
            metadata = {"input_count": len(inputs), "output_count": len(outputs), "inputs": [], "outputs": []}
            
            for inp in inputs: metadata["inputs"].append({"name": inp.name, "shape": inp.shape, "dtype": inp.type})
            for out in outputs: metadata["outputs"].append({"name": out.name, "shape": out.shape, "dtype": out.type})
            
            if len(inputs) == 1: metadata.update({"input_shape": inputs[0].shape, "input_dtype": inputs[0].type, "input_name": inputs[0].name})
            if len(outputs) == 1: metadata.update({"output_shape": outputs[0].shape, "output_dtype": outputs[0].type, "output_name": outputs[0].name})
            
            return metadata
        except Exception as e: raise RuntimeError(f"Failed to extract model metadata: {str(e)}")
    
    def release_model(self, model: Any) -> None:
        if hasattr(model, 'end_profiling'):
            try: model.end_profiling()
            except: pass

_FRAMEWORKS = {"onnxruntime": ONNXRuntime}

def get_framework_adapter(framework_id: str, config: dict) -> FrameworkAdapter:
    if framework_id not in _FRAMEWORKS:
        raise ValueError(f"Unknown framework '{framework_id}'. Available: {list(_FRAMEWORKS.keys())}")
    return _FRAMEWORKS[framework_id](config)

def list_frameworks() -> List[str]: return list(_FRAMEWORKS.keys())

def get_all_framework_info() -> Dict[str, Dict[str, Any]]:
    return {fid: cls({}).get_detection_info() for fid, cls in _FRAMEWORKS.items()}

def check_framework_availability(framework_id: str) -> bool:
    return framework_id in _FRAMEWORKS and _FRAMEWORKS[framework_id]({}).is_available()