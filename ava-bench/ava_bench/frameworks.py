# ava_bench/frameworks.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List

__all__ = [
    "FrameworkAdapter",
    "get_framework_adapter",
    "list_frameworks", 
    "get_all_framework_info",
    "check_framework_availability"
]

class FrameworkAdapter(ABC):
    FRAMEWORK_ID: str = ""
    FRAMEWORK_NAME: str = ""
    REQUIRED_PACKAGES: List[str] = []
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if framework is available"""
        pass
    
    @abstractmethod
    def get_detection_info(self) -> Dict[str, Any]:
        """Get detailed availability information for debugging"""
        pass
    
    def get_framework_info(self) -> Dict[str, Any]:
        """Get basic framework metadata"""
        return {
            "id": self.FRAMEWORK_ID,
            "name": self.FRAMEWORK_NAME,
            "required_packages": self.REQUIRED_PACKAGES,
            "available": self.is_available()
        }

class ONNXRuntimeAdapter(FrameworkAdapter):
    """ONNX Runtime framework adapter - universal inference engine"""
    
    FRAMEWORK_ID = "onnxruntime"
    FRAMEWORK_NAME = "ONNX Runtime"
    REQUIRED_PACKAGES = ["onnxruntime"]
    
    def is_available(self) -> bool:
        """Check ONNX Runtime availability - never raises exceptions"""
        try:
            import onnxruntime as ort
            # Test basic functionality
            ort.get_available_providers()
            return True
        except ImportError:
            return False
        except Exception:
            return False
    
    def get_detection_info(self) -> Dict[str, Any]:
        """Get detailed ONNX Runtime detection information"""
        info = {
            "framework_id": self.FRAMEWORK_ID,
            "available": False,
            "version": None,
            "error": None,
            "install_suggestion": "pip install onnxruntime>=1.20.1",
            "providers": [],
            "device_support": {}
        }
        
        try:
            import onnxruntime as ort
            info["version"] = ort.__version__
            
            # Get available execution providers
            providers = ort.get_available_providers()
            info["providers"] = providers
            
            # Check device support
            info["device_support"] = {
                "cpu": "CPUExecutionProvider" in providers,
                "gpu": "CUDAExecutionProvider" in providers,
                "directml": "DmlExecutionProvider" in providers,
                "coreml": "CoreMLExecutionProvider" in providers
            }
            
            info["available"] = True
            info["error"] = None
            
        except ImportError as e:
            info["error"] = f"Import failed: {str(e)}"
        except Exception as e:
            info["error"] = f"ONNX Runtime check failed: {str(e)}"
        
        return info

_FRAMEWORKS = {
    "onnxruntime": ONNXRuntimeAdapter,
}

def get_framework_adapter(framework_id: str, config: dict) -> FrameworkAdapter:
    """Get framework adapter by ID - explicit lookup, clear errors"""
    if framework_id not in _FRAMEWORKS:
        available = list(_FRAMEWORKS.keys())
        raise ValueError(f"Unknown framework '{framework_id}'. Available: {available}")
    
    adapter_class = _FRAMEWORKS[framework_id]
    return adapter_class(config)

def list_frameworks() -> List[str]:
    """List all registered frameworks"""
    return list(_FRAMEWORKS.keys())

def get_all_framework_info() -> Dict[str, Dict[str, Any]]:
    """Get detection info for all frameworks"""
    info = {}
    for framework_id, adapter_class in _FRAMEWORKS.items():
        temp_adapter = adapter_class({})
        info[framework_id] = temp_adapter.get_detection_info()
    return info

def check_framework_availability(framework_id: str) -> bool:
    """Quick check if specific framework is available"""
    if framework_id not in _FRAMEWORKS:
        return False
    
    adapter_class = _FRAMEWORKS[framework_id]
    temp_adapter = adapter_class({})
    return temp_adapter.is_available()