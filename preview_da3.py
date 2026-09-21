"""Create diagnostic projections and a standalone interactive point viewer."""
from pathlib import Path
import argparse
import json
import html as html_utils
import numpy as np
import trimesh
from PIL import Image, ImageDraw

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent/'DA3/outputs/headphones')
p.add_argument('--cloud',choices=['object_points.ply','scene_points.ply'],help='Default: object cloud when present, otherwise scene cloud')
p.add_argument('--label',default='DA3点群')
a=p.parse_args()
cloud_name=a.cloud or ('object_points.ply' if (a.directory/'object_points.ply').exists() else 'scene_points.ply')
cloud=trimesh.load(a.directory/cloud_name,process=False)
xyz=np.array(cloud.vertices); colors=np.array(cloud.colors)[:,:3]
lo,hi=np.percentile(xyz,[1,99],axis=0)
center=(lo+hi)/2
out=Image.new('RGB',(1200,440),'white')
for panel,(u,v,d) in enumerate([(0,1,2),(0,2,1),(2,1,0)]):
 im=Image.new('RGB',(400,400),'#dddddd'); draw=ImageDraw.Draw(im)
 xy=(xyz[:,[u,v]]-center[[u,v]])*360/max(hi[u]-lo[u],hi[v]-lo[v])+200
 for i in np.argsort(xyz[:,d])[::-1]:
  x,y=xy[i]
  if 0<=x<400 and 0<=y<400:draw.point((int(x),int(y)),fill=tuple(colors[i]))
 out.paste(im,(panel*400,0)); ImageDraw.Draw(out).text((panel*400+10,410),['XY','XZ','ZY'][panel]+' DA3 point cloud',fill='black')
out.save(a.directory/'point_preview.png')
indices=np.linspace(0,len(xyz)-1,min(len(xyz),40000),dtype=int)
points=np.round((xyz[indices]-center)/max(hi-lo),5)
rows=np.column_stack([points,colors[indices]]).tolist()
html='''<!doctype html><meta charset="utf-8"><title>DA3 point cloud</title>
<style>body{margin:0;background:#ddd;font:16px sans-serif}header{position:absolute;top:12px;left:16px;background:#fffd;padding:12px}canvas{display:block;touch-action:none}</style>
<header>LABEL（3DGSではありません）<br>ドラッグ: 回転 / ホイール: 拡大縮小 / ダブルクリック: リセット<br>表示は最大4万点に間引き。PLY/GLBは全点です。</header><canvas></canvas><script>
const pts=DATA;const c=document.querySelector('canvas'),ctx=c.getContext('2d');let rx=0,ry=0,zoom=1,drag=false,px,py;
function render(){c.width=innerWidth;c.height=innerHeight;ctx.fillStyle='#ddd';ctx.fillRect(0,0,c.width,c.height);const ax=Math.cos(rx),bx=Math.sin(rx),ay=Math.cos(ry),by=Math.sin(ry),s=Math.min(c.width,c.height)*.75*zoom;
let q=pts.map(p=>{const x=ay*p[0]+by*p[2],z=-by*p[0]+ay*p[2];return[x,ax*p[1]-bx*z,bx*p[1]+ax*z,p];});q.sort((a,b)=>b[2]-a[2]);for(const [x,y,z,p] of q){ctx.fillStyle=`rgb(${p[3]},${p[4]},${p[5]})`;ctx.fillRect(c.width/2+x*s,c.height/2+y*s,2,2);}}
c.onpointerdown=e=>{drag=true;px=e.clientX;py=e.clientY;c.setPointerCapture(e.pointerId)};c.onpointerup=()=>drag=false;c.onpointercancel=()=>drag=false;c.onpointermove=e=>{if(!drag)return;ry+=(e.clientX-px)*.01;rx-=(e.clientY-py)*.01;px=e.clientX;py=e.clientY;render()};c.onwheel=e=>{e.preventDefault();zoom=Math.max(.1,Math.min(10,zoom*Math.exp(-e.deltaY*.001)));render()};c.ondblclick=()=>{rx=ry=0;zoom=1;render()};onresize=render;render();</script>'''.replace('DATA',json.dumps(rows,separators=(',',':'))).replace('LABEL',html_utils.escape(a.label))
(a.directory/'viewer.html').write_text(html)
print('Preview and offline viewer written:',a.directory)
