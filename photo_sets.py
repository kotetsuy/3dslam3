"""Uploaded photo sets and asynchronous DA3 -> simple 3DGS jobs."""
import io
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import traceback
import uuid
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from time import perf_counter
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)

ROOT = Path(__file__).resolve().parent
STORE = ROOT/'DA3/uploads'
TRASH = ROOT/'DA3/trash'
MAX_SETS, MAX_IMAGES, MAX_BYTES = 20, 8, 64*1024*1024
LOCK = threading.RLock()
JOB_LOCK = threading.Lock()
ACTIVE = set()
ROCM_RUNTIME = None


class InputError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def folder(key):
    if not re.fullmatch(r'[0-9a-f]{32}', key):
        raise InputError('写真セットが見つかりません', 404)
    path = STORE/key
    if not (path/'meta.json').is_file():
        raise InputError('写真セットが見つかりません', 404)
    return path


def read_meta(path):
    return json.loads((path/'meta.json').read_text())


def write_meta(path, meta):
    temp = path/'meta.tmp'
    temp.write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
    os.replace(temp, path/'meta.json')


def listing():
    with LOCK:
        return [read_meta(p.parent) for p in sorted(STORE.glob('*/meta.json'), key=lambda p:p.stat().st_mtime, reverse=True)]


def recover_jobs():
    for meta in listing():
        if meta['status'] == 'running':
            meta.update(status='error', message='サーバーが停止したため中断しました。再生成してください。')
            write_meta(folder(meta['id']), meta)


def create(content_type, body):
    if len(body) > MAX_BYTES:
        raise InputError('写真の合計は64MB以内にしてください', 413)
    if '\r' in content_type or '\n' in content_type or not content_type.startswith('multipart/form-data'):
        raise InputError('写真をmultipart形式で送信してください')
    message = BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
    if not message.is_multipart():
        raise InputError('アップロード形式が不正です')
    name, files = '', []
    for part in message.iter_parts():
        field = part.get_param('name', header='content-disposition')
        data = part.get_payload(decode=True) or b''
        if field == 'name':
            name = data.decode('utf-8', errors='replace').strip()
        elif field == 'files':
            files.append(data)
    if not name or len(name) > 40:
        raise InputError('セット名は1〜40文字で入力してください')
    if not 2 <= len(files) <= MAX_IMAGES:
        raise InputError('写真は2〜8枚選択してください')
    validated = []
    for number, data in enumerate(files, 1):
        detected_format = None
        try:
            with Image.open(io.BytesIO(data)) as image:
                detected_format = image.format
                ext = {'JPEG':'.jpg', 'PNG':'.png', 'WEBP':'.webp', 'HEIF':'.jpg', 'MPO':'.jpg'}.get(image.format)
                if not ext:
                    raise InputError(f'{number}枚目は未対応の画像形式（{image.format}）です。JPEG・PNG・WebP・HEIC/HEIF・MPOを選択してください')
                if image.width*image.height > 30_000_000:
                    raise InputError(f'{number}枚目が3000万画素を超えています')
                image.load()
                thumb = ImageOps.exif_transpose(image).convert('RGB')
                # MPO opens on its primary image; auxiliary frames are not separate photos.
                if detected_format in ('HEIF', 'MPO'):
                    converted = io.BytesIO()
                    thumb.save(converted, format='JPEG', quality=95, subsampling=0,
                               icc_profile=image.info.get('icc_profile'))
                    data = converted.getvalue()
                thumb.thumbnail((480,360))
                stream = io.BytesIO()
                thumb.save(stream, format='JPEG', quality=85)
                validated.append((data, ext, stream.getvalue()))
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            logging.exception('Photo decode failed: index=%d format=%s bytes=%d',
                              number, detected_format, len(data))
            raise InputError(f'{number}枚目の画像を読み込めませんでした（形式: {detected_format or "判別できません"}）。JPEG・PNG・WebP・HEIC/HEIF・MPOの写真を選択してください') from exc
    with LOCK:
        if len(listing()) >= MAX_SETS:
            raise InputError('写真セットが上限に達しています', 409)
        STORE.mkdir(parents=True, exist_ok=True)
        key = uuid.uuid4().hex
        stage = STORE/('.upload-'+key)
        stage.mkdir()
        try:
            (stage/'input').mkdir()
            (stage/'thumb').mkdir()
            images = []
            for i,(data,ext,thumbnail) in enumerate(validated):
                filename=f'img_{i:03d}{ext}'
                (stage/'input'/filename).write_bytes(data)
                (stage/'thumb'/filename).write_bytes(thumbnail)
                images.append(filename)
            meta=dict(id=key, name=name, images=images, num_images=len(images), status='none',
                      message='', has_ply=False, num_gaussians=None, read_only=False,
                      created=datetime.now(timezone.utc).isoformat())
            write_meta(stage, meta)
            stage.rename(STORE/key)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return meta


