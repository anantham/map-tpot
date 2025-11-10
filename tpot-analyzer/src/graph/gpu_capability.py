"""GPU capability detection and configuration.

Detects NVIDIA CUDA availability and RAPIDS cuGraph for accelerated graph metrics.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GpuCapability:
    """Container for GPU hardware and software availability."""

    cuda_available: bool
    cugraph_available: bool
    gpu_count: int
    gpu_name: Optional[str]
    cuda_version: Optional[str]
    driver_version: Optional[str]
    enabled: bool  # Whether GPU metrics are enabled (opt-in)

    @property
    def can_use_gpu(self) -> bool:
        """Check if GPU acceleration is available and enabled."""
        return self.enabled and self.cuda_available and self.cugraph_available

    def __str__(self) -> str:
        """Human-readable status."""
        if self.can_use_gpu:
            return f"GPU enabled ({self.gpu_name}, CUDA {self.cuda_version})"
        elif self.enabled and not self.cuda_available:
            return "GPU requested but CUDA unavailable"
        elif self.enabled and not self.cugraph_available:
            return "GPU requested but cuGraph unavailable"
        else:
            return "GPU disabled (CPU mode)"


def _check_nvidia_smi() -> tuple[bool, int, Optional[str], Optional[str], Optional[str]]:
    """Check NVIDIA GPU via nvidia-smi command.

    Returns:
        (has_gpu, gpu_count, gpu_name, cuda_version, driver_version)
        gpu_name is from the first GPU if multiple are detected
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,cuda_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=2
        )

        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            if lines:
                gpu_count = len(lines)
                # Use first GPU's info for reporting
                parts = lines[0].split(',')
                gpu_name = parts[0].strip() if len(parts) > 0 else None
                driver_version = parts[1].strip() if len(parts) > 1 else None
                cuda_version = parts[2].strip() if len(parts) > 2 else None
                return True, gpu_count, gpu_name, cuda_version, driver_version

    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"nvidia-smi check failed: {e}")

    return False, 0, None, None, None


def _check_numba_cuda() -> bool:
    """Check CUDA availability via numba library."""
    try:
        from numba import cuda
        return cuda.is_available()
    except ImportError:
        return False
    except Exception as e:
        logger.debug(f"numba.cuda check failed: {e}")
        return False


def _check_cugraph() -> bool:
    """Check if RAPIDS cuGraph is available."""
    try:
        import cugraph
        import cudf
        return True
    except ImportError:
        return False
    except Exception as e:
        logger.debug(f"cuGraph import failed: {e}")
        return False


def detect_gpu_capability(force_cpu: bool = False) -> GpuCapability:
    """Detect GPU hardware and software availability.

    Args:
        force_cpu: If True, disable GPU even if available

    Returns:
        GpuCapability dataclass with detection results

    Environment Variables:
        USE_GPU_METRICS: Set to "true" or "1" to enable GPU metrics
        FORCE_CPU_METRICS: Set to "true" or "1" to force CPU mode
    """
    # Check environment flags
    use_gpu = os.getenv("USE_GPU_METRICS", "").lower() in ("true", "1")
    force_cpu_env = os.getenv("FORCE_CPU_METRICS", "").lower() in ("true", "1")

    enabled = use_gpu and not (force_cpu or force_cpu_env)

    if not enabled:
        logger.info("GPU metrics disabled (set USE_GPU_METRICS=true to enable)")
        return GpuCapability(
            cuda_available=False,
            cugraph_available=False,
            gpu_count=0,
            gpu_name=None,
            cuda_version=None,
            driver_version=None,
            enabled=False
        )

    # Check CUDA availability
    cuda_via_smi, gpu_count, gpu_name, cuda_version, driver_version = _check_nvidia_smi()
    cuda_via_numba = _check_numba_cuda()

    cuda_available = cuda_via_smi or cuda_via_numba

    if not cuda_available:
        logger.warning("GPU requested but CUDA not available (check nvidia-smi)")
        return GpuCapability(
            cuda_available=False,
            cugraph_available=False,
            gpu_count=0,
            gpu_name=None,
            cuda_version=None,
            driver_version=None,
            enabled=True
        )

    # Check cuGraph availability
    cugraph_available = _check_cugraph()

    if not cugraph_available:
        logger.warning(
            "GPU requested but cuGraph not available. "
            "Install RAPIDS: conda install -c rapidsai -c conda-forge cugraph"
        )
        return GpuCapability(
            cuda_available=True,
            cugraph_available=False,
            gpu_count=gpu_count if cuda_via_smi else 0,
            gpu_name=gpu_name,
            cuda_version=cuda_version,
            driver_version=driver_version,
            enabled=True
        )

    # Success - GPU fully available
    gpu_info = f"GPU metrics enabled: {gpu_name} (CUDA {cuda_version}, Driver {driver_version})"
    if gpu_count > 1:
        gpu_info += f" - {gpu_count} GPUs detected"
    logger.info(gpu_info)

    return GpuCapability(
        cuda_available=True,
        cugraph_available=True,
        gpu_count=gpu_count,
        gpu_name=gpu_name,
        cuda_version=cuda_version,
        driver_version=driver_version,
        enabled=True
    )


# Global singleton
_gpu_capability: Optional[GpuCapability] = None


def get_gpu_capability(force_cpu: bool = False, refresh: bool = False) -> GpuCapability:
    """Get cached GPU capability detection result.

    Args:
        force_cpu: Force CPU mode
        refresh: Re-run detection instead of using cached result
    """
    global _gpu_capability

    if _gpu_capability is None or refresh:
        _gpu_capability = detect_gpu_capability(force_cpu=force_cpu)

    return _gpu_capability
