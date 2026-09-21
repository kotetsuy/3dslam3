"""Reproducible local smoke evaluation; existing images are read only."""
from model_config import MODEL_ID, CACHE_DIR
import argparse
import json
from pathlib import Path
from clip_classifier import ClipClassifier, collect_images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=MODEL_ID)
    parser.add_argument('--output', type=Path, default=Path('reports/siglip2_evaluation.json'))
    args = parser.parse_args()
    datasets = {
        'headphones': (str(Path.home() / 'room3dgs/data/sets/4b8f82bc/input'), 'object'),
        'station': (str(Path.home() / 'room3dgs/data/sets/7c57ca12/input'), 'scene'),
        'room_cat': (str(Path.home() / 'room3dgs-work/out/Room_Cat/images'), 'scene'),
        'toy': (str(Path.home() / 'VGGT/results/scene_kitchen/images'), 'object'),
    }
    classifier = ClipClassifier(model=args.model, cache_dir=CACHE_DIR, local_files_only=True)
    results = {}
    for name, (directory, expected) in datasets.items():
        paths = collect_images([directory])[:4]
        runs = [classifier.classify(paths) for _ in range(3)]
        results[name] = {'expected_route': expected, 'passed': runs[-1]['route'] == expected, 'runs': runs}
        print(name, runs[-1]['route'], [round(r['classification_seconds'], 3) for r in runs], flush=True)
    mixed = collect_images([datasets['headphones'][0]])[:2] + collect_images([datasets['station'][0]])[:2]
    run = classifier.classify(mixed)
    results['mixed'] = {'expected_route': 'uncertain', 'passed': run['route'] == 'uncertain', 'runs': [run]}
    print('mixed', run['route'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'load_seconds': classifier.load_seconds, 'results': results}, indent=2) + '\n')
    if not all(value['passed'] for value in results.values()):
        raise SystemExit(f'Some expected routes did not match; inspect {args.output}')


if __name__ == '__main__':
    main()
