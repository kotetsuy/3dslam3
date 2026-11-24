"""Select a fully installed ROCm environment, retaining the legacy fallback."""
from pathlib import Path


def rocm_python(root: Path) -> Path:
    env = root / 'DA3/.venv-rocm102'
    if (env / '.da3-ready').is_file() and (env / 'bin/python').is_file():
        return env / 'bin/python'
    return root / 'DA3/.venv-rocm/bin/python'
