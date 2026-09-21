"""Diagnostic orthographic point projections, not a Gaussian renderer."""
from pathlib import Path
import argparse
import numpy as np
from PIL import Image, ImageDraw

parser=argparse.ArgumentParser()
parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent/'FreeSplatter-O/outputs/headphones')
root=parser.parse_args().directory
g=np.load(root/'gaussians_raw.npz')['gaussians']
g=g[g[:,15]>np.log(0.05/0.95)] # opacity > 0.05
if len(g)==0:
 raise SystemExit('No gaussians with opacity > 0.05')
xyz=g[:,:3]
color=np.uint8(np.clip(g[:,3:6]*0.28209479177387814+0.5,0,1)*255)
lo,hi=np.percentile(xyz,[1,99],axis=0)
out=Image.new('RGB',(1200,440),'white')
for panel,(a,b,d) in enumerate([(0,1,2),(0,2,1),(2,1,0)]):
 im=Image.new('RGB',(400,400),(230,230,230))
 draw=ImageDraw.Draw(im)
 scale=360/max(hi[a]-lo[a],hi[b]-lo[b])
 coords=(xyz[:,[a,b]]-(lo+hi)[[a,b]]/2)*scale+200
 for i in np.argsort(xyz[:,d])[::-1]:
  x,y=coords[i]
  if 0<=x<400 and 0<=y<400:
   draw.point((int(x),int(y)),fill=tuple(color[i]))
 out.paste(im,(panel*400,0))
 ImageDraw.Draw(out).text((panel*400+10,410),['XY','XZ','ZY'][panel]+' point projection (opacity > 0.05)',fill='black')
out.save(root/'point_preview.png')
print('High opacity points:',len(g),'bounds (1-99%):',lo.tolist(),hi.tolist())
