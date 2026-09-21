#!/usr/bin/env python3
"""Convert an RGB point PLY to unoptimized, isotropic Gaussian splats."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from plyfile import PlyData, PlyElement
from scipy.spatial import cKDTree

SH_C0 = 0.28209479177387814


def convert(input_path, output_path, opacity=0.8, scale_factor=0.75):
    if input_path.resolve() == output_path.resolve():
        raise ValueError('Input and output must differ')
    if not np.isfinite(opacity) or not 0 < opacity < 1:
        raise ValueError('opacity must be between 0 and 1 (exclusive)')
    if not np.isfinite(scale_factor) or scale_factor <= 0:
        raise ValueError('scale-factor must be finite and positive')
    start = perf_counter()
    vertex = PlyData.read(input_path)['vertex'].data
    required = ('x','y','z','red','green','blue')
    if not set(required).issubset(vertex.dtype.names):
        raise ValueError('Expected point PLY with x,y,z and red,green,blue (0..255)')
    xyz = np.column_stack([vertex[n] for n in required[:3]]).astype(np.float64)
    rgb = np.column_stack([vertex[n] for n in required[3:]]).astype(np.float64)
    if not np.isfinite(xyz).all() or not np.isfinite(rgb).all() or (rgb<0).any() or (rgb>255).any():
        raise ValueError('Invalid coordinates or RGB values')
    input_count = len(xyz)
    # Deduplicate exact positions so repeated observations cannot force zero scale.
    unique, inverse = np.unique(xyz, axis=0, return_inverse=True)
    sums = np.zeros((len(unique),3))
    np.add.at(sums,inverse,rgb)
    rgb = sums / np.bincount(inverse)[:,None] / 255.0
    xyz = unique
    if len(xyz) < 2:
        raise ValueError('At least two distinct points are required')
    distances,_ = cKDTree(xyz).query(xyz,k=min(4,len(xyz)),workers=1)
    spacing = np.sqrt(np.mean(distances[:,1:]**2,axis=1))
    positive = spacing[spacing>0]
    floor = max(float(np.median(positive))*0.05,1e-12)
    # Limit sparse outliers from becoming very large isolated blobs.
    ceiling = max(float(np.percentile(positive,95))*2,floor)
    sigma = np.clip(spacing,floor,ceiling)*scale_factor
    fields = ['x','y','z','nx','ny','nz'] + [f'f_dc_{i}' for i in range(3)] + [f'f_rest_{i}' for i in range(45)] + ['opacity'] + [f'scale_{i}' for i in range(3)] + [f'rot_{i}' for i in range(4)]
    out = np.zeros(len(xyz),dtype=[(n,'<f4') for n in fields])
    for i,n in enumerate(('x','y','z')):out[n]=xyz[:,i]
    for i in range(3):
        out[f'f_dc_{i}']=(rgb[:,i]-0.5)/SH_C0
        out[f'scale_{i}']=np.log(sigma)
    out['opacity']=np.log(opacity/(1-opacity))
    out['rot_0']=1 # identity quaternion, wxyz; isotropic so orientation is irrelevant
    if not all(np.isfinite(out[n]).all() for n in fields):
        raise ValueError('Nonfinite Gaussian attributes')
    output_path.parent.mkdir(parents=True,exist_ok=True)
    PlyData([PlyElement.describe(out,'vertex')],text=False,byte_order='<',
            comments=['Unoptimized isotropic Gaussians from DA3 RGB points; higher SH coefficients zero']).write(output_path)
    report=dict(input=str(input_path.resolve()),output=str(output_path.resolve()),
                input_points=input_count,gaussians=len(xyz),duplicates_merged=input_count-len(xyz),
                opacity=opacity,scale_factor=scale_factor,sigma_min=float(sigma.min()),sigma_median=float(np.median(sigma)),sigma_max=float(sigma.max()),
                scale_estimation='RMS distance to up to 3 nearest distinct neighbors; floor=0.05*median; cap=2*p95',
                sh_degree=3,higher_sh_zero=True,rotation='identity wxyz',optimized=False,
                coordinate_frame='unchanged from input PLY',elapsed_seconds=perf_counter()-start,
                output_bytes=output_path.stat().st_size)
    output_path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--opacity',type=float,default=0.8)
    p.add_argument('--scale-factor',type=float,default=0.75)
    a=p.parse_args()
    output=a.output or a.input.with_name(a.input.stem+'_3dgs.ply')
    try:
        print(json.dumps(convert(a.input,output,a.opacity,a.scale_factor),indent=2))
    except (OSError,ValueError) as exc:
        p.exit(1,f'Conversion failed: {exc}\n')


if __name__=='__main__':main()
