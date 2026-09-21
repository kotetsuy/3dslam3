"""Local U2Net segmentation; preserve source pixels and write RGBA PNGs."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ.setdefault('U2NET_HOME',str(ROOT/'.cache/rembg'))
os.environ.setdefault('OMP_NUM_THREADS','4')
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.cache/numba'))
import argparse
import json
import numpy as np
from time import perf_counter
from PIL import Image, ImageOps
from rembg import new_session, remove
from clip_classifier import collect_images


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('images',nargs='+')
 p.add_argument('--dark-object',action='store_true',help='Headphone-specific: remove light tabletop inside the headband using brightness')
 p.add_argument('--limit',type=int,default=4)
 p.add_argument('--output',type=Path,default=ROOT/'FreeSplatter-O/inputs/headphones_rgba')
 a=p.parse_args()
 if a.limit<1:p.error('limit must be positive')
 a.output.mkdir(parents=True,exist_ok=True)
 start=perf_counter()
 session=new_session('u2net',providers=['CPUExecutionProvider'])
 loaded=perf_counter()
 paths=collect_images(a.images)[:a.limit]
 for i,path in enumerate(paths):
  with Image.open(path) as im:
   rgba=remove(ImageOps.exif_transpose(im).convert('RGB'),session=session)
   if a.dark_object:
    pixels=np.array(rgba)
    brightness=pixels[:,:,:3].mean(axis=2)
    dark_weight=np.clip((145-brightness)/35,0,1)
    rgb=pixels[:,:,:3].astype('float32')
    wood=(brightness>65)&((rgb[:,:,0]-rgb[:,:,2])>10)&((rgb[:,:,1]-rgb[:,:,2])>5)
    dark_weight[wood]=0
    pixels[:,:,3]=(pixels[:,:,3]*dark_weight).astype('uint8')
    rgba=Image.fromarray(pixels)
   rgba.save(a.output/f'{i:02}_{path.stem}.png')
  print('Removed background:',path.name,flush=True)
 (a.output/'report.json').write_text(json.dumps(dict(model='u2net',dark_object_refinement=a.dark_object,images=list(map(str,paths)),load_seconds=loaded-start,segmentation_seconds=perf_counter()-loaded),indent=2))

if __name__=='__main__':main()
