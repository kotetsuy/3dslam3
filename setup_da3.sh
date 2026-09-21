#!/usr/bin/env bash
# Isolated CPU environment for geometry-only DA3 inference.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$project_dir/.cache/uv}"
uv venv "$project_dir/DA3/.venv" --python 3.10 --allow-existing
uv pip install --python "$project_dir/DA3/.venv/bin/python" torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python "$project_dir/DA3/.venv/bin/python" -r "$project_dir/requirements-da3.txt"
