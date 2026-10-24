"""
Centralized System & Hardware Resource Manager for SANTRA.
Provides thread-safe, non-blocking telemetry for CPU, RAM, and NVIDIA GPU acceleration.
Distinguishes process-level resources from system-wide metrics and manages
verified hardware capability detection, workload routing policies, and profile states.
"""

import os
import sys
import time
import ctypes
import logging
import threading
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Callable, List

import psutil

logger = logging.getLogger("Jarvis.ResourceManager")

# ==========================================
# RESOURCE DATA STRUCTURES
# ==========================================

@dataclass
class ResourceSnapshot:
    """Thread-safe snapshot of system and process resource metrics."""
    timestamp: float
    # Process Metrics (Santra specific)
    process_pid: int
    process_cpu_pct: float
    process_rss_mb: float
    process_vms_mb: float
    # System-wide CPU & RAM Metrics
    system_cpu_pct: float
    system_ram_total_mb: float
    system_ram_used_mb: float
    system_ram_available_mb: float
    system_ram_percent: float
    # NVIDIA GPU Telemetry (System-wide & Hardware)
    gpu_available: bool
    gpu_name: str
    gpu_driver_version: str
    gpu_utilization_pct: Optional[float]
    gpu_mem_total_mb: Optional[float]
    gpu_mem_used_mb: Optional[float]
    gpu_mem_free_mb: Optional[float]
    gpu_temp_c: Optional[float]
    gpu_power_w: Optional[float]
    # Execution & Workload Context
    profile_state: str           # "STANDBY", "ACTIVE", "PROCESSING", "SLEEPING"
    current_task: str            # e.g., "Idle / Standby", "Transcribing Speech", "Synthesizing Voice"
    current_model: str           # e.g., "faster-whisper-base", "edge-tts", "none"
    inference_device: str        # e.g., "CPU (int8)", "CUDA (RTX 3050)"
    acceleration_status: str     # "VERIFIED_CUDA", "VERIFIED_CPU_FALLBACK", "UNAVAILABLE"
    diagnostic_message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==========================================
# DIRECT WINDOWS NVML CTYPES TELEMETRY
# ==========================================

class _NVMLUtilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

class _NVMLMemory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class NvmlTelemetry:
    """Zero-dependency, in-process telemetry using Windows native nvml.dll via ctypes.
    Executes in <0.1ms without creating external subprocesses or blocking Qt UI threads.
    """

    def __init__(self):
        self.is_initialized = False
        self._nvml = None
        self._device_handle = None
        self.gpu_name = "N/A"
        self.driver_version = "N/A"
        self.total_vram_mb = 0.0
        self._init_nvml()

    def _init_nvml(self):
        if sys.platform != "win32":
            return
        try:
            # nvml.dll is present in System32 / DriverStore on Windows systems with NVIDIA drivers
            self._nvml = ctypes.CDLL("nvml.dll")
            if self._nvml.nvmlInit_v2() == 0:
                dev_count = ctypes.c_uint()
                self._nvml.nvmlDeviceGetCount_v2(ctypes.byref(dev_count))
                if dev_count.value > 0:
                    handle = ctypes.c_void_p()
                    if self._nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                        self._device_handle = handle
                        # Query device name
                        name_buf = ctypes.create_string_buffer(96)
                        if self._nvml.nvmlDeviceGetName(handle, name_buf, 96) == 0:
                            self.gpu_name = name_buf.value.decode("utf-8", errors="ignore").strip()
                        # Query driver version
                        ver_buf = ctypes.create_string_buffer(64)
                        if self._nvml.nvmlSystemGetDriverVersion(ver_buf, 64) == 0:
                            self.driver_version = ver_buf.value.decode("utf-8", errors="ignore").strip()
                        # Query total VRAM
                        mem = _NVMLMemory()
                        if self._nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == 0:
                            self.total_vram_mb = round(mem.total / (1024 * 1024), 1)

                        self.is_initialized = True
                        logger.info(f"[NVML] Initialized GPU: {self.gpu_name} (Driver: {self.driver_version}, VRAM: {self.total_vram_mb} MB)")
        except Exception as e:
            logger.debug(f"[NVML] Native NVML telemetry unavailable: {e}")
            self.is_initialized = False

    def query_metrics(self) -> Dict[str, Any]:
        """Queries instant hardware metrics in <0.1ms."""
        if not self.is_initialized or not self._device_handle:
            return {
                "available": False,
                "name": "N/A",
                "driver": "N/A",
                "utilization_pct": None,
                "mem_total_mb": None,
                "mem_used_mb": None,
                "mem_free_mb": None,
                "temp_c": None,
                "power_w": None
            }

        try:
            # 1. Utilization
            util = _NVMLUtilization()
            gpu_util = None
            if self._nvml.nvmlDeviceGetUtilizationRates(self._device_handle, ctypes.byref(util)) == 0:
                gpu_util = float(util.gpu)

            # 2. VRAM
            mem = _NVMLMemory()
            mem_used_mb = None
            mem_free_mb = None
            if self._nvml.nvmlDeviceGetMemoryInfo(self._device_handle, ctypes.byref(mem)) == 0:
                mem_used_mb = round(mem.used / (1024 * 1024), 1)
                mem_free_mb = round(mem.free / (1024 * 1024), 1)

            # 3. Temperature
            temp = ctypes.c_uint()
            temp_c = None
            if self._nvml.nvmlDeviceGetTemperature(self._device_handle, 0, ctypes.byref(temp)) == 0:
                temp_c = float(temp.value)

            # 4. Power
            power = ctypes.c_uint()
            power_w = None
            try:
                if self._nvml.nvmlDeviceGetPowerUsage(self._device_handle, ctypes.byref(power)) == 0:
                    power_w = round(power.value / 1000.0, 2)
            except Exception:
                pass

            return {
                "available": True,
                "name": self.gpu_name,
                "driver": self.driver_version,
                "utilization_pct": gpu_util,
                "mem_total_mb": self.total_vram_mb,
                "mem_used_mb": mem_used_mb,
                "mem_free_mb": mem_free_mb,
                "temp_c": temp_c,
                "power_w": power_w
            }
        except Exception as e:
            logger.debug(f"[NVML] Failed reading GPU metrics: {e}")
            return {
                "available": False,
                "name": self.gpu_name,
                "driver": self.driver_version,
                "utilization_pct": None,
                "mem_total_mb": self.total_vram_mb,
                "mem_used_mb": None,
                "mem_free_mb": None,
                "temp_c": None,
                "power_w": None
            }

    def shutdown(self):
        if self.is_initialized and self._nvml:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self.is_initialized = False


