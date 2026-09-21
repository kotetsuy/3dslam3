"""CLIP scene routing. Scores are relative similarities, not calibrated probabilities."""
import argparse
import json
import math
from pathlib import Path
from time import perf_counter
from model_config import MODEL_ID, MODEL_REVISION, CACHE_DIR

LABELS = ('object', 'room', 'outdoor')
PROMPTS = {
    'object': ['A close-up photo of a single object.', 'A product photo of an object.', 'A photo focused on one item, with background visible.'],
    'room': ['A wide view of an indoor room.', 'A photo of an interior space with walls and a floor.', 'A photo of a furnished room.'],
    'outdoor': ['A wide view of an outdoor scene.', 'A photo of a street with buildings.', 'A photo of an outdoor landscape.'],
}
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}


def collect_images(inputs):
    paths = []
    for value in inputs:
        path = Path(value)
        if path.is_dir():
            paths.extend(sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS))
        elif path.is_file() and path.suffix.lower() in EXTENSIONS:
            paths.append(path)
        else:
            raise ValueError(f'Image or directory not found/supported: {path}')
    paths = list(dict.fromkeys(p.resolve() for p in paths))
    if not paths:
        raise ValueError('No images found')
    return paths


def aggregate(rows, min_score=0.60, min_margin=0.15):
    """Conservative routing: every image must confidently agree on object vs scene."""
    if not rows:
        raise ValueError('No scores supplied')
    if not 0 <= min_score <= 1 or not 0 <= min_margin <= 1:
        raise ValueError('Thresholds must be between 0 and 1')
    for row in rows:
        if len(row) != 3 or any(not math.isfinite(x) or x < 0 for x in row) or not math.isclose(sum(row), 1, abs_tol=1e-4):
            raise ValueError('Expected three finite normalized scores')
    mean = [sum(row[i] for row in rows) / len(rows) for i in range(3)]
    routes = []
    for row in rows:
        obj, scene = row[0], row[1] + row[2]
        routes.append(('object' if obj > scene else 'scene') if max(obj, scene) >= min_score and abs(obj - scene) >= min_margin else 'uncertain')
    route = routes[0] if len(set(routes)) == 1 else 'uncertain'
    return {
        'label': ('object' if route == 'object' else LABELS[max((1, 2), key=lambda i: mean[i])]) if route != 'uncertain' else 'uncertain',
        'route': route,
        'recommended_model': {'object': 'FreeSplatter-O', 'scene': 'Depth Anything 3', 'uncertain': None}[route],
        'scores': dict(zip(LABELS, mean)),
        'per_image_routes': routes,
        'reason': 'all_images_agree' if route != 'uncertain' else 'mixed_or_low_confidence',
    }


class ClipClassifier:
    def __init__(self, model=MODEL_ID, device='cpu', cache_dir=CACHE_DIR, local_files_only=False, threads=4):
        import torch
        from transformers import AutoModel, CLIPProcessor, SiglipProcessor
        if threads < 1:
            raise ValueError('threads must be positive')
        torch.set_num_threads(threads)
        self.torch = torch
        self.device = device
        self.model_id = model
        start = perf_counter()
        options = dict(cache_dir=cache_dir, local_files_only=local_files_only)
        if model == MODEL_ID:
            options['revision'] = MODEL_REVISION
        processor_class = SiglipProcessor if 'siglip' in model.lower() else CLIPProcessor
        self.processor = processor_class.from_pretrained(model, use_fast=False, **options)
        self.model = AutoModel.from_pretrained(model, **options).to(device).eval()
        prompts = [text for label in LABELS for text in PROMPTS[label]]
        self.is_siglip = self.model.config.model_type in ('siglip', 'siglip2')
        token_options = dict(padding='max_length', max_length=self.model.config.text_config.max_position_embeddings, truncation=True) if self.is_siglip else dict(padding=True)
        tokens = self.processor(text=prompts, return_tensors='pt', **token_options).to(device)
        with torch.inference_mode():
            features = self.model.get_text_features(**tokens)
            features = features / features.norm(dim=-1, keepdim=True)
            features = features.reshape(3, 3, -1).mean(dim=1)
            self.text_features = features / features.norm(dim=-1, keepdim=True)
        self._sync()
        self.load_seconds = perf_counter() - start

    def _sync(self):
        if str(self.device).startswith('cuda'):
            self.torch.cuda.synchronize(self.device)

    def classify(self, paths, min_score=0.60, min_margin=0.15, batch_size=4):
        from PIL import Image, ImageOps
        if batch_size < 1:
            raise ValueError('batch_size must be positive')
        if not paths:
            raise ValueError('No images supplied')
        start = perf_counter()
        rows = []
        for offset in range(0, len(paths), batch_size):
            images = []
            for path in paths[offset:offset + batch_size]:
                with Image.open(path) as source:
                    images.append(ImageOps.exif_transpose(source).convert('RGB'))
            pixels = self.processor(images=images, return_tensors='pt')['pixel_values'].to(self.device)
            with self.torch.inference_mode():
                features = self.model.get_image_features(pixel_values=pixels)
                features = features / features.norm(dim=-1, keepdim=True)
                logits = self.model.logit_scale.exp() * features @ self.text_features.T
                rows.extend(logits.softmax(dim=-1).cpu().tolist())
        self._sync()
        result = aggregate(rows, min_score, min_margin)
        result.update(model=self.model_id, device=self.device, thresholds={'min_score': min_score, 'min_margin': min_margin},
                      images=[{'path': str(p), 'scores': dict(zip(LABELS, row)), 'route': route} for p, row, route in zip(paths, rows, result.pop('per_image_routes'))],
                      classification_seconds=perf_counter() - start,
                      score_note='Softmax of scaled cosine similarities of mean prompt embeddings; relative scores, not calibrated probabilities. SigLIP native sigmoid scores are not used.' if self.is_siglip else 'Relative CLIP scores; not calibrated probabilities.')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', help='Image files or directories (nonrecursive)')
    parser.add_argument('--model', default=MODEL_ID)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--cache-dir', default=str(CACHE_DIR))
    parser.add_argument('--local-files-only', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--limit', type=int, help='Use first N files in sorted directory order')
    parser.add_argument('--repeat', type=int, default=1, help='Repeat with model resident for warm timing')
    parser.add_argument('--min-score', type=float, default=0.60)
    parser.add_argument('--min-margin', type=float, default=0.15)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.repeat < 1 or (args.limit is not None and args.limit < 1):
            raise ValueError('repeat and limit must be positive')
        if not 0 <= args.min_score <= 1 or not 0 <= args.min_margin <= 1:
            raise ValueError('Thresholds must be between 0 and 1')
        paths = collect_images(args.images)
        if args.limit:
            paths = paths[:args.limit]
        classifier = ClipClassifier(model=args.model, device=args.device, cache_dir=args.cache_dir, local_files_only=args.local_files_only, threads=args.threads)
        runs = [classifier.classify(paths, args.min_score, args.min_margin) for _ in range(args.repeat)]
        result = {'model_load_seconds': classifier.load_seconds, 'runs': runs}
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + '\n')
        print(rendered)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
