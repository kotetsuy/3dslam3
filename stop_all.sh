#!/usr/bin/env bash
# Stop only the instance recorded by this project's start_all.sh.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$project_dir/server_control.py" stop "$@"
