#!/usr/bin/env python3
"""Fit isotropic Gaussian appearance to calibrated photos with a PyTorch renderer.

Fixed centers/cameras, front-to-back alpha compositing, perspective covariance,
white background. No gsplat/CUDA extension or additional model weights required.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from PIL import Image, ImageDraw
import torch

C0 = 0.28209479177387814
TILE = 8


def read_float_ply(path):
    # Deliberately accept only the float-only binary format produced by our converter.
    with open(path, 'rb') as f:
        if f.readline().strip() != b'ply':
            raise ValueError('Not a PLY file')
        names, count, binary = [], None, False
        while True:
            line = f.readline()
            if not line:
                raise ValueError('Truncated PLY header')
            words = line.decode('ascii').strip().split()
            if words[:1] == ['format']:
                binary = words[1:] == ['binary_little_endian', '1.0']
            elif words[:1] == ['element']:
                if words[1] != 'vertex' or count is not None:
                    raise ValueError('Only one vertex element is supported')
                count = int(words[2])
            elif words[:1] == ['property']:
                if len(words) != 3 or words[1] != 'float':
                    raise ValueError('Expected float-only Gaussian PLY')
                names.append(words[2])
            elif words == ['end_header']:
                break
        if not binary or count is None:
            raise ValueError('Expected binary little endian vertex PLY')
        a = np.fromfile(f, dtype=np.dtype([(n, '<f4') for n in names]), count=count)
        if len(a) != count or not all(np.isfinite(a[n]).all() for n in names):
            raise ValueError('Incomplete/nonfinite PLY')
    return a


def write_float_ply(path, a):
    header = 'ply\nformat binary_little_endian 1.0\ncomment Photo-fitted isotropic DA3 Gaussians\n'
    header += f'element vertex {len(a)}\n'
    header += ''.join(f'property float {n}\n' for n in a.dtype.names) + 'end_header\n'
    with open(path, 'wb') as f:
        f.write(header.encode('ascii'))
        a.tofile(f)


class TileRenderer:
    def __init__(self, xyz, sigma, prediction, masks, device):
        images = prediction['images'] / 255.0
        self.h, self.w = images.shape[1:3]
        self.views = len(images)
        self.tiles = []
        centers, covariances = [], []
        self.targets, self.masks, self.valid = [], [], []
        self.eligible = []
        for view, (K, E) in enumerate(zip(prediction['intrinsics'], prediction['extrinsics'])):
            cam = xyz @ E[:3, :3].T + E[:3, 3]
            z = cam[:, 2]
            uv = cam @ K.T
            uv = uv[:, :2] / uv[:, 2:]
            # Jacobian of perspective projection, full 2D covariance of a sphere.
            J = np.zeros((len(xyz), 2, 3), np.float32)
            J[:, 0, 0], J[:, 1, 1] = K[0, 0] / z, K[1, 1] / z
            J[:, 0, 2] = -K[0, 0] * cam[:, 0] / z**2
            J[:, 1, 2] = -K[1, 1] * cam[:, 1] / z**2
            cov = (J @ E[:3, :3])
            cov = (cov @ cov.transpose(0, 2, 1)) * sigma[:, None, None]**2
            centers.append(uv)
            covariances.append(cov[:, [0, 0, 1], [0, 1, 1]])
            # Conservative support includes max permitted 1.5x size and pixel low-pass.
            radius = 4 * np.sqrt(np.linalg.eigvalsh(cov)[:, 1] * 1.5**2 + 0.3)
            buckets = [[] for _ in range(((self.h+7)//8)*((self.w+7)//8))]
            nw = (self.w+7)//8
            for i in np.argsort(z):
                if z[i] <= 0 or not np.isfinite(radius[i]):
                    continue
                x0, y0 = np.floor((uv[i]-radius[i])/8).astype(int)
                x1, y1 = np.floor((uv[i]+radius[i])/8).astype(int)
                for ty in range(max(0,y0), min((self.h+7)//8-1,y1)+1):
                    for tx in range(max(0,x0), min(nw-1,x1)+1):
                        buckets[ty*nw+tx].append(i)
            target = images[view] * masks[view,:,:,None] + 1-masks[view,:,:,None]
            for ty in range((self.h+7)//8):
                for tx in range(nw):
                    yy, xx = np.mgrid[ty*8:ty*8+8,tx*8:tx*8+8]
                    valid = (xx < self.w) & (yy < self.h)
                    yc, xc = yy.clip(0,self.h-1), xx.clip(0,self.w-1)
                    ids = np.array(buckets[ty*nw+tx], dtype=np.int64)
                    index = len(self.tiles)
                    self.tiles.append((view,ty,tx,ids))
                    self.targets.append(target[yc,xc].reshape(64,3))
                    self.masks.append(masks[view,yc,xc].reshape(64))
                    self.valid.append(valid.reshape(64))
                    if len(ids) or np.any(masks[view,yc,xc] > .1):
                        self.eligible.append(index)
        self.device = device
        self.center = torch.tensor(np.stack(centers), dtype=torch.float32, device=device)
        self.cov = torch.tensor(np.stack(covariances), dtype=torch.float32, device=device)
        self.target = torch.tensor(np.array(self.targets), dtype=torch.float32, device=device)
        self.mask = torch.tensor(np.array(self.masks), dtype=torch.float32, device=device)
        self.valid = torch.tensor(np.array(self.valid), device=device)
        yy, xx = np.mgrid[:8,:8]
        self.offset = torch.tensor(np.stack([xx.ravel(),yy.ravel()],-1)+.5, device=device, dtype=torch.float32)
        print(json.dumps({'tiles':len(self.tiles),'active_tiles':len(self.eligible),
                          'max_candidates':max(len(t[3]) for t in self.tiles)}),flush=True)

    def render(self, selection, rgb, opacity, logsize):
        tiles = [self.tiles[i] for i in selection]
        n = max(1,max(len(t[3]) for t in tiles))
        ids = np.zeros((len(tiles),n),np.int64)
        present = np.zeros((len(tiles),n),bool)
        for b, t in enumerate(tiles):
            ids[b,:len(t[3])] = t[3]
            present[b,:len(t[3])] = True
        ids = torch.tensor(ids,device=self.device)
        present = torch.tensor(present,device=self.device)
        views = torch.tensor([t[0] for t in tiles],device=self.device)[:,None]
        origin = torch.tensor([[t[2]*8,t[1]*8] for t in tiles],device=self.device)
        pix = origin[:,None,:] + self.offset[None,:,:]
        d = pix[:,:,None,:] - self.center[views,ids][:,None,:,:]
        cov = self.cov[views,ids] * torch.exp(2*logsize[ids])[:,:,None]
        a,b,c = cov.unbind(-1)
        a,c = a+.3,c+.3
        determinant = a*c-b*b
        dx,dy = d.unbind(-1)
        power = (c[:,None,:]*dx**2-2*b[:,None,:]*dx*dy+a[:,None,:]*dy**2)/determinant[:,None,:]
        alpha = (opacity[ids].sigmoid()[:,None,:] * torch.exp(-.5*power)).clamp(max=.99)
        alpha = torch.where(present[:,None,:] & (alpha >= 1/255), alpha, 0.)
        trans = torch.cumprod(1-alpha,dim=-1)
        weights = alpha * torch.cat([torch.ones_like(trans[:,:,:1]),trans[:,:,:-1]],dim=-1)
        color = torch.einsum('bpn,bnc->bpc',weights,rgb[ids]) + trans[:,:,-1,None]
        return color, 1-trans[:,:,-1]

    @torch.no_grad()
    def evaluate(self, rgb, opacity, logsize):
        renders = np.ones((self.views,self.h,self.w,3),np.float32)
        alpha = np.zeros((self.views,self.h,self.w),np.float32)
        for start in range(0,len(self.tiles),8):
            selection = list(range(start,min(start+8,len(self.tiles))))
            color, al = self.render(selection,rgb,opacity,logsize)
            color,al = color.cpu().numpy(),al.cpu().numpy()
            for k,i in enumerate(selection):
                v,ty,tx,_ = self.tiles[i]
                hh,ww = min(8,self.h-ty*8),min(8,self.w-tx*8)
                renders[v,ty*8:ty*8+hh,tx*8:tx*8+ww] = color[k].reshape(8,8,3)[:hh,:ww]
                alpha[v,ty*8:ty*8+hh,tx*8:tx*8+ww] = al[k].reshape(8,8)[:hh,:ww]
        return renders,alpha


def metrics(render, target, masks):
    error = render-target
    fg = masks>.5
    mse = float(np.mean(error[fg]**2))
    return {'foreground_mae':float(np.abs(error[fg]).mean()),'foreground_psnr_db':float(-10*np.log10(max(mse,1e-12))),
            'full_image_mae':float(np.abs(error).mean()),'full_image_psnr_db':float(-10*np.log10(max(float(np.mean(error**2)),1e-12)))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=Path('DA3/outputs/headphones/object_3dgs.ply'))
    p.add_argument('--prediction',type=Path,default=Path('DA3/outputs/headphones/prediction.npz'))
    p.add_argument('--mask-dir',type=Path,default=Path('FreeSplatter-O/inputs/headphones_rgba'))
    p.add_argument('--output-dir',type=Path,default=Path('DA3/outputs/headphones/optimized_conservative'))
    p.add_argument('--steps',type=int,default=4000)
    p.add_argument('--batch-tiles',type=int,default=16)
    p.add_argument('--device',default='cuda')
    a = p.parse_args()
    if a.steps < 1 or a.batch_tiles < 1:
        p.error('--steps and --batch-tiles must be positive')
    if not 1 <= a.batch_tiles <= 128:
        p.error('--batch-tiles must be at most 128')
    torch.set_num_threads(8)
    torch.manual_seed(42)
    rng = np.random.default_rng(42)
    start = perf_counter()
    vertex = read_float_ply(a.input)
    xyz = np.column_stack([vertex[n] for n in ('x','y','z')])
    scales = np.column_stack([vertex[f'scale_{i}'] for i in range(3)])
    if not np.allclose(scales,scales[:,:1]):
        raise ValueError('This renderer supports isotropic Gaussians only')
    if any(np.any(vertex[f'f_rest_{i}'] != 0) for i in range(45)):
        raise ValueError('Expected DC-only SH input')
    pred = dict(np.load(a.prediction))
    h,w = pred['images'].shape[1:3]
    paths = sorted(a.mask_dir.glob('*.png'))
    if len(paths) != len(pred['images']):
        raise ValueError('One ordered RGBA mask per prediction view required')
    masks = np.stack([np.asarray(Image.open(path).getchannel('A').resize((w,h),Image.Resampling.BILINEAR),np.float32)/255 for path in paths])
    if not np.any(masks > .5):
        raise ValueError('Masks contain no foreground')
    target = pred['images']/255 * masks[:,:,:,None]+1-masks[:,:,:,None]
    renderer = TileRenderer(xyz,np.exp(scales[:,0]),pred,masks,a.device)
    rgb0 = torch.tensor(np.column_stack([vertex[f'f_dc_{i}'] for i in range(3)])*C0+.5,device=a.device)
    opacity0 = torch.tensor(vertex['opacity'].copy(),device=a.device)
    rgb = torch.nn.Parameter(rgb0.clone())
    opacity = torch.nn.Parameter(opacity0.clone())
    logsize = torch.nn.Parameter(torch.zeros(len(vertex),device=a.device))
    optimizer = torch.optim.Adam([{'params':[rgb],'lr':.003},{'params':[opacity],'lr':.03},{'params':[logsize],'lr':.003}])
    a.output_dir.mkdir(parents=True,exist_ok=True)
    before,before_alpha = renderer.evaluate(rgb,opacity,logsize)
    before_metrics = metrics(before,target,masks)
    print('before',json.dumps(before_metrics),flush=True)
    training_start = perf_counter()
    history = []
    for step in range(a.steps):
        selection = rng.choice(renderer.eligible,size=a.batch_tiles,replace=True).tolist()
        rendered,alpha = renderer.render(selection,rgb,opacity,logsize)
        truth,mask,valid = renderer.target[selection],renderer.mask[selection],renderer.valid[selection]
        weight = valid.float() * (.25+.75*mask)
        photometric = ((rendered-truth).abs().mean(-1)*weight).sum()/weight.sum()
        silhouette = ((alpha-mask).abs()*valid).sum()/valid.sum()
        regularizer = .002*(rgb-rgb0).square().mean() + .001*logsize.square().mean() + .0001*(opacity-opacity0).square().mean()
        loss = photometric + .2*silhouette + regularizer
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            rgb.copy_(torch.maximum(torch.minimum(rgb, rgb0+.1), rgb0-.1).clamp(0,1))
            opacity.clamp_(-4.6,4.6)
            logsize.clamp_(np.log(.67),np.log(1.5))
        if step%250==0 or step==a.steps-1:
            row={'step':step+1,'loss':float(loss.detach()),'seconds':perf_counter()-training_start}
            history.append(row)
            print(json.dumps(row),flush=True)
    torch.cuda.synchronize() if a.device.startswith('cuda') else None
    train_seconds = perf_counter()-training_start
    after,after_alpha = renderer.evaluate(rgb,opacity,logsize)
    after_metrics = metrics(after,target,masks)
    print('after',json.dumps(after_metrics),flush=True)
    out = vertex.copy()
    color = rgb.detach().cpu().numpy()
    size = logsize.detach().cpu().numpy()
    for i in range(3):
        out[f'f_dc_{i}'] = (color[:,i]-.5)/C0
        out[f'scale_{i}'] += size
    out['opacity'] = opacity.detach().cpu().numpy()
    output = a.output_dir/'object_3dgs_optimized.ply'
    if output.resolve() == a.input.resolve():
        raise ValueError('Refusing to overwrite input')
    write_float_ply(output,out)
    reread = read_float_ply(output)
    assert len(reread)==len(vertex)
    assert all(np.array_equal(reread[k],vertex[k]) for k in ('x','y','z'))
    # Independently verify exported parameters reproduce the optimized training render.
    export_rgb = torch.tensor(np.column_stack([reread[f'f_dc_{i}'] for i in range(3)])*C0+.5,device=a.device)
    export_opacity = torch.tensor(reread['opacity'].copy(),device=a.device)
    export_size = torch.tensor(reread['scale_0']-vertex['scale_0'],device=a.device)
    with torch.no_grad():
        ids = renderer.eligible[::max(1,len(renderer.eligible)//16)][:16]
        saved,_ = renderer.render(ids,export_rgb,export_opacity,export_size)
        fitted,_ = renderer.render(ids,rgb,opacity,logsize)
        roundtrip = float((saved-fitted).abs().max())
        assert roundtrip < 1e-5
    contact = Image.new('RGB',(w*3,h*len(masks)+28),'white')
    draw = ImageDraw.Draw(contact)
    for col,label in enumerate(['Photo + mask (target)','Before optimization','After optimization']):
        draw.text((col*w+8,8),label,fill='black')
    for view in range(len(masks)):
        for col,(label,data) in enumerate([('target',target),('before',before),('after',after)]):
            im = Image.fromarray(np.uint8(np.clip(data[view],0,1)*255))
            im.save(a.output_dir/f'{label}_{view:02d}.png')
            contact.paste(im,(col*w,28+view*h))
    contact.save(a.output_dir/'comparison.jpg',quality=94)
    report = {'input':str(a.input.resolve()),'output':str(output.resolve()),'prediction':str(a.prediction.resolve()),
              'masks':[str(x.resolve()) for x in paths],'device':torch.cuda.get_device_name() if a.device.startswith('cuda') else a.device,
              'torch':torch.__version__,'gaussians':len(vertex),'resolution':[w,h],'steps':a.steps,'batch_tiles':a.batch_tiles,'seed':42,
              'optimized':['RGB SH DC','opacity','isotropic scale'],'fixed':['positions','cameras','rotations','zero higher SH'],
              'scale_factor_bounds':[.67,1.5],'rgb_change_bound':.1,'silhouette_loss_weight':.2,'renderer':'PyTorch perspective covariance, 0.3px^2 low-pass, depth-sorted alpha compositing, white background',
              'evaluation':'All four training views, foreground mask > 0.5. No held-out or novel-view claim.',
              'before':before_metrics,'after':after_metrics,'training_seconds':train_seconds,'total_seconds':perf_counter()-start,
              'export_render_max_error':roundtrip,'history':history}
    (a.output_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='history'},indent=2),flush=True)


if __name__=='__main__':
    main()
