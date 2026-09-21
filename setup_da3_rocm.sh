#!/usr/bin/env bash
# Read-only reuse of an existing ROCm PyTorch environment; DA3 additions stay local.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
rocm_python="${ROCM_PYTHON:-$HOME/RealtimeDepth/.venv-rocm10/bin/python}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$project_dir/.cache/uv}"
"$rocm_python" -c 'import torch, torchvision, numpy, cv2; assert torch.version.hip, "ROCm PyTorch is required"; print("Reusing", torch.__version__)'
uv venv "$project_dir/DA3/.venv-rocm" --python "$rocm_python" --system-site-packages --allow-existing
"$project_dir/DA3/.venv-rocm/bin/python" - "$rocm_python" <<'PY'
import json, pathlib, site, subprocess, sys
base_sites = json.loads(subprocess.check_output([sys.argv[1], '-c', 'import site,json; print(json.dumps(site.getsitepackages()))'], text=True))
pathlib.Path(site.getsitepackages()[0], 'rocm_base.pth').write_text('\n'.join(base_sites)+'\n')
PY
# Resolve nothing against torch: ordinary dependency resolution could install a different build.
uv pip install --python "$project_dir/DA3/.venv-rocm/bin/python" --no-deps -r "$project_dir/requirements-da3-rocm.txt"
"$project_dir/DA3/.venv-rocm/bin/python" - "$project_dir" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import infer_da3, torch
assert torch.version.hip
print('DA3 ready:', torch.__version__, 'HIP', torch.version.hip)
PY
