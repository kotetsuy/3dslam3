#!/usr/bin/env bash
# Install ROCm 10.2 in a separate project-local environment.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_dir="$project_dir/DA3/.venv-rocm102"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$project_dir/.cache/uv}"
if [[ -e "$env_dir/.da3-ready" ]]; then
  python3 -c 'import pathlib,sys; pathlib.Path(sys.argv[1]).unlink()' "$env_dir/.da3-ready"
fi
uv venv "$env_dir" --python "${ROCM102_PYTHON:-3.14}" --allow-existing
uv pip install --python "$env_dir/bin/python" --index https://stable.repo.amd.com/rocm/whl-next/ \
  'torch[device-gfx1151]==2.15.0+rocm10.2.0' 'torchvision[device-gfx1151]==0.29.2+rocm10.2.0'
uv pip install --python "$env_dir/bin/python" opencv-python-headless
uv pip install --python "$env_dir/bin/python" --no-deps -r "$project_dir/requirements-da3-rocm.txt"
"$env_dir/bin/python" - "$project_dir" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import cv2, infer_da3, torch, torchvision
assert torch.version.hip and '+rocm10.2.0' in torch.__version__, torch.__version__
print('DA3 ready:', torch.__version__, 'HIP', torch.version.hip, 'GPU available:', torch.cuda.is_available())
PY
touch "$env_dir/.da3-ready"
