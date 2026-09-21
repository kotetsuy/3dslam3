"""Shared, pinned default for inference and model downloads."""
from pathlib import Path

MODEL_ID = 'google/siglip2-base-patch16-224'
MODEL_REVISION = '75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2'
CACHE_DIR = Path(__file__).resolve().parent / '.cache' / 'huggingface'
MODEL_FILES = (
    'config.json', 'model.safetensors', 'preprocessor_config.json',
    'special_tokens_map.json', 'tokenizer.json', 'tokenizer.model',
    'tokenizer_config.json', 'README.md',
)
