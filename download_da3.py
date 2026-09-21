#!/usr/bin/env python3
"""Fetch pinned DA3 source and DA3-BASE weights; install nothing."""
import argparse
import subprocess
from pathlib import Path
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent / 'DA3'
SOURCE_URL = 'https://github.com/ByteDance-Seed/Depth-Anything-3.git'
SOURCE_REVISION = '3d835ec1a5802d64a8b8b15f817a1ab54809bfe4'
MODEL_ID = 'depth-anything/DA3-BASE'
MODEL_REVISION = 'f4a6c9b3c95e41c82048423d3493a81ec3fa810e'
FILES = ('model.safetensors', 'config.json', 'README.md')


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-files-only', action='store_true', help='Check existing source revision and downloaded files offline')
    args = parser.parse_args()
    source = ROOT / 'source'
    weights = ROOT / 'checkpoints'
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        if not (source / '.git').is_dir():
            if args.local_files_only:
                raise OSError('Source not downloaded')
            if source.exists():
                raise OSError(f'Refusing to overwrite existing directory: {source}')
            git('clone', '--no-checkout', SOURCE_URL, source)
            git('-C', source, 'checkout', '--detach', SOURCE_REVISION)
        actual = git('-C', source, 'rev-parse', 'HEAD')
        if actual != SOURCE_REVISION:
            raise OSError(f'Source revision differs: {actual}; existing checkout left untouched')
        if git('-C', source, 'status', '--porcelain', '--untracked-files=no'):
            raise OSError('Source has tracked changes; refusing to report a pinned source as verified')
        for required in ('LICENSE', 'README.md', 'src/depth_anything_3/api.py', 'pyproject.toml'):
            if not (source / required).is_file():
                raise OSError(f'Missing source file: {required}')
        print(f'OK source {SOURCE_REVISION}', flush=True)
        for filename in FILES:
            path = hf_hub_download(repo_id=MODEL_ID, revision=MODEL_REVISION,
                                   filename=filename, local_dir=weights,
                                   local_files_only=args.local_files_only)
            if not Path(path).is_file():
                raise OSError(f'Missing model file: {path}')
            print(f'OK {filename}', flush=True)
        print(f'Ready: {ROOT}\nModel revision: {MODEL_REVISION}')
    except (OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Download/verification failed: {exc}\n')


if __name__ == '__main__':
    main()