# ==========================================
# HARDWARE CAPABILITY DETECTOR
# ==========================================

class HardwareCapabilityDetector:
    """Probes NVIDIA GPU hardware, CUDA backends, CTranslate2, PyTorch, and ONNX Runtime.
    Performs verified, bounded sandbox smoke tests to prevent unhandled runtime crashes.
    """

    def __init__(self, nvml_telemetry: NvmlTelemetry):
        self.nvml = nvml_telemetry
        self._probe_results: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

    def get_capabilities(self, force_refresh: bool = False) -> Dict[str, Any]:
        with self._lock:
            if self._probe_results is not None and not force_refresh:
                return self._probe_results

            logger.info("[CAPABILITY_DETECTOR] Auditing hardware acceleration capabilities...")
            results = {
                "hardware_gpu_detected": self.nvml.is_initialized,
                "gpu_name": self.nvml.gpu_name if self.nvml.is_initialized else "None",
                "gpu_driver": self.nvml.driver_version if self.nvml.is_initialized else "None",
                "gpu_total_vram_mb": self.nvml.total_vram_mb,
                "ctranslate2_installed": False,
                "ctranslate2_version": "N/A",
                "ctranslate2_cuda_count": 0,
                "ctranslate2_cuda_verified": False,
                "torch_installed": False,
                "torch_cuda_available": False,
                "onnxruntime_providers": [],
                "recommended_stt_device": "cpu",
                "recommended_stt_compute": "int8",
                "status_message": ""
            }

            # 1. Audit CTranslate2
            try:
                import ctranslate2
                results["ctranslate2_installed"] = True
                results["ctranslate2_version"] = getattr(ctranslate2, "__version__", "unknown")
                cuda_count = ctranslate2.get_cuda_device_count()
                results["ctranslate2_cuda_count"] = cuda_count

                if cuda_count > 0:
                    # Run small, bounded smoke test to verify if CUDA runtime libraries (cublas64_12.dll) exist
                    is_verified, reason = self._verify_ctranslate2_cuda()
                    results["ctranslate2_cuda_verified"] = is_verified
                    if not is_verified:
                        results["cuda_failure_reason"] = reason
                        logger.warning(f"[CAPABILITY_DETECTOR] CTranslate2 reports CUDA device count {cuda_count}, but CUDA smoke test failed: {reason}")
                else:
                    results["ctranslate2_cuda_verified"] = False
                    results["cuda_failure_reason"] = "No CUDA devices reported by CTranslate2."
            except Exception as ce:
                results["ctranslate2_cuda_verified"] = False
                results["cuda_failure_reason"] = f"CTranslate2 audit failed: {ce}"

            # 2. Audit PyTorch
            try:
                import torch
                results["torch_installed"] = True
                results["torch_cuda_available"] = torch.cuda.is_available()
            except ImportError:
                results["torch_installed"] = False
                results["torch_cuda_available"] = False

            # 3. Audit ONNX Runtime
            try:
                import onnxruntime as ort
                results["onnxruntime_providers"] = ort.get_available_providers()
            except Exception:
                results["onnxruntime_providers"] = []

            # 4. Formulate Recommended Workload Routing
            if results["ctranslate2_cuda_verified"]:
                results["recommended_stt_device"] = "cuda"
                results["recommended_stt_compute"] = "float16"
                results["status_message"] = f"Verified CUDA acceleration active on {results['gpu_name']}."
            else:
                results["recommended_stt_device"] = "cpu"
                results["recommended_stt_compute"] = "int8"
                if results["hardware_gpu_detected"]:
                    reason = results.get("cuda_failure_reason", "CUDA runtime library missing")
                    results["status_message"] = f"{results['gpu_name']} detected. CUDA backend unavailable ({reason}); safely routed to CPU (int8)."
                else:
                    results["status_message"] = "Standard CPU execution (int8)."

            logger.info(f"[CAPABILITY_DETECTOR] Routing Policy: {results['status_message']}")
            self._probe_results = results
            return results

    def _verify_ctranslate2_cuda(self) -> (bool, str):
        """Runs a tiny, bounded smoke test on CTranslate2 CUDA matrix multiplication.
        Returns (True, '') if working, or (False, error_reason) without crashing.
        """
        try:
            import ctranslate2
            import numpy as np

            # Fast test: check if ctranslate2 can create a dummy storage or run a tiny model
            # To avoid model downloading, we test if CUDA runtime libraries (cublas64_12.dll) can be linked
            # or try a minimal WhisperModel on CUDA with local_files_only
            from faster_whisper import WhisperModel
            test_model = WhisperModel("tiny.en", device="cuda", compute_type="float16", local_files_only=True)
            # Create a 0.1s dummy audio buffer
            dummy_audio = np.zeros(1600, dtype=np.float32)
            segments, info = test_model.transcribe(dummy_audio, beam_size=1)
            # Iterate generator to force actual CUDA encoder matrix multiplication
            for _ in segments:
                break
            return True, ""
        except FileNotFoundError:
            # Model file not in local cache; cannot verify CUDA without downloading
            return False, "Tiny model not cached for CUDA verification"
        except RuntimeError as re:
            err = str(re)
            if "cublas64" in err or "cannot be loaded" in err or "not found" in err:
                return False, "cublas64_12.dll missing"
            if "out of memory" in err.lower():
                return False, "CUDA out of memory"
            return False, err
        except Exception as e:
            return False, str(e)


