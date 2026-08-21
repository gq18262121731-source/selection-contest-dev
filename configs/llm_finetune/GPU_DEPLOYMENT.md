# GPU LLaMA-Factory Deployment

This project uses `Dockerfile.llamafactory-rtx50-cu128` for the GPU fine-tuning stack.

Verified on the current machine:

- GPU: NVIDIA GeForce RTX 5060 Laptop GPU
- Driver: 577.03
- Container torch: `2.11.0+cu128`
- CUDA tensor execution: passed
- LLaMA-Factory: available
- Liger Kernel: available

Known limits:

- The default `health-llamafactory-gpu` image is the stable RTX 50/cu128 training image.
- The optional `health-llamafactory-gpu-devel` image adds CUDA compile tooling (`nvcc`) and is the place to enable DeepSpeed, FlashAttention, vLLM or Unsloth.
- FlashAttention, vLLM and Unsloth remain opt-in because they can pull large dependency graphs or compile CUDA extensions.

Run:

```powershell
.\scripts\start_llamafactory_gpu_stack.ps1 -Build
```

Run the CUDA devel image:

```powershell
.\scripts\start_llamafactory_devel_stack.ps1 -Build
```

Open:

- GPU WebUI: `http://127.0.0.1:7861`
- GPU Devel WebUI: `http://127.0.0.1:7862`
- Existing native WebUI: `http://127.0.0.1:7860`

Validate:

```powershell
.\scripts\model_tuning_capabilities.ps1
.\scripts\verify_llamafactory_gpu_images.ps1
```
