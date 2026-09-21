#!/usr/bin/env python3
"""Download the pinned SigLIP 2 weights, tokenizer, configs and model card."""
import argparse
from pathlib import Path
from huggingface_hub import hf_hub_download
from model_config import CACHE_DIR, MODEL_FILES, MODEL_ID, MODEL_REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=CACHE_DIR)
    parser.add_argument('--local-files-only', action='store_true', help='Verify cached files without downloading')
    args = parser.parse_args()
    try:
        for filename in MODEL_FILES:
            path = hf_hub_download(repo_id=MODEL_ID, revision=MODEL_REVISION,
                                   filename=filename, cache_dir=args.cache_dir,
                                   local_files_only=args.local_files_only)
            if not Path(path).is_file():
                raise OSError(f'Missing downloaded file: {path}')
            print(f'OK {filename}', flush=True)
    except OSError as exc:
        parser.exit(1, f'Download/verification failed: {exc}\n')
    print(f'Model: {MODEL_ID}\nRevision: {MODEL_REVISION}\nCache: {args.cache_dir.resolve()}')


if __name__ == '__main__':
    main()
