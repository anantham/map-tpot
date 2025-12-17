# GPU Acceleration Setup Guide

This guide explains how to enable NVIDIA GPU acceleration for graph metrics using RAPIDS cuGraph.

## Performance Gains

With GPU acceleration on an NVIDIA RTX 4060 (70,845 nodes, 226,123 edges):

| Metric | CPU (NetworkX) | CPU (NetworKit) | GPU (cuGraph) | GPU Speedup |
|--------|----------------|-----------------|---------------|-------------|
| PageRank | 30-60s | 10-20s | **5-10s** | **3-6x** |
| Betweenness (exact) | 30-60 min | 2-5 min | **30-90s** | **20-40x** |
| Betweenness (k=500) | 2-3 min | 30-60s | **10-20s** | **6-12x** |
| Louvain | 30-60s | N/A | **10-20s** | **2-3x** |
| Closeness | 1-2 min | 10-20s | **5-15s** | **8-12x** |

## System Requirements

### Hardware
- **NVIDIA GPU**: RTX 20xx series or newer recommended
- **GPU Memory**: 4GB+ for 70k node graphs, 8GB+ for 200k+ nodes
- **System RAM**: 16GB+ recommended

### Software
- **OS**: Linux (Ubuntu 20.04+) or WSL2 on Windows
- **CUDA**: 11.2+ or 12.0+ (check with `nvidia-smi`)
- **Driver**: NVIDIA driver 470+ (for CUDA 11.2) or 525+ (for CUDA 12.0)
- **Python**: 3.9, 3.10, or 3.11 (RAPIDS doesn't support 3.12 yet)

### Verify CUDA Installation

```bash
# Check NVIDIA driver and CUDA version
nvidia-smi

# Expected output:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.xx       Driver Version: 535.xx       CUDA Version: 12.2   |
# +-----------------------------------------------------------------------------+
```

## Installation

### Option 1: Conda (Recommended)

RAPIDS is best installed via conda to ensure all dependencies match:

```bash
# Create new environment with Python 3.10
conda create -n tpot-gpu python=3.10
conda activate tpot-gpu

# Install RAPIDS cuGraph + cuDF (CUDA 11.8)
conda install -c rapidsai -c conda-forge -c nvidia \
    cugraph=24.02 cudf=24.02 python=3.10 cudatoolkit=11.8

# For CUDA 12.x:
conda install -c rapidsai -c conda-forge -c nvidia \
    cugraph=24.02 cudf=24.02 python=3.10 'cuda-version>=12.0,<13.0a0'

# Install project dependencies
pip install -r requirements.txt

# Verify installation
python -c "import cugraph, cudf; print('cuGraph installed successfully')"
```

### Option 2: Pip (Advanced)

Pip wheels are available but may have compatibility issues:

```bash
pip install cudf-cu11 cugraph-cu11  # For CUDA 11.x
# or
pip install cudf-cu12 cugraph-cu12  # For CUDA 12.x
```

See [RAPIDS Installation Guide](https://docs.rapids.ai/install) for latest instructions.

### WSL2 on Windows

1. Install WSL2 with Ubuntu 22.04
2. Install NVIDIA driver **on Windows** (not in WSL)
3. Verify CUDA is accessible: `nvidia-smi` should work in WSL
4. Follow conda installation above

## Enabling GPU Metrics

### Environment Variables

Set these before running scripts or starting the API:

```bash
# Enable GPU acceleration
export USE_GPU_METRICS=true

# Force CPU mode (disable GPU)
export FORCE_CPU_METRICS=true

# Prefer NetworKit over GPU (for testing)
export PREFER_NETWORKIT=true
```

### Usage in Scripts

```bash
# Refresh snapshot with GPU acceleration
USE_GPU_METRICS=true python -m scripts.refresh_graph_snapshot --include-shadow

# Benchmark CPU vs GPU
python -m scripts.benchmark_metrics --include-shadow --test-gpu

# Verify GPU detection
python -c "from src.graph.gpu_capability import get_gpu_capability; print(get_gpu_capability())"
```

### API Server with GPU

```bash
# Start API with GPU enabled
USE_GPU_METRICS=true python -m scripts.start_api_server

# API responses include backend info:
# {
#   "metrics": {...},
#   "_backend": "gpu",
#   "_backend_details": {
#     "pagerank": "gpu",
#     "betweenness": "gpu",
#     "communities": "gpu"
#   }
# }
```

### Per-Request GPU Control

```python
# Force CPU for a specific request
POST /api/metrics/compute
{
  "seeds": [...],
  "use_gpu": false  # Override GPU setting
}
```

## Routing Logic

The dispatcher automatically selects the best backend:

```
1. GPU (cuGraph)    - if USE_GPU_METRICS=true and GPU available
2. NetworKit (C++)  - if available and graph > 100 nodes
3. NetworkX (Python) - fallback
```

To force a specific backend:
- `USE_GPU_METRICS=true` + `FORCE_CPU_METRICS=false` → GPU
- `PREFER_NETWORKIT=true` → NetworKit over GPU
- `FORCE_CPU_METRICS=true` → NetworkX only

## Troubleshooting

### "CUDA not available"

```bash
# Check driver
nvidia-smi

# Check CUDA runtime
nvcc --version  # Should match driver CUDA version

# Reinstall RAPIDS with correct CUDA version
conda install -c rapidsai -c conda-forge cugraph cudatoolkit=11.8
```

### "cuGraph import failed"

```bash
# Check Python version (must be 3.9-3.11)
python --version

# Reinstall with matching versions
conda install -c rapidsai -c conda-forge cugraph=24.02 python=3.10
```

### "Out of GPU memory"

Reduce graph size or use sampling:
```python
# Compute betweenness with sampling
betweenness = compute_betweenness_gpu(graph, k=200)  # Sample 200 nodes instead of all
```

### WSL2: "GPU not detected"

1. Ensure NVIDIA driver installed **on Windows** (not WSL)
2. Update WSL: `wsl --update`
3. Check: `nvidia-smi` should work in WSL terminal

### Performance worse than CPU

- **Small graphs** (<1000 nodes): GPU overhead > speedup, use CPU
- **Data transfer**: Ensure graphs are large enough to amortize GPU copy cost
- **Sampling**: GPU shines on exact algorithms, sampling reduces GPU advantage

## Benchmarking

Compare performance across backends:

```bash
# Quick benchmark (PageRank + Betweenness)
python -m scripts.benchmark_metrics --include-shadow --test-gpu

# Expected output on RTX 4060:
# pagerank_networkx              :    45.21s
# pagerank_networkit             :    15.32s
# pagerank_gpu                   :     8.45s  # 5.3x faster
# betweenness_networkx_sampled   :   142.15s
# betweenness_networkit_sampled  :    48.32s
# betweenness_gpu_sampled        :    18.76s  # 7.6x faster
```

## Best Practices

1. **Use GPU for snapshot generation** - One-time cost, benefits all API requests
   ```bash
   USE_GPU_METRICS=true python -m scripts.enrich_shadow_graph --refresh-snapshot
   ```

2. **Keep GPU warm** - First call has overhead (~2s), subsequent calls are fast

3. **Batch computations** - Use `compute_all_metrics()` instead of individual calls

4. **Monitor GPU usage**:
   ```bash
   watch -n 1 nvidia-smi  # Real-time GPU monitoring
   ```

5. **Profile to verify**:
   ```bash
   python -m scripts.profile_graph_rendering --include-shadow --verbose
   ```

## Advanced: Multi-GPU

For systems with multiple GPUs:

```python
import cudf
cudf.set_option("default_device", 0)  # Use GPU 0
cudf.set_option("default_device", 1)  # Use GPU 1
```

## References

- [RAPIDS Documentation](https://docs.rapids.ai/)
- [cuGraph API Reference](https://docs.rapids.ai/api/cugraph/stable/)
- [RAPIDS Installation](https://rapids.ai/start.html)
- [WSL2 + CUDA Setup](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)

## Next Steps

After GPU setup:
1. Run benchmark: `python -m scripts.benchmark_metrics --test-gpu`
2. Regenerate snapshot: `USE_GPU_METRICS=true python -m scripts.refresh_graph_snapshot --include-shadow`
3. Verify: `python -m scripts.verify_graph_snapshot`
4. Restart API: `USE_GPU_METRICS=true python -m scripts.start_api_server`
