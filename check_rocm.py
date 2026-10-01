#!/usr/bin/env python3
"""Check native ROCm device access and the FP32 operations used by DA3."""
import json
import os


def check():
    import torch
    import torch.nn.functional as F

    if os.environ.get('HSA_OVERRIDE_GFX_VERSION'):
        raise RuntimeError('Unset HSA_OVERRIDE_GFX_VERSION; use a native gfx1150 PyTorch build.')
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('ROCm PyTorch and access to /dev/kfd and /dev/dri are required.')
    properties = torch.cuda.get_device_properties(0)
    # Device discovery alone does not prove rocBLAS/SDPA kernels support the GPU.
    with torch.inference_mode():
        x = torch.linspace(-1, 1, 1024).reshape(32, 32)
        gpu = x.cuda()
        torch.testing.assert_close((gpu @ gpu.T).cpu(), x @ x.T, rtol=1e-4, atol=1e-4)
        q = gpu.reshape(1, 2, 16, 32)
        actual = F.scaled_dot_product_attention(q, q, q).cpu()
        reference = F.scaled_dot_product_attention(q.cpu(), q.cpu(), q.cpu())
        torch.testing.assert_close(actual, reference, rtol=1e-4, atol=1e-4)
        torch.cuda.synchronize()
    return dict(device=properties.name, architecture=properties.gcnArchName,
                torch_version=torch.__version__, hip_version=torch.version.hip,
                total_memory_bytes=properties.total_memory, fp32_matmul_sdpa='passed')


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
