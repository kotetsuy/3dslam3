#!/usr/bin/env python3
"""Local photo-upload GUI, DA3 jobs and copied room3dgs viewer."""
import argparse
import os
import json
import shutil
import subprocess
import ipaddress
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np
import photo_sets

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'DA3/outputs'
SETS = {
    'headphones': ('ヘッドホン・簡易3DGS', 'headphones/object_3dgs.ply', 'headphones/prediction.npz'),
    'shibuya4': ('渋谷駅・4枚', 'shibuya_4views/scene_3dgs.ply', 'shibuya_4views/prediction.npz'),
    'shibuya8': ('渋谷駅・8枚', 'shibuya_8views/scene_3dgs.ply', 'shibuya_8views/prediction.npz'),
    'headphones-optimized': ('ヘッドホン・最適化版', 'headphones/optimized_conservative/object_3dgs_optimized.ply', 'headphones/prediction.npz'),
}


def connection_urls(server):
    """Read current interface addresses, including changes after tethering reconnects."""
    bound_host, port = server.server_address[:2]
    local_only = ipaddress.ip_address(bound_host).is_loopback
    try:
        result = subprocess.run(['ip','-j','-4','address','show','up'],
                                capture_output=True,text=True,check=True,timeout=2)
        interfaces = json.loads(result.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):
        return dict(urls=[],local_only=local_only,error='PCのIPアドレスを取得できませんでした')
    urls = []
    seen = set()
    for interface in interfaces:
        if interface.get('operstate') == 'DOWN':
            continue
        for info in interface.get('addr_info',[]):
            try:
                address = ipaddress.IPv4Address(info.get('local',''))
            except ipaddress.AddressValueError:
                continue
            if address.is_loopback or address.is_unspecified or address.is_multicast:
                continue
            if not local_only and bound_host != '0.0.0.0' and str(address) != bound_host:
                continue
            if str(address) not in seen:
                seen.add(str(address))
                urls.append(dict(url=f'http://{address}:{port}/',interface=interface['ifname']))
    return dict(urls=urls,local_only=local_only,error=None)


def count_ply(path):
    with path.open('rb') as f:
        for _ in range(100):
            line = f.readline().decode('ascii').strip()
            if line.startswith('element vertex '):
                return int(line.split()[-1])
            if line == 'end_header':
                break
    raise ValueError('PLY vertex count missing')


def existing_photos(key):
    # Use the saved model inputs beside the prediction, including optimized sets.
    directory = (OUTPUT/SETS[key][2]).parent
    return {path.name: path for path in sorted(directory.glob('input_*.png'))}