def get(key):
    with LOCK:
        return read_meta(folder(key))


def archive(key):
    with LOCK:
        path = folder(key)
        if key in ACTIVE:
            raise InputError('生成中のセットは取り除けません', 409)
        TRASH.mkdir(parents=True, exist_ok=True)
        path.rename(TRASH/(key+'-'+uuid.uuid4().hex[:8]))


def start(key, device):
    if device not in ('cpu','rocm'):
        raise InputError('実行環境が不正です')
    python = ROOT/('DA3/.venv-rocm/bin/python' if device == 'rocm' else 'DA3/.venv/bin/python')
    if not python.is_file():
        raise InputError('選択した実行環境がありません。セットアップを実行してください')
    with LOCK:
        path = folder(key)
        if not JOB_LOCK.acquire(blocking=False):
            raise InputError('別のセットを生成中です。完了後に実行してください', 409)
        try:
            meta = read_meta(path)
            meta.update(status='running', message='3Dを生成しています', device=device)
            write_meta(path, meta)
            ACTIVE.add(key)
            threading.Thread(target=run, args=(key,python,device), daemon=True).start()
        except Exception:
            ACTIVE.discard(key)
            JOB_LOCK.release()
            raise
    return meta


def run(key, python, device):
    start_time = perf_counter()
    path = folder(key)
    output = path/('runs/'+uuid.uuid4().hex)
    output.mkdir(parents=True)
    try:
        with (output/'generation.log').open('w') as log:
            if device == 'rocm' and ROCM_RUNTIME is not None:
                result = ROCM_RUNTIME.generate(path/'input',output)
                log.write(json.dumps(result,indent=2)+'\n')
            else:
                subprocess.run([str(python),str(ROOT/'infer_da3.py'),str(path/'input'),
                                '--limit',str(MAX_IMAGES),'--device',device,'--dtype','float32','--output',str(output)],
                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
                subprocess.run([str(ROOT/'DA3/.venv/bin/python'),str(ROOT/'points_to_3dgs.py'),
                                str(output/'scene_points.ply'),'--output',str(output/'scene_3dgs.ply')],
                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        count = json.loads((output/'scene_3dgs.json').read_text())['gaussians']
        with LOCK:
            meta = read_meta(path)
            meta.update(status='done',message='完了',has_ply=True,num_gaussians=count,
                        result=str(output.relative_to(path)),elapsed_seconds=perf_counter()-start_time)
            write_meta(path,meta)
    except Exception as exc:
        with (output/'generation.log').open('a') as log:
            traceback.print_exc(file=log)
        with LOCK:
            meta = read_meta(path)
            meta.update(status='error',message=f'生成に失敗しました（{type(exc).__name__}）。実行環境を確認して再試行してください。',
                        failed_run=str(output.relative_to(path)))
            write_meta(path,meta)
    finally:
        with LOCK:
            ACTIVE.discard(key)
        JOB_LOCK.release()


def result_paths(key):
    path = folder(key)
    meta = get(key)
    relative = meta.get('result')
    if not relative:
        raise InputError('3Dがまだ生成されていません',404)
    output = (path/relative).resolve()
    if not output.is_relative_to(path.resolve()):
        raise InputError('保存先が不正です',404)
    return output/'scene_3dgs.ply', output/'prediction.npz'
