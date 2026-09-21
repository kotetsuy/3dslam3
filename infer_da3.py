#!/usr/bin/env python3
"""DA3-BASE CPU/ROCm geometry inference: RGB point clouds, not Gaussian splats."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.cache/matplotlib'))
os.environ.setdefault('XDG_CONFIG_HOME', str(ROOT/'.cache/config'))
sys.path.insert(0, str(ROOT/'DA3/source/src'))
import argparse
from contextlib import nullcontext
import json
from time import perf_counter
import numpy as np
import torch
from PIL import Image, ImageOps
from safetensors.torch import load_model
import trimesh
from depth_anything_3.api import DepthAnything3
from depth_anything_3.utils.io.input_processor import InputProcessor
from clip_classifier import collect_images


class SequentialInputProcessor(InputProcessor):
    def __call__(self, *args, **kwargs):
        kwargs['sequential'] = True
        return super().__call__(*args, **kwargs)


class DeviceDA3(DepthAnything3):
    inference_dtype = torch.float32

    @torch.inference_mode()
    def forward(self, *args, **kwargs):
        device = args[0].device
        is_gpu = device.type == 'cuda'  # PyTorch uses this name for ROCm too.
        if is_gpu:
            torch.cuda.synchronize(device)
        start = perf_counter()
        context = (torch.autocast('cuda', dtype=self.inference_dtype)
                   if is_gpu and self.inference_dtype != torch.float32 else nullcontext())
        with context:
            result = self.model(*args, **kwargs)
        if is_gpu:
            torch.cuda.synchronize(device)
        self.forward_seconds = perf_counter()-start
        return result


def unproject(depth, K, w2c):
    h,w = depth.shape
    y,x = np.mgrid[:h,:w]
    pixels=np.stack([x,y,np.ones_like(x)],axis=-1).reshape(-1,3)
    cam=(pixels @ np.linalg.inv(K).T)*depth.reshape(-1,1)
    return (cam-w2c[:3,3]) @ np.linalg.inv(w2c[:3,:3]).T


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('images',nargs='+')
    p.add_argument('--limit',type=int,default=4)
    p.add_argument('--threads',type=int,default=8)
    p.add_argument('--device',choices=['cpu','cuda','rocm'],default='cpu')
    p.add_argument('--dtype',choices=['float32','float16'],default='float32')
    p.add_argument('--repeat',type=int,default=1,help='Inference runs in one process; exports only the last prediction')
    p.add_argument('--output',type=Path,default=ROOT/'DA3/outputs/headphones')
    p.add_argument('--mask-dir',type=Path,help='RGBA masks named NN_<input_stem>.png, used only after inference')
    p.add_argument('--conf-percentile',type=float,default=40)
    a=p.parse_args()
    if a.limit<1 or a.threads<1 or a.repeat<1 or not 0<=a.conf_percentile<100:
        p.error('Invalid limit, threads, or confidence percentile')
    device = 'cuda' if a.device == 'rocm' else a.device
    if device == 'cuda' and not torch.cuda.is_available():
        p.error('GPU is unavailable; use a ROCm-enabled PyTorch environment and GPU device access')
    if a.device == 'rocm' and not torch.version.hip:
        p.error('--device rocm requires a ROCm PyTorch build')
    if device == 'cpu' and a.dtype != 'float32':
        p.error('CPU inference uses float32')
    return run_inference(a)


def create_model(device='cuda', dtype='float32', threads=8):
    torch.set_num_threads(threads)
    start=perf_counter()
    model=DeviceDA3(model_name='da3-base').eval()
    model.inference_dtype=getattr(torch,dtype)
    load_model(model,str(ROOT/'DA3/checkpoints/model.safetensors'),strict=True)
    model.to(device)
    if device == 'cuda':
        torch.cuda.synchronize()
    model.input_processor=SequentialInputProcessor()
    return model, perf_counter()-start


def run_inference(a, model=None):
    device = 'cuda' if a.device == 'rocm' else a.device
    paths=collect_images(a.images)[:a.limit]
    a.output.mkdir(parents=True,exist_ok=True)
    start=perf_counter()
    resident_model = model is not None
    if model is None:
        model, load_seconds = create_model(device,a.dtype,a.threads)
    else:
        if next(model.parameters()).device.type != device or model.inference_dtype != getattr(torch,a.dtype):
            raise ValueError('Resident model device/dtype differs from request')
        load_seconds=0.0
    if device == 'cuda':
        torch.cuda.reset_peak_memory_stats()
    inputs=[]
    for path in paths:
        with Image.open(path) as im:
            inputs.append(ImageOps.exif_transpose(im).convert('RGB'))
    inference_runs=[]
    print('Running DA3-BASE on',len(inputs),'images:',device,a.dtype,flush=True)
    for run in range(a.repeat):
        predict_start=perf_counter()
        pred=model.inference(inputs,process_res=504,process_res_method='upper_bound_resize',infer_gs=False,ref_view_strategy='first')
        predict_seconds=perf_counter()-predict_start
        inference_runs.append(dict(run=run+1,forward_seconds=model.forward_seconds,prediction_seconds=predict_seconds))
        print(json.dumps(inference_runs[-1]),flush=True)
    for name in ('depth','conf','intrinsics','extrinsics'):
        if not np.isfinite(getattr(pred,name)).all():raise ValueError(f'Nonfinite {name}')
    np.savez_compressed(a.output/'prediction.npz',depth=pred.depth,conf=pred.conf,
                        intrinsics=pred.intrinsics,extrinsics=pred.extrinsics,images=pred.processed_images)
    threshold=float(np.percentile(pred.conf,a.conf_percentile))
    xyzs=[]; rgbs=[]; mask_xyz=[]; mask_rgb=[]; views=[]
    for i,path in enumerate(paths):
        depth=pred.depth[i]; h,w=depth.shape
        xyz=unproject(depth,pred.intrinsics[i],pred.extrinsics[i])
        rgb=pred.processed_images[i].reshape(-1,3)
        keep=(depth.reshape(-1)>0)&(pred.conf[i].reshape(-1)>=threshold)&np.isfinite(xyz).all(axis=1)
        xyzs.append(xyz[keep]); rgbs.append(rgb[keep]); views.append(np.full(keep.sum(),i,dtype=np.uint8))
        Image.fromarray(pred.processed_images[i]).save(a.output/f'input_{i:02}.png')
        if a.mask_dir:
            with Image.open(a.mask_dir/f'{i:02}_{path.stem}.png') as mask:
                alpha=np.array(mask.getchannel('A').resize((w,h),Image.Resampling.NEAREST))
            obj_keep=keep&(alpha.reshape(-1)>127)
            mask_xyz.append(xyz[obj_keep]); mask_rgb.append(rgb[obj_keep])
    xyz=np.concatenate(xyzs); rgb=np.concatenate(rgbs)
    cloud=trimesh.points.PointCloud(xyz,colors=rgb)
    cloud.export(a.output/'scene_points.ply')
    trimesh.Scene(cloud).export(a.output/'scene_points.glb')
    np.savez_compressed(a.output/'points.npz',xyz=xyz,rgb=rgb,view=np.concatenate(views))
    object_count=None
    if mask_xyz:
        obj=trimesh.points.PointCloud(np.concatenate(mask_xyz),colors=np.concatenate(mask_rgb))
        obj.export(a.output/'object_points.ply')
        trimesh.Scene(obj).export(a.output/'object_points.glb')
        object_count=len(obj.vertices)
    report=dict(model='DA3-BASE',resident_model=resident_model,device=device,backend=('rocm' if torch.version.hip else 'cuda') if device == 'cuda' else 'cpu',
                dtype=a.dtype,threads=a.threads,torch_version=torch.__version__,hip_version=torch.version.hip,
                gpu_name=torch.cuda.get_device_name() if device == 'cuda' else None,
                peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated() if device == 'cuda' else None,
                inference_runs=inference_runs,repeat=a.repeat,
                images=list(map(str,paths)),depth_shape=list(pred.depth.shape),
                resolution_limit=504,ref_view_strategy='first',background_removed_before_inference=False,
                mask_dir=str(a.mask_dir) if a.mask_dir else None,conf_percentile=a.conf_percentile,
                confidence_threshold=threshold,load_seconds=load_seconds,forward_seconds=model.forward_seconds,
                prediction_seconds=predict_seconds,total_seconds=perf_counter()-start,
                scene_points=len(xyz),object_points=object_count,
                output_type='RGB point cloud, not 3DGS or mesh',metric_scale=False)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=='__main__':main()