@lru_cache(maxsize=16)
def cameras(relative, modified_ns):
    with np.load(relative) as pred:
        h, w = pred['images'].shape[1:3]
        result = []
        for i, (K, E) in enumerate(zip(pred['intrinsics'], pred['extrinsics'])):
            c2w = np.linalg.inv(E[:3, :3])
            result.append(dict(id=i, width=w, height=h, fx=float(K[0, 0]), fy=float(K[1, 1]),
                               position=(-c2w @ E[:3, 3]).tolist(), rotation=c2w.tolist()))
        return result


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def send_file(self, path, mime):
        if not path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(path.stat().st_size))
        self.end_headers()
        if self.command != 'HEAD':
            try:
                with path.open('rb') as f:
                    shutil.copyfileobj(f, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            self.send_json(dict(ready=True,pid=os.getpid(),instance_token=self.server.instance_token,
                                rocm=photo_sets.ROCM_RUNTIME.info if photo_sets.ROCM_RUNTIME else dict(ready=False)))
        elif path == '/api/connection':
            self.send_json(connection_urls(self.server))
        elif path in ('/', '/viewer'):
            self.send_file(ROOT/'viewer'/('index.html' if path == '/' else 'viewer.html'), 'text/html; charset=utf-8')
        elif path == '/api/sets':
            items = []
            for key, (name, ply, _) in SETS.items():
                file = OUTPUT/ply
                if file.is_file():
                    prediction = OUTPUT/SETS[key][2]
                    with np.load(prediction) as pred:
                        count = len(pred['extrinsics'])
                    items.append(dict(id=key, name=name, num_gaussians=count_ply(file), bytes=file.stat().st_size,
                                      num_images=count, images=list(existing_photos(key)), has_ply=True, read_only=True, status='done', message=''))
            self.send_json(dict(sets=photo_sets.listing()+items, max=photo_sets.MAX_SETS,
                                default_device='rocm' if photo_sets.ROCM_RUNTIME else 'cpu'))
        elif path.startswith('/api/sets/'):
            parts = path.split('/')
            if len(parts) not in (5,6):
                self.send_error(404)
                return
            key, action = parts[3:5]
            try:
                if key in SETS:
                    if action in ('thumb', 'photo') and len(parts) == 6:
                        photo = existing_photos(key).get(parts[5])
                        if photo is None:
                            self.send_error(404)
                        else:
                            self.send_file(photo, 'image/png')
                        return
                    _, ply, prediction = SETS[key]
                    ply, prediction = OUTPUT/ply, OUTPUT/prediction
                else:
                    meta = photo_sets.get(key)
                    if action == 'status' and len(parts) == 5:
                        self.send_json(meta)
                        return
                    if action == 'thumb' and len(parts) == 6 and parts[5] in meta['images']:
                        self.send_file(photo_sets.folder(key)/'thumb'/parts[5], 'image/jpeg')
                        return
                    if action == 'photo' and len(parts) == 6 and parts[5] in meta['images']:
                        photo = photo_sets.folder(key)/'input'/parts[5]
                        mime = {'.jpg':'image/jpeg', '.png':'image/png', '.webp':'image/webp'}[photo.suffix]
                        self.send_file(photo, mime)
                        return
                    ply, prediction = photo_sets.result_paths(key)
                if len(parts) == 5 and action == 'scene.ply':
                    self.send_file(ply, 'application/octet-stream')
                elif len(parts) == 5 and action == 'cameras.json' and prediction.is_file():
                    self.send_json(cameras(str(prediction), prediction.stat().st_mtime_ns))
                else:
                    self.send_error(404)
            except photo_sets.InputError as exc:
                self.send_json(dict(detail=str(exc)), exc.status)
        elif path in {'/static/'+name for name in ('viewer.js','splat-viewer.js','style.css','index.js','app.js')}:
            self.send_file(ROOT/'viewer'/path.rsplit('/',1)[-1], 'text/css' if path.endswith('.css') else 'text/javascript')
        else:
            self.send_error(404)

    def mutation(self, method):
        try:
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                raise photo_sets.InputError('異なるサイトからの操作は受け付けません',403)
            path = urlsplit(self.path).path
            if method == 'DELETE':
                parts = path.split('/')
                if len(parts) != 4 or parts[1:3] != ['api','sets']:
                    raise photo_sets.InputError('Not found',404)
                photo_sets.archive(parts[3])
                self.send_json(dict(ok=True))
                return
            try:
                length = int(self.headers.get('Content-Length','0'))
            except ValueError:
                raise photo_sets.InputError('Content-Lengthが不正です')
            if not 0 <= length <= photo_sets.MAX_BYTES:
                self.close_connection = True
                raise photo_sets.InputError('アップロードは64MB以内にしてください',413)
            self.connection.settimeout(60)
            body = self.rfile.read(length)
            if len(body) != length:
                raise photo_sets.InputError('アップロードが中断されました')
            if path == '/api/sets':
                self.send_json(photo_sets.create(self.headers.get('Content-Type',''),body),201)
            else:
                parts = path.split('/')
                if len(parts) != 5 or parts[1:3] != ['api','sets'] or parts[4] != 'reconstruct':
                    raise photo_sets.InputError('Not found',404)
                try:
                    options=json.loads(body or b'{}')
                    if not isinstance(options,dict): raise ValueError()
                except (ValueError, UnicodeDecodeError):
                    raise photo_sets.InputError('生成設定が不正です')
                self.send_json(photo_sets.start(parts[3],options.get('device','cpu')),202)
        except photo_sets.InputError as exc:
            self.log_error('Request rejected: %s', exc)
            self.send_json(dict(detail=str(exc)),exc.status)
        except (TimeoutError,ConnectionError):
            self.close_connection = True

    def do_POST(self):
        self.mutation('POST')

    def do_DELETE(self):
        self.mutation('DELETE')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--warmup-rocm',action='store_true')
    parser.add_argument('--instance-token',default='manual')
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.instance_token = args.instance_token
    if args.warmup_rocm:
        from da3_runtime import ResidentDA3
        print('Initializing ROCm and warming DA3…',flush=True)
        photo_sets.ROCM_RUNTIME = ResidentDA3()
    photo_sets.recover_jobs()
    print(f'3DGS viewer: http://{args.host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if photo_sets.ROCM_RUNTIME:
            photo_sets.ROCM_RUNTIME.close()
