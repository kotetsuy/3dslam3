#!/usr/bin/env bash
# Start the local GUI after ROCm/DA3 warmup; keep the model resident.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$project_dir/server_control.py" start "$@"
