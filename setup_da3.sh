#!/usr/bin/env bash
# Isolated CPU environment for geometry-only DA3 inference.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$project_dir/.cache/uv}"
env_dir="$project_dir/DA3/.venv"
if [[ -x "$env_dir/bin/python" ]] && ! "$env_dir/bin/python" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 11))'; then
  backup="$project_dir/DA3/.venv-before-python311"
  if [[ -e "$backup" ]]; then
    echo "Cannot preserve the existing DA3 environment: $backup already exists." >&2
    exit 1
  fi
  mv "$env_dir" "$backup"
  echo "Previous DA3 environment saved to $backup"
fi
uv venv "$env_dir" --python 3.11 --allow-existing
uv pip install --python "$project_dir/DA3/.venv/bin/python" torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python "$project_dir/DA3/.venv/bin/python" -r "$project_dir/requirements-da3.txt"
