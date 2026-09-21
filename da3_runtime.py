"""One resident ROCm model, warmed and executed on the same dedicated thread."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import os


class ResidentDA3:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='da3-rocm')
        self.info = dict(ready=False)
        try:
            self.executor.submit(self._initialize).result()
        except BaseException:
            self.executor.shutdown(wait=False, cancel_futures=True)
            raise

    def _initialize(self):
        start = perf_counter()
        import numpy as np
        import torch
        from PIL import Image
        from infer_da3 import create_model
        from points_to_3dgs import convert
        if not torch.version.hip or not torch.cuda.is_available():
            raise RuntimeError('ROCm GPUが利用できません。setup_da3_rocm.shとデバイスへのアクセスを確認してください。')
        self.model, load_seconds = create_model('cuda','float32',8)
        self.convert = convert
        # Representative portrait batch, matching the current 4-photo workflow.
        rng = np.random.default_rng(42)
        base = rng.integers(0,256,(504,378,3),dtype=np.uint8)
        images = [Image.fromarray(np.roll(base,i*4,axis=1)) for i in range(4)]
        timings = []
        for _ in range(2):
            prediction = self.model.inference(images,process_res=504,process_res_method='upper_bound_resize',
                                              infer_gs=False,ref_view_strategy='first')
            if not all(np.isfinite(getattr(prediction,key)).all() for key in ('depth','conf','intrinsics','extrinsics')):
                raise RuntimeError('ROCm warmup produced nonfinite predictions')
            timings.append(self.model.forward_seconds)
        torch.cuda.synchronize()
        self.info = dict(ready=True,pid=os.getpid(),device=torch.cuda.get_device_name(),dtype='float32',
                         load_seconds=load_seconds,warmup_forward_seconds=timings,
                         warmup_shape=[4,504,378],initialization_seconds=perf_counter()-start)
        print('ROCm ready:',self.info,flush=True)

    def generate(self, images, output):
        return self.executor.submit(self._generate,images,output).result()

    def _generate(self, images, output):
        from infer_da3 import run_inference
        start = perf_counter()
        output = Path(output)
        args = SimpleNamespace(images=[str(images)],limit=8,threads=8,device='rocm',dtype='float32',
                               repeat=1,output=output,mask_dir=None,conf_percentile=40)
        report = run_inference(args,model=self.model)
        conversion = self.convert(output/'scene_points.ply',output/'scene_3dgs.ply')
        result = dict(pid=os.getpid(),resident_model=True,inference=report,conversion=conversion,
                      total_seconds=perf_counter()-start)
        import json
        (output/'resident_timing.json').write_text(json.dumps(result,indent=2)+'\n')
        return result

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
