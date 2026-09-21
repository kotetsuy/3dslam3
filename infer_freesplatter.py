#!/usr/bin/env python3
"""Object-only FreeSplatter forward pass with PyTorch SDPA and native-frame PLY."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from safetensors.torch import load_file
from clip_classifier import collect_images

ROOT = Path(__file__).resolve().parent / 'FreeSplatter-O'


def attention(q, k, v):
    # Upstream packs batch and attention heads into dimension zero.
    return F.scaled_dot_product_attention(q.unsqueeze(1), k.unsqueeze(1), v.unsqueeze(1)).squeeze(1)


def write_ply(path, values):
    xyz, sh, opacity, scale, rotation = torch.split(values, [3, 12, 1, 3, 4], dim=-1)
    scale = torch.log(0.0001 + 0.0199 * scale.sigmoid())
    rotation = F.normalize(rotation, dim=-1)
    sh = sh.reshape(-1, 4, 3)
    data = torch.cat([xyz, torch.zeros_like(xyz), sh[:, 0], sh[:, 1:].transpose(1, 2).flatten(1), opacity, scale, rotation], dim=1).numpy().astype('<f4')
    names = ['x','y','z','nx','ny','nz'] + [f'f_dc_{i}' for i in range(3)] + [f'f_rest_{i}' for i in range(9)] + ['opacity'] + [f'scale_{i}' for i in range(3)] + [f'rot_{i}' for i in range(4)]
    header = 'ply\nformat binary_little_endian 1.0\n' + f'element vertex {len(data)}\n' + ''.join(f'property float {n}\n' for n in names) + 'end_header\n'
    with path.open('wb') as f:
        f.write(header.encode('ascii'))
        f.write(data.tobytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs'/'headphones')
    parser.add_argument('--crop-alpha', action='store_true', help='Crop to alpha > 127 before square padding')
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--limit', type=int, default=4)
    args = parser.parse_args()
    if args.limit < 1 or args.threads < 1:
        parser.error('limit and threads must be positive')
    torch.set_num_threads(args.threads)
    paths = collect_images(args.images)[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    # Execute official transformer source, replacing only the xformers import.
    # The original checkout remains unchanged; weights load strictly.
    source_path = ROOT/'source/freesplatter/models/transformer.py'
    source = source_path.read_text()
    assert source.count('import xformers.ops as xops') == 1
    ns = {'xops': SimpleNamespace(memory_efficient_attention=attention)}
    exec(compile(source.replace('import xformers.ops as xops', '# xops supplied by SDPA adapter'), str(source_path), 'exec'), ns)
    model = ns['Transformer'](output_dim=23).eval()
    state = load_file(str(ROOT/'checkpoints/freesplatter-object.safetensors'))
    assert all(k.startswith('transformer.') for k in state)
    model.load_state_dict({k.removeprefix('transformer.'): v for k,v in state.items()}, strict=True)
    del state
    load_seconds = perf_counter() - start
    tensors = []
    for i,path in enumerate(paths):
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert('RGBA')
            if args.crop_alpha:
                bbox = im.getchannel('A').point(lambda x: 255 if x > 127 else 0).getbbox()
                if bbox is None:
                    raise ValueError(f'Empty foreground: {path}')
                im = im.crop(bbox)
            # White square padding, 90% occupancy.
            white = Image.new('RGBA', im.size, 'white')
            white.alpha_composite(im)
            size = int(max(im.size)/0.9)
            canvas = Image.new('RGB', (size,size), 'white')
            canvas.paste(white.convert('RGB'), ((size-im.width)//2,(size-im.height)//2))
            canvas = canvas.resize((512,512), Image.Resampling.BICUBIC)
            canvas.save(args.output/f'input_{i:02}.png')
            tensors.append(torch.from_numpy(np.asarray(canvas).copy()).permute(2,0,1).float()/255)
    images = torch.stack(tensors).unsqueeze(0)
    preprocess_seconds = perf_counter()-start-load_seconds
    for i,block in enumerate(model.blocks):
        block.register_forward_hook(lambda m,a,o,i=i: print(f'Layer {i+1}/24: {perf_counter()-forward_start:.1f}s',flush=True))
    forward_start = perf_counter()
    with torch.inference_mode():
        raw = model(images).reshape(-1,23).float().cpu()
    inference_seconds = perf_counter()-forward_start
    if not torch.isfinite(raw).all():
        raise RuntimeError('Nonfinite model output')
    np.savez_compressed(args.output/'gaussians_raw.npz', gaussians=raw.numpy())
    selected = raw[raw[:,15].sigmoid() > 0.005]
    write_ply(args.output/'gaussians.ply', selected)
    report = dict(model='FreeSplatter-O', device='cpu', dtype='float32',threads=args.threads,
                  images=[str(p) for p in paths], resolution=512, background_removal='external RGBA segmentation' if args.crop_alpha else False,
                  preprocessing=('alpha bbox crop; ' if args.crop_alpha else '') + 'EXIF correction, white alpha composite, square pad with 0.9 occupancy, bicubic resize',
                  attention='PyTorch SDPA instead of xformers', load_seconds=load_seconds,
                  preprocessing_seconds=preprocess_seconds,inference_seconds=inference_seconds,
                  total_seconds=perf_counter()-start, raw_gaussians=len(raw),saved_gaussians=len(selected),
                  coordinate_frame='native model reference-camera frame',
                  limitations='No camera estimation, Gaussian rendering, mesh extraction or metric scale verification.')
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    main()