# ==========================================
# CENTRAL RESOURCE MANAGER SERVICE
# ==========================================

class SystemResourceManager:
    """Thread-safe, singleton background service monitoring CPU, RAM, and GPU telemetry.
    Maintains a low-frequency non-blocking background loop and serves instant snapshots to UI.
    """

    _instance: Optional["SystemResourceManager"] = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SystemResourceManager":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._process = psutil.Process(os.getpid())
        self.nvml = NvmlTelemetry()
        self.capability_detector = HardwareCapabilityDetector(self.nvml)
        self.capabilities = self.capability_detector.get_capabilities()

        # Operational state
        self._profile_state = "STANDBY"
        self._current_task = "Standing by for wake word"
        self._current_model = "None (Idle)"
        self._inference_device = f"{self.capabilities['recommended_stt_device'].upper()} ({self.capabilities['recommended_stt_compute']})"
        self._acceleration_status = (
            "VERIFIED_CUDA" if self.capabilities["ctranslate2_cuda_verified"]
            else "VERIFIED_CPU_FALLBACK" if self.capabilities["hardware_gpu_detected"]
            else "UNAVAILABLE"
        )
        self._sampling_interval_sec = 2.0  # 2.0s in active/standby, 5.0s in sleeping

        # Cached initial snapshot
        self._cached_snapshot: ResourceSnapshot = self._sample_snapshot()

    def start(self):
        """Starts the low-overhead background telemetry loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._monitor_loop,
                name="SantraResourceMonitor",
                daemon=True
            )
            self._worker_thread.start()
            logger.info(f"[RESOURCE_MANAGER] Background resource monitor started (interval={self._sampling_interval_sec}s).")

    def stop(self):
        """Stops the telemetry monitor cleanly."""
        with self._lock:
            self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self.nvml.shutdown()
        logger.info("[RESOURCE_MANAGER] Resource monitor stopped cleanly.")

    def set_profile(self, state: str):
        """Switches runtime profile: 'STANDBY', 'ACTIVE', 'PROCESSING', 'SLEEPING'."""
        with self._lock:
            self._profile_state = state
            if state == "SLEEPING":
                self._sampling_interval_sec = 5.0  # Conserve power during sleep
                self._current_task = "Sleeping (Low power wake detection)"
            elif state == "PROCESSING":
                self._sampling_interval_sec = 1.0  # Responsive during active compute
            else:
                self._sampling_interval_sec = 2.0
        logger.debug(f"[RESOURCE_MANAGER] Profile switched to '{state}', sampling={self._sampling_interval_sec}s")

    def update_task_context(self, task: str, model: str = None, device: str = None):
        """Updates the active task and model context for HUD and telemetry."""
        with self._lock:
            self._current_task = task
            if model:
                self._current_model = model
            if device:
                self._inference_device = device

    def get_snapshot(self) -> ResourceSnapshot:
        """Returns the latest cached snapshot instantly without blocking."""
        with self._lock:
            return self._cached_snapshot

    def _sample_snapshot(self) -> ResourceSnapshot:
        """Performs a single lightweight sampling pass."""
        now = time.time()
        pid = self._process.pid

        # 1. Process CPU & RAM
        try:
            proc_cpu = self._process.cpu_percent()
            mem_info = self._process.memory_info()
            proc_rss = round(mem_info.rss / (1024 * 1024), 1)
            proc_vms = round(mem_info.vms / (1024 * 1024), 1)
        except Exception:
            proc_cpu = 0.0
            proc_rss = 0.0
            proc_vms = 0.0

        # 2. System CPU & RAM
        try:
            sys_cpu = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            sys_ram_total = round(vm.total / (1024 * 1024), 1)
            sys_ram_used = round(vm.used / (1024 * 1024), 1)
            sys_ram_avail = round(vm.available / (1024 * 1024), 1)
            sys_ram_pct = vm.percent
        except Exception:
            sys_cpu = 0.0
            sys_ram_total = 0.0
            sys_ram_used = 0.0
            sys_ram_avail = 0.0
            sys_ram_pct = 0.0

        # 3. GPU Telemetry
        gpu_data = self.nvml.query_metrics()

        return ResourceSnapshot(
            timestamp=now,
            process_pid=pid,
            process_cpu_pct=proc_cpu,
            process_rss_mb=proc_rss,
            process_vms_mb=proc_vms,
            system_cpu_pct=sys_cpu,
            system_ram_total_mb=sys_ram_total,
            system_ram_used_mb=sys_ram_used,
            system_ram_available_mb=sys_ram_avail,
            system_ram_percent=sys_ram_pct,
            gpu_available=gpu_data["available"],
            gpu_name=gpu_data["name"],
            gpu_driver_version=gpu_data["driver"],
            gpu_utilization_pct=gpu_data["utilization_pct"],
            gpu_mem_total_mb=gpu_data["mem_total_mb"],
            gpu_mem_used_mb=gpu_data["mem_used_mb"],
            gpu_mem_free_mb=gpu_data["mem_free_mb"],
            gpu_temp_c=gpu_data["temp_c"],
            gpu_power_w=gpu_data["power_w"],
            profile_state=self._profile_state,
            current_task=self._current_task,
            current_model=self._current_model,
            inference_device=self._inference_device,
            acceleration_status=self._acceleration_status,
            diagnostic_message=self.capabilities.get("status_message", "")
        )

    def _monitor_loop(self):
        """Worker loop sampling resources periodically."""
        # Initial cpu_percent measurement prime
        try:
            self._process.cpu_percent()
            psutil.cpu_percent()
        except Exception:
            pass

        while self._running:
            try:
                snapshot = self._sample_snapshot()
                with self._lock:
                    self._cached_snapshot = snapshot
                    interval = self._sampling_interval_sec

                time.sleep(interval)
            except Exception as e:
                logger.debug(f"[RESOURCE_MONITOR] Sampling exception: {e}")
                time.sleep(2.0)


# Global singleton accessor
system_resource_manager = SystemResourceManager.get_instance()
