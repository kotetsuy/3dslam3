# 3dslam3 — Generate simple 3DGS from multiple photos

[Japanese documentation / 日本語](READMEJ.md)

## Model selection status

- **SigLIP 2: adopted** for classifying objects versus rooms/scenes. Implemented as a standalone CLI; it does not run automatically from the photo GUI.
- **FreeSplatter-O: rejected**. Four headphone photos were tested both with backgrounds and after background removal, but the user was not satisfied with the visual quality. CPU inference took about 50 seconds, also missing the 10-second target. This decision applies to the photos, preprocessing, and execution conditions tested here. Scripts and results are retained for reproducibility.
- **DA3-BASE → point cloud → simple 3DGS: adopted as the current default pipeline**. The user rated the headphone and Shibuya Station results positively after viewing them.
- **Photo-based optimization: optional additional processing**. Optimization of color, opacity, and size has been implemented and validated. It is not part of normal GUI generation because the simple conversion is currently considered sufficient.

## Current usage

Updated: 2026-09-21. The target machine is an AMD Ryzen AI MAX+ 395 / Radeon 8060S. The current pipeline is:

```text
2–8 photos (start with 4)
  → Estimate depth and camera poses with DA3-BASE
  → Convert to an RGB point cloud
  → Convert to spherical Gaussians
  → Save a PLY with standard 3DGS attributes and display it in a WebGL2 viewer
```

DA3-BASE itself does not generate 3DGS directly. The GUI generates the entire scene, including the background. Extracting only the object using background-removal masks, as tested with the headphones, is an additional CLI operation. No mesh is generated.

### Starting and stopping

The required models and environments are already set up on this PC. Run these commands from the project directory:

```bash
./start_all.sh
# Reports successful startup after ROCm initialization, model loading, and warmup
# Browser: http://127.0.0.1:8080/

./stop_all.sh
```

While running, the server keeps the DA3 model on the GPU and reuses it for photo generation. New sets default to GPU (ROCm / float32), with CPU also available. Use `./start_all.sh --cpu` to skip the resident ROCm model. Logs are written to `run/server.log`. See the sections below for initial downloads and setup, configuration changes, and which processes the stop script manages. `start_all.sh` itself does not install dependencies or download models.

### Photo GUI and viewer

1. Enter a set name, then select photos by clicking or dragging and dropping.
2. Click “Save this set” (このセットを保存).
3. Select the execution environment and click “Create 3D” (3Dを作成).
4. When generation finishes, click “View 3D” (3Dを見る). You can also download the PLY.

Supports JPEG, PNG, WebP, HEIC/HEIF, and MPO: 2–8 photos, up to 64 MB total, and up to 30 million pixels per image. HEIC/HEIF and MPO images are orientation-corrected and converted to JPEG on upload. Only the primary image of each MPO is used. Up to 20 new sets can be stored, and only one generation job can run at a time. Existing headphone and Shibuya Station results are available in the same list.

Each card displays all its photos. Click a photo to open the full-size stored image in a new tab. Existing headphone and Shibuya Station results use the same photo-card layout and display the saved model input images (`input_*.png`); their 3D results remain read-only. The user confirmed both the photo links and the updated cards work.

The photo-selection GUI and WebGL2 viewer were copied from room3dgs and connected to the DA3 pipeline. The original room3dgs project was not modified. Dragging in the viewer rotates around **the center of the model's coordinate bounds**, rather than a point at a fixed distance. Right-drag pans, Ctrl+wheel moves forward/backward, and number keys return to the capture viewpoints.

### Understanding processing times

| Conditions | Measured time | Scope |
|---|---:|---|
| 4 Shibuya Station photos, resident ROCm FP32 | **About 1.91–1.92 s** | Photo loading, DA3 inference, point-cloud conversion, and simple 3DGS saving; excludes upload, startup, and display |
| DA3 network only, same conditions | About 0.356 s | Inference only, included in the row above |
| 4 Shibuya Station photos, standalone CPU run | About 6.31 s | Includes Python startup, imports, model loading, and point-cloud/simple 3DGS saving |
| 8 Shibuya Station photos, standalone CPU run | About 10.49 s | Same scope as above |
| 4 Shibuya Station photos, standalone ROCm run | About 6.34–6.82 s | Same scope; separate FP16/FP32 runs with caches populated by earlier tests |
| 4 headphone photos, initial CPU measurement | About 3.54 s | DA3 internal timing of 3.38 s + simple conversion of 0.16 s; excludes startup, imports, background removal, etc. |

**The resident-model result of about 1.9 seconds and the startup-inclusive result of about 6 seconds cover different scopes.** DA3 model initialization and warmup at server startup took about 4 seconds in this test, excluding Python startup and some imports. The full time from photo upload to display on an iPhone has not been measured. Detailed conditions and measurements are retained below.

### Devices used

| Operation | Current implementation |
|---|---|
| SigLIP 2 classification (standalone CLI) | CPU; not connected to the GUI |
| DA3 depth and camera estimation | Resident ROCm GPU during normal startup; CPU path retained |
| Point-cloud creation, simple 3DGS conversion, and saving | CPU |
| Optional photo-based optimization | ROCm GPU |
| Browser display | WebGL2; GPU use depends on the browser environment |

### Connecting from an iPhone or personal hotspot

`./start_all.sh` listens on `0.0.0.0` by default, allowing external connections. To use an iPhone, connect the PC to the same network, such as the iPhone's personal hotspot. Use `./start_all.sh --host 127.0.0.1` for PC-only access. Normal startup:

```bash
./stop_all.sh
./start_all.sh
```

On the PC, check “PC connection URL” (PCの接続URL) at the top of the page. Open that URL in Safari on the iPhone to select photos. An example is `http://192.168.0.9:8080/`, but this IP is not fixed. The page obtains IPv4 addresses from connected interfaces and refreshes them **every 15 seconds and when focus returns**. It also displays the actual port if changed. Use the displayed PC IP address, rather than entering `0.0.0.0` or the iPhone's own `localhost` in Safari.

If the server is listening only locally, the page indicates that too. Displaying a URL does not enable external access by itself. If you cannot connect, check the PC's network connection, IP address, listening configuration, and firewall access to port 8080. Uploading four 1152×1536 photos from a physical iPhone was confirmed by the user after adding MPO support. Personal-hotspot connectivity has not been separately verified. Select JPEG, PNG, WebP, HEIC/HEIF, or MPO files supported by the photo GUI.

### Storage locations and main files

| Location or file | Purpose |
|---|---|
| `DA3/checkpoints/`, `DA3/source/` | DA3 weights and official source at pinned revisions |
| `DA3/.venv/`, `DA3/.venv-rocm/` | CPU environment and additional ROCm dependencies |
| `DA3/uploads/<ID>/` | GUI photos, thumbnails, metadata, and generated results |
| `DA3/trash/` | Archived sets removed from the GUI list |
| `DA3/outputs/` | CLI test results, including headphones and Shibuya Station |
| `viewer/` | Copied GUI, WebGL2 viewer, and license notices |
| `start_all.sh`, `stop_all.sh`, `server_control.py` | Server startup, shutdown, and readiness checks |
| `viewer_server.py`, `photo_sets.py`, `da3_runtime.py` | HTTP API, photo-set management, and resident ROCm model |
| `infer_da3.py`, `points_to_3dgs.py` | Depth/point-cloud inference and simple 3DGS conversion |
| `optimize_3dgs.py` | Optional photo-based optimization |
| `reports/` | Validation reports |
| `run/` | Server control files and logs |

Downloads, generated files, photos, environments, and caches are excluded by `.gitignore` entries such as `.venv/`, `.cache/`, `/DA3/`, `/FreeSplatter-O/`, and `/run/`. Download scripts, execution scripts, validation code, and license notices are intended to be tracked. License details and pinned revisions are listed in the model-specific sections.

## SigLIP 2 classification (standalone CLI)

After implementing and comparing CLIP, we switched to SigLIP 2, whose selected weights have an explicit license in the model card. CLIP comparison records are retained.

`google/siglip2-base-patch16-224` classifies photos as `object` (object-focused), `room` (indoor space), or `outdoor` (outdoor scene). SigLIP 2 is the default model. No additional training is performed.

### SigLIP 2 setup and download

```bash
uv venv .venv
uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python download_model.py
```

`download_model.py` downloads the model from Hugging Face. The first download requires network access and about 1.6 GB of free space. Existing downloaded files are reused. `requirements.lock` lists the packages in the measured environment.

The model ID, revision, and default storage location are centralized in `model_config.py`; inference and download use the same revision.

- Model: `google/siglip2-base-patch16-224`
- Revision: `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`
- Storage: `.cache/huggingface/` under the project root, independent of the working directory at runtime
- Downloaded files: `model.safetensors`, `config.json`, `preprocessor_config.json`, `special_tokens_map.json`, `tokenizer.json`, `tokenizer.model`, `tokenizer_config.json`, and the upstream `README.md` (model card)

All downloaded files, Hub caches, and lock files are stored under `.cache/` and excluded by `.gitignore`. The `.venv/` virtual environment is also excluded.

```bash
# Check that the required downloaded files exist without using the network
.venv/bin/python download_model.py --local-files-only
```

Use `--cache-dir` to change the storage location. Pass the same `--cache-dir` to inference. If you create a custom storage directory inside the repository, add it to `.gitignore` too.

### Running classification

```bash
.venv/bin/python clip_classifier.py /path/to/photos --limit 4 --local-files-only
# Keep the model loaded, measure three runs, and save JSON
.venv/bin/python clip_classifier.py /path/to/photos --limit 4 --repeat 3 --local-files-only --output reports/result.json
```

Photos are processed locally. You can also specify multiple files directly. Directory inputs include only immediate children, sorted by filename; omitting `--limit` processes all images. EXIF orientation correction and RGB conversion are applied. Invalid files and corrupt images produce errors.

Defaults are CPU, 4 threads, and float32. Instantiate `ClipClassifier` once and call `classify(paths)` repeatedly to keep the model resident. `--device cuda` requires a compatible PyTorch build; GPU classification has not been tested. `--model` can select CLIP for comparison, but the default download script downloads only SigLIP 2.

### Classification method and legacy routing

For each class, normalized average features are built from three English prompts. Image similarity is multiplied by the learned scale, then passed through softmax. SigLIP text is padded to the model's maximum length. These are relative classification scores for this application, not SigLIP's native sigmoid scores or calibrated probabilities of correctness. The shared `logit_bias` is omitted because it cancels out in softmax.

A recommended model is returned only when all images in a set agree on object or scene with a sufficient margin. The scene score is room + outdoor. Default requirements are a maximum score of at least 0.60 and an object/scene margin of at least 0.15. Mixed or low-confidence sets return `uncertain`. These thresholds are not calibrated.

- Object → `FreeSplatter-O`
- Scene → `Depth Anything 3`
- Uncertain → no recommended model

This describes the `recommended_model` output in `clip_classifier.py` from the comparison tests. **The legacy object → FreeSplatter-O mapping remains in the code, but is no longer the adopted policy.** The classifier does not launch a reconstruction model, and the GUI does not use this routing. The current GUI uses DA3 → simple 3DGS for both objects and scenes.

### SigLIP 2 license

The selected SigLIP 2 weights are explicitly licensed under **Apache-2.0** in Google's [model card at the pinned revision](https://huggingface.co/google/siglip2-base-patch16-224/blob/75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2/README.md). The download script also saves the model card containing this declaration.

Commercial use, modification, and redistribution are permitted under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). Key requirements and provisions include:

- When redistributing, provide recipients with the full Apache License 2.0 text. A README link alone is not a substitute.
- Mark modified files as changed and retain relevant copyright, patent, trademark, and attribution notices.
- If the distribution includes a NOTICE file, retain the applicable attribution notices.
- The license provides no warranty and does not grant trademark rights.
- Using this model does not require disclosure of your application's source code.

This section describes the selected model's terms. Dependencies such as PyTorch and Transformers have their own licenses. This section does not assign a new license to this project's original code.

### Classification validation results (2026-09-21)

AMD Ryzen AI MAX+ 395, CPU with 4 threads, float32, Python 3.14.3, torch 2.14.0+cpu, and transformers 4.57.6. Each set was processed three times while retaining the same loaded model.

| Input (4 photos per set) | SigLIP 2 result | Resident runs 2–3 |
|---|---|---|
| Headphones | object | 0.456–0.460 s |
| Shibuya Station | room / scene | 0.455–0.456 s |
| Room with a cat | uncertain | 0.475–0.476 s |
| Toys on a table | object | 0.441–0.442 s |
| 2 headphone photos + 2 station photos | uncertain | One run only; see JSON |

Timing includes image loading, preprocessing, inference, and decision logic. It excludes Python startup, library imports, model initialization, downloads, and JSON writing. Model initialization from cache took 0.653 seconds.

For the room with a cat, one close-up photo of small items near a wall was classified as an object, disagreeing with the other three and producing an uncertain result. Of the four regular sets, three followed the expected route and one was uncertain. The mixed set also returned uncertain. Routing decisions matched the earlier CLIP results, while processing took about 2.6–3.1 times as long. This small sample does not establish general accuracy. A dedicated outdoor set, GPU classification speed, and reconstruction quality when connected to classification were not tested.

```bash
.venv/bin/python -m unittest discover -s tests -p test_classifier.py -v
HF_HUB_OFFLINE=1 .venv/bin/python evaluate_clip.py
```

All seven unit tests passed. The real-image evaluation script depends on existing data paths on this machine. It returns exit code 1 for the known evaluation shortfall in which the room does not follow the expected scene route.

Raw results: [SigLIP 2](reports/siglip2_evaluation.json), [original CLIP](reports/evaluation.json), and [CLIP regression check](reports/clip_regression.json).

## FreeSplatter-O download and test record (rejected)

FreeSplatter-O estimates 3D Gaussian Splatting and camera parameters from multiple object photos. It is not an object detector. It was tested as a downstream reconstruction candidate for photos classified as object-focused by SigLIP 2, but was rejected based on visual quality. The following records are retained for reproducibility.

```bash
# Use the same download virtual environment as SigLIP 2
.venv/bin/python download_freesplatter.py
# Check downloaded files and the source revision without network access
.venv/bin/python download_freesplatter.py --local-files-only
```

Git and huggingface-hub, installed by the setup above, are required. The script stores files in `FreeSplatter-O/` under the project root regardless of the working directory. The entire folder is listed in `.gitignore`. The download script itself is intended to be tracked.

```text
FreeSplatter-O/
├── source/                            # Official Git repository (configuration, code, license)
│   ├── LICENSE.txt
│   ├── README.md
│   ├── configs/freesplatter-object.yaml
│   └── ...
└── checkpoints/
    ├── freesplatter-object.safetensors # About 1.23 GB, 306M parameters
    ├── README.md                      # Model card from the weights publisher
    └── .cache/                        # Hugging Face download metadata
```

Downloads use these pinned versions:

- [Official source](https://github.com/TencentARC/FreeSplatter): `70ef1ff0a8b618d80aab6eaad3cc580536da2ece`
- [Official weights](https://huggingface.co/TencentARC/FreeSplatter): `728fad7e13bad72d7a47407be523fdb571832e08`
- Only the standard `freesplatter-object.safetensors` weights are downloaded. The 2DGS and scene variants are not downloaded.

Repeated runs reuse existing downloads. If the source revision differs or tracked files have been modified, the script stops without overwriting changes. The offline check verifies file existence, source revision, and related conditions; it does not recompute a hash of the entire weights file.

### FreeSplatter license

The official README states that **both code and models are covered by a license based on Apache 2.0 with additional Tencent-specific terms**. Do not assume it is identical to standard Apache-2.0 based solely on the Hugging Face `apache-2.0` tag.

The [LICENSE.txt at the pinned version](https://github.com/TencentARC/FreeSplatter/blob/70ef1ff0a8b618d80aab6eaad3cc580536da2ece/LICENSE.txt) identifies inference code, parameters, and weights as covered materials and states that use within the EU is not intended. Review the original text when using or distributing the materials, and follow its requirements, including bundling the license, preserving relevant notices, and identifying modified files. A copy is saved at `FreeSplatter-O/source/LICENSE.txt`.

The [official README](https://github.com/TencentARC/FreeSplatter/blob/70ef1ff0a8b618d80aab6eaad3cc580536da2ece/README.md) also explains that Hunyuan3D-1 and BRIAAI RMBG-2.0, used by the demo, have separate noncommercial licenses. Our script does not download these additional models.

### Current setup scope

After downloading the source and object weights, Gaussian generation was completed using the CPU-only path below. The officially recommended environment is CUDA-focused; GPU inference on the Radeon 8060S has not been tested.

The official `app.py` downloads additional models and expects weights under `./ckpts/FreeSplatter`. The dedicated script below reads our `checkpoints/` directory directly. Do not simply add the official CUDA dependencies to the CPU virtual environment used for SigLIP 2.

### FreeSplatter-O CPU inference (2026-09-21)

```bash
.venv/bin/python infer_freesplatter.py /path/to/object/photos --limit 4
# Diagnostic point-cloud projections for the default headphones output
.venv/bin/python preview_freesplatter.py
```

`infer_freesplatter.py` loads the official Transformer and replaces xformers Attention with PyTorch SDPA. It does not modify the official source, and checks all weights with `strict=True`. The replacement attention was verified against an explicit scaled dot-product calculation on small tensors. A full-model numerical comparison against the official xformers implementation has not been performed.

Inputs were four headphone photos in filename order. Without background removal, preprocessing applied EXIF orientation correction, compositing onto white, square padding with 90% image occupancy, and resizing to 512×512. These conditions differ from the official demo's background removal and foreground cropping. Results below used CPU, 8 threads, and float32.

| Operation | Time |
|---|---:|
| Model construction and weight loading | 1.54 s |
| Image preprocessing | 0.25 s |
| Inference | 49.59 s |
| Total including output saving | 53.65 s |

Python startup and library imports are excluded. This is a single measurement, not warm-run statistics. The approximately 10-second target was not met.

The model generated 1,048,576 Gaussians; 306,374 with opacity > 0.005 were saved to PLY. All outputs were verified to be finite. Results are stored in the Git-ignored `FreeSplatter-O/outputs/headphones/` directory, configurable with `--output`.

- `gaussians.ply`: Standard 3DGS attributes: SH degree 1, log scale, opacity logits, and normalized wxyz quaternions. Saved in the model's reference-camera coordinates.
- `gaussians_raw.npz`: Unfiltered 23-dimensional raw outputs.
- `input_00.png`–`input_03.png`: Images actually passed to the model.
- `report.json`: Input paths, conditions, and processing times.
- `point_preview.png`: Diagnostic XY/XZ/ZY projections of 14,397 points with opacity > 0.05. This is not Gaussian rendering.

The projections show the headphone outline, but many background points remain. Only 53 Gaussians have opacity > 0.5, so a simple high threshold would discard most points. At this stage, camera estimation, Gaussian rendering, meshing, and dimensional accuracy had not been validated, and quality as a finished 3D model had not yet been assessed.

### Re-running inference after background removal

```bash
.venv/bin/python remove_background.py /path/to/headphone/photos --dark-object
.venv/bin/python infer_freesplatter.py FreeSplatter-O/inputs/headphones_rgba --crop-alpha --output FreeSplatter-O/outputs/headphones_nobg
.venv/bin/python preview_freesplatter.py --directory FreeSplatter-O/outputs/headphones_nobg
```

Background removal uses rembg 2.0.85 / U2Net / ONNX Runtime CPU. The first run downloads about 176 MB of weights to the Git-ignored `.cache/rembg/` directory. Original images are unchanged; transparent PNGs are saved under `FreeSplatter-O/inputs/headphones_rgba/`.

U2Net alone left part of the desk inside the headband, so `--dark-object` adds brightness- and brown-color-based corrections for these black headphones. This correction is not general-purpose and should not be used for white or brown objects. Reflective areas may be missing and some shadows remain; these are not precise masks. Omit the option to use only the U2Net mask.

The inference option `--crop-alpha` crops to the alpha > 127 region, then standardizes the input to a white background, 90% occupancy, and 512 px. The cable is included in the mask, so this differs from cropping only the main object body. The original results with backgrounds remain in `outputs/headphones/`.

The rembg code declares [MIT](https://github.com/danielgatis/rembg), and the upstream U2Net repository declares [Apache-2.0](https://github.com/xuebinqin/U-2-Net). The ONNX file used here is distributed by rembg. These declarations do not substitute for independently confirming permission for the converted ONNX weights.

Measurements after background removal: 1.33 seconds for four images, excluding 0.18 seconds for model loading; 51.06 seconds for FreeSplatter inference; and 55.06 seconds including inference-side loading and output. A total of 55,420 Gaussians with opacity > 0.005 were saved. A lower point count alone does not demonstrate better quality. The background-removal preview is `FreeSplatter-O/inputs/background_removal_preview.jpg`; the comparison PLY is `FreeSplatter-O/outputs/headphones_nobg/gaussians.ply`.

## DA3-BASE download, CLI usage, and test record

The currently adopted model is **DA3-BASE**. Its [official model card](https://huggingface.co/depth-anything/DA3-BASE) explicitly licenses the weights under Apache-2.0. It supports relative-depth and camera-pose estimation from multiple images. Other models, such as DA3-LARGE, may use different licenses, so these terms should not be assumed to cover all DA3 models.

```bash
# Download source and weights using the existing shared environment
.venv/bin/python download_da3.py
.venv/bin/python download_da3.py --local-files-only
# Create a Python 3.10 / CPU environment for DA3
bash setup_da3.sh
# Run inference on the same four photos
DA3/.venv/bin/python infer_da3.py /path/to/photos --limit 4
```

Pinned versions:

- [Official source](https://github.com/ByteDance-Seed/Depth-Anything-3): `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`
- [DA3-BASE weights](https://huggingface.co/depth-anything/DA3-BASE): `f4a6c9b3c95e41c82048423d3493a81ec3fa810e`
- Downloaded files: `model.safetensors` (about 542 MB), `config.json`, and model card `README.md`

```text
DA3/                                # Entire directory excluded by .gitignore
├── source/                         # Official source, configuration, and LICENSE
├── checkpoints/                    # Weights, configuration, model card, and download metadata
├── .venv/                          # Python 3.10 CPU environment
├── .venv-rocm/                     # Additional ROCm dependencies (references an existing ROCm environment)
├── uploads/                        # Photos and results saved through the GUI
├── trash/                          # Archived sets removed from the list
└── outputs/                        # Headphone, Shibuya Station, and performance-test results
```

Existing downloads are reused. The script stops without overwriting if the source revision differs or tracked files have been modified. Both code and weights use Apache-2.0. The license text is in `DA3/source/LICENSE`, and the model's license declaration is in the downloaded model card. Follow the Apache-2.0 requirements described above, including bundling the license, preserving relevant notices, and identifying changes when distributing.

The official DA3 package has Python and NumPy requirements that differ from the existing environment, so it is isolated in `DA3/.venv`. `requirements-da3.txt` defines the dependencies required for CPU geometry inference here, and `requirements-da3.lock` records all versions in the measured environment. Instead of installing the entire official package, the script loads the pinned source directly. xformers, gsplat, and Open3D are not installed. The startup message about missing gsplat concerns a 3DGS rendering dependency that this pipeline does not use.

### Output formats and execution conditions

DA3-BASE does not output 3DGS directly. Here, estimated depth is unprojected using camera intrinsics and transformed into common coordinates using w2c extrinsics, then saved as an **RGB point cloud**. This is neither a mesh nor a Gaussian PLY and may not display in viewers designed exclusively for 3DGS.

- `scene_points.ply` / `scene_points.glb`: Point cloud including the background.
- `prediction.npz`: Depth, confidence, intrinsics/extrinsics, and processed RGB images.
- `points.npz`: Point coordinates, colors, and input-image indices.
- `report.json`: Input paths, timings, and conditions.
- `input_00.png`, etc.: Processed input images.

On CPU, a subclass runs the official network in float32 rather than using the official API's automatic fp16 switching. Weights are fully checked with `safetensors.load_model(..., strict=True)`, which handles shared parameters. Images are processed sequentially by the official InputProcessor, resized to a long side of 504 and dimensions divisible by 14. The first image is the reference (`first`). The source is unchanged.

### Results for four headphone photos (2026-09-21)

The same original photos, `img_000.jpg`–`img_003.jpg`, were provided with their backgrounds. Each was 504×378 px; execution used CPU, 8 threads, and float32. Background-removed images were not used as model inputs. The earlier alpha masks were used **only to filter points after inference**. The bottom 40% of confidence values across all pixels were discarded, and object points were selected with alpha > 127. These are initial thresholds; point count or confidence alone does not establish quality.

| Operation or output | Measurement |
|---|---:|
| Model construction and weight loading | 0.35 s |
| Network inference | 1.92 s |
| Preprocessing, inference, and prediction conversion | 1.97 s |
| Loading through point-cloud output saving | 3.38 s |
| Point cloud including background | 457,229 points |
| Object point cloud selected by masks | 75,923 points |

This is one measurement excluding Python startup, library imports, model download, background removal, and viewer display. It does not demonstrate a 10-second time from submitting images to the first 3D display. All predictions were checked for finite values, and camera-rotation determinants were verified to be approximately 1.

```bash
DA3/.venv/bin/python infer_da3.py /home/your-user/room3dgs/data/sets/4b8f82bc/input \
  --mask-dir FreeSplatter-O/inputs/headphones_rgba
DA3/.venv/bin/python preview_da3.py
```

Masks must be RGBA files named `NN_<original-image-stem>.png`, covering the same field of view and image area as the originals. With `--mask-dir`, `object_points.ply` / `object_points.glb` are also generated. `preview_da3.py` uses these to generate:

- `point_preview.png`: Diagnostic projections from three directions.
- `viewer.html`: An offline point-cloud viewer opened in a browser. Drag to rotate and use the wheel to zoom. Display is subsampled to at most 40,000 points; PLY/GLB files retain all points.

The projections show the headband and ear-pad shapes, but there are misaligned surfaces and spread in the thickness direction. Geometric accuracy has not been fully validated. Subsequent user reviews of the point cloud and simple 3DGS were positive, leading to adoption as the current default pipeline. The result is also affected by the earlier imperfect masks. Unobserved back surfaces, dimensional accuracy, meshes, and novel-view 3DGS rendering have not been evaluated.

### Simple conversion from DA3 point clouds to 3DGS format

```bash
DA3/.venv/bin/python points_to_3dgs.py DA3/outputs/headphones/object_points.ply \
  --output DA3/outputs/headphones/object_3dgs.ply
```

`points_to_3dgs.py` converts each RGB point into a spherical Gaussian and saves it using the 3DGS PLY attribute format. It does not modify the original point cloud.

- Position: Preserves point coordinates. Only exact duplicate coordinates are merged, averaging their colors.
- Color: Converts RGB to SH DC coefficients. SH degree 3 attributes are provided for compatibility, with all 45 higher-order coefficients set to zero.
- Size: Estimated from the RMS distance to up to three neighbors, multiplied by the default `--scale-factor 0.75`. A cap limits excessively large isolated Gaussians.
- Opacity: Defaults to `--opacity 0.8`, stored as a logit in the PLY.
- Orientation: Identity quaternion (wxyz). Orientation has no effect on isotropic spheres.

The 75,923 object points were converted to 75,923 Gaussians. Conversion took about 0.16 seconds, producing an approximately 18.8 MB PLY. The saved file was reloaded to verify positions, recovered RGB, opacity, positive scales, unit quaternions, and finite values. Conversion settings are saved in `object_3dgs.json`.

The attributes required for 3DGS loading were verified, and the user rated the simple conversion positively when viewing it in Sculptly. The file is **`object_3dgs.ply`**; the original `object_points.ply` is a regular point cloud. Because this simple conversion uses no training or camera-based optimization, holes, bleeding, and surface misalignment may remain. The photo-optimized version is described next. This conversion does not fill unphotographed regions or correct geometry. If splats are too large, reduce scale-factor; if they are too small and gaps are visible, increase it and write to a separate output file.

### Optimizing 3DGS against the original photos

After the user rated the simple conversion positively in Sculptly, optimization against the four original photos was added while preserving the original `object_3dgs.ply`.

**Output for this test: `DA3/outputs/headphones/optimized_conservative/object_3dgs_optimized.ply`**

`optimize_3dgs.py` uses DA3 camera intrinsics/extrinsics and the processed original photos in `prediction.npz`. Target photos are composited onto white using the existing background-removal alpha masks. Adam optimizes color (SH DC), opacity, and spherical Gaussian size. Point positions, cameras, orientations, and higher-order SH coefficients remain fixed. No Gaussians are added or removed; the count stays at 75,923.

To preserve the satisfactory shape, RGB changes are limited to ±0.1 per channel on a 0–1 scale, and sizes to 0.67–1.5 times their initial values. The loss combines mask-weighted RGB L1 error, alpha silhouette error, and regularization against changes from initial values. Early trials produced uneven color, so the version reviewed here is `optimized_conservative`, which limits color changes.

Rendering uses this project's PyTorch implementation: perspective-projected covariance, a 0.3 pixel² low-pass filter, and depth-sorted front-to-back alpha compositing. Training samples 16 tiles of 8×8 pixels at a time; evaluation renders all pixels of the four images. The renderer supports only isotropic Gaussians and DC colors, rejecting anisotropic Gaussians or higher-order SH input. No gsplat build or additional pretrained weights are required. DA3 and background-removal model licenses remain as described above.

Re-run using the existing ROCm environment used for this test, without modifying that environment:

```bash
/home/your-user/RealtimeDepth/.venv-rocm10/bin/python optimize_3dgs.py \
  --input DA3/outputs/headphones/object_3dgs.ply \
  --prediction DA3/outputs/headphones/prediction.npz \
  --mask-dir FreeSplatter-O/inputs/headphones_rgba \
  --output-dir DA3/outputs/headphones/optimized_conservative \
  --steps 4000
```

Dependencies are PyTorch, NumPy, and Pillow. In another environment, install a compatible PyTorch build and replace the Python executable path. `--device cpu` is also supported, but the measurements below used Radeon 8060S / PyTorch 2.13.0+rocm10.0.0. No GPU PyTorch installation step was added to the CPU environment created by `setup_da3.sh`.

PNG masks in `--mask-dir` are read in filename order and matched one-to-one with the prediction images. They must be RGBA images covering the same image area as the originals. The four images in this test were used for training and evaluation at 504×378 px, with masks resized to that resolution.

| Metric (4 training images) | Before optimization | After optimization |
|---|---:|---:|
| Object-region RGB mean absolute error (0–1) | 0.09246 | 0.06422 |
| Object-region PSNR | 16.34 dB | 17.59 dB |
| Full-image RGB mean absolute error, including white background | 0.04979 | 0.02537 |
| Full-image PSNR, including white background | 15.40 dB | 18.79 dB |

The object region is defined by alpha > 0.5. Its mean absolute error decreased by about 30.5%. Training for 4,000 iterations took about 34.1 seconds; preparation, before/after rendering, and saving brought the total to about 38.0 seconds. Python startup, imports, DA3 inference, and background removal are excluded. This was a quality-validation operation and did not achieve an end-to-end pipeline within 10 seconds.

The output directory contains the following; the entire `/DA3/` directory is excluded by `.gitignore`.

- `object_3dgs_optimized.ply`: Optimized 3DGS; open this file in Sculptly.
- `comparison.jpg`: Target photo with background removed, before optimization, and after optimization from left to right; four viewpoints from top to bottom.
- `target_00.png` onward / `before_00.png` onward / `after_00.png` onward: Separate images for each viewpoint.
- `report.json`: Conditions, metrics, runtime, loss history, and PLY write-back validation results.

Before/after images showed reduced color unevenness and bleeding outside the silhouette, while missing details, multiple surfaces, and camera/geometry misalignment remained. The metrics above measure **fit to the same four training images** and do not guarantee improvement at unphotographed viewpoints. Rendering conditions may differ from Sculptly; the optimized version's appearance in Sculptly has not yet been checked.

Three validation tests passed, comparing compositing order, exclusion of points behind the camera, and opacity/size gradients against analytical values or finite differences. Coordinates after PLY reload exactly matched the originals. The maximum difference between rendering reloaded attributes and rendering immediately after training was 1.8×10⁻⁷.

```bash
/home/your-user/RealtimeDepth/.venv-rocm10/bin/python -m unittest discover \
  -s tests -p test_3dgs_renderer.py -v
```

### Shibuya Station simple 3DGS test (2026-09-21)

The same DA3-BASE → point cloud → simple 3DGS pipeline was run on photos from the existing set at `/home/your-user/room3dgs/data/sets/7c57ca12/input`. The four-view version used `img_000.jpg`–`img_003.jpg` in filename order, and the eight-view version used `img_000.jpg`–`img_007.jpg`. No background removal or photo-based optimization was performed.

Shared conditions: CPU with 8 threads, float32, 504×378 px per image, first image as reference, bottom 40% of confidence values across all pixels discarded, Gaussian opacity=0.8, and scale-factor=0.75.

| Measurement | 4 photos | 8 photos |
|---|---:|---:|
| DA3 network inference | 1.95 s | 4.40 s |
| DA3 loading, inference, and point-cloud saving (internal timing) | 3.21 s | 6.59 s |
| Point-cloud to simple 3DGS conversion (internal timing) | 0.66 s | 1.46 s |
| **Combined elapsed time for both processes, including startup, imports, and saving** | **6.31 s** | **10.49 s** |
| Gaussian count | 457,229 | 914,458 |
| 3DGS PLY size (decimal MB) | 113.4 MB | 226.8 MB |

Combined elapsed time was measured by launching DA3 inference and conversion sequentially from a parent process. It includes both Python startups and imports, model loading, image loading/preprocessing, and point-cloud/3DGS file saving. It excludes model and other downloads, classification, preview generation, and viewer display. Each condition was measured once; results vary with OS caches and other factors. The earlier headphone result of about 3.54 seconds sums internal timings and therefore covers a different scope.

Outputs:

- `DA3/outputs/shibuya_4views/scene_3dgs.ply`: Simple 3DGS from four photos.
- `DA3/outputs/shibuya_8views/scene_3dgs.ply`: Simple 3DGS from eight photos.
- `scene_points.ply` / `.glb` in each directory: Regular RGB point clouds.
- `point_preview.png` / `viewer.html`: Diagnostic point-cloud projections and offline viewer; these do not render Gaussians.
- `report.json` / `scene_3dgs.json` / `pipeline_timing.json`: Inference/conversion settings, timing breakdowns, and combined elapsed time.

Point-cloud projections show the mural, columns, floor, and ceiling. The four-view version still has gaps and surface misalignment; the eight-view version shows more noticeable overlap and misalignment between surfaces from different viewpoints. The eight photos cover a wider range of directions, so both photo count and coverage changed. These results do not establish that eight photos improve quality. All PLY attributes were checked for finite values, positive scales, unit quaternions, and camera-rotation determinants of approximately 1, but these checks do not guarantee geometric accuracy. After this test, the user also rated Shibuya Station as “well done,” supporting continued use of the simple pipeline alongside the headphone results. Separate user ratings of the four- and eight-view versions have not been established.

Re-run example; change the limit and output directory for eight photos:

```bash
DA3/.venv/bin/python infer_da3.py /home/your-user/room3dgs/data/sets/7c57ca12/input \
  --limit 4 --output DA3/outputs/shibuya_4views
DA3/.venv/bin/python points_to_3dgs.py DA3/outputs/shibuya_4views/scene_points.ply \
  --output DA3/outputs/shibuya_4views/scene_3dgs.ply
DA3/.venv/bin/python preview_da3.py --directory DA3/outputs/shibuya_4views \
  --cloud scene_points.ply --label '渋谷駅・4枚 DA3点群'
```

`preview_da3.py` supports selecting a point cloud with `--cloud`. When omitted, it uses the object point cloud if available, otherwise the scene point cloud. `--label` sets the HTML viewer's display name; the example retains the original Japanese label (“Shibuya Station, 4 photos, DA3 point cloud”). All generated files are excluded by the existing `/DA3/` entry in `.gitignore`.

### Local 3DGS viewer (ported from room3dgs)

The WebGL2 viewer from `/home/your-user/room3dgs/static/` was copied to `viewer/`. The original project was not modified. It uses no CDN and lists available generated results: the simple and optimized headphone versions, and the four- and eight-view Shibuya Station versions.

```bash
DA3/.venv/bin/python viewer_server.py --port 8080
```

This is an example of manual startup. Normally, use `./start_all.sh` / `./stop_all.sh`. Open **http://127.0.0.1:8080/** in a browser and select a result. Stop a manually started server with Ctrl+C in its terminal. Use `--port` to choose another port. The server uses Python, NumPy, and Pillow and listens only on localhost by default when launched manually; `./start_all.sh` enables external connections by default. Existing generated files are served as-is. See “Photo-selection GUI” below for saving new photos and generating results.

- Drag: Rotate around the model center. Right-drag: Pan.
- Ctrl+wheel: Move forward/backward. Normal wheel: Rotate.
- WASD/arrows: Move. Space/Shift: Move up/down.
- Number keys 0–7: Switch to the corresponding capture viewpoint, within the available photo count.
- The PLY download button saves the currently displayed result.

The viewer reads DA3 camera poses and starts at the first photo's viewpoint. A browser worker converts and depth-sorts standard 3DGS PLY data for Gaussian rendering. This is separate from the point-cloud `viewer.html`. The renderer does not use higher-order SH for view-dependent color; the simple PLY files generated here have zero higher-order SH coefficients. WebGL2 is required. The eight-view version loads about 227 MB into the browser.

The source project and modifications are documented in `viewer/NOTICE.md`. The Apache-2.0 license for the room3dgs-derived portions and the MIT license for the [antimatter15/splat](https://github.com/antimatter15/splat) renderer (Copyright © 2023 Kevin Kwok) are included in `viewer/licenses/`.

After the port, headless Chromium checks verified the result list, Gaussian rendering of the simple headphone version and both Shibuya Station versions, and viewpoint switching with number keys. There were no page JavaScript exceptions. Rendering screenshots are saved as `DA3/outputs/viewer_headphones.png`, `viewer_shibuya4.png`, and `viewer_shibuya8.png`.

The orbit center is the center of the bounding box of the loaded Gaussians' XYZ coordinates. Dragging, normal wheel rotation, and one-finger touch rotation share this center. Rotation remains centered on the model after panning or zooming. Run `node tests/test_viewer_orbit.cjs` to validate the rotation matrices.

### DA3 ROCm inference (Radeon 8060S, verified 2026-09-21)

`infer_da3.py` now supports `--device rocm` and `--dtype float32|float16`. The CPU version uses `--device cpu --dtype float32`, which remain the defaults. ROCm uses the `cuda` device in the PyTorch API, while reports record `backend: rocm`. Weights, model, preprocessing, and reference viewpoint are shared with the CPU version; the official DA3 source is unchanged.

The setup references an existing ROCm environment without modifying it and installs only additional DA3 dependencies inside this project.

```bash
bash setup_da3_rocm.sh
```

- Destination: `DA3/.venv-rocm/`. The CPU environment at `DA3/.venv/` is retained.
- Base environment: `/home/your-user/RealtimeDepth/.venv-rocm10/bin/python` by default; override with the `ROCM_PYTHON` environment variable.
- Verified environment: Python 3.14.3, PyTorch 2.13.0+rocm10.0.0, torchvision 0.28.0+rocm10.0.0, NumPy 2.5.2, and AMD Radeon 8060S Graphics. `torch.version.hip` is 7.15.26333.
- `rocm_base.pth` references packages in the existing environment. If that environment is removed or moved, setup must be repeated. This script does not install ROCm itself or GPU drivers.
- `requirements-da3-rocm.txt` pins the additional packages. Installation uses `--no-deps` to prevent dependency resolution from replacing ROCm PyTorch. torch, torchvision, NumPy, and OpenCV come from the existing environment. This combination must be revalidated for a different Python/ROCm environment.
- Environments, downloads, and validation outputs fall under the existing `/DA3/` and `/.cache/` exclusions. No additional DA3 weights are needed, and the license terms are unchanged.

Example using four Shibuya Station photos:

```bash
DA3/.venv-rocm/bin/python infer_da3.py /home/your-user/room3dgs/data/sets/7c57ca12/input \
  --limit 4 --device rocm --dtype float32 --output DA3/outputs/shibuya_4views_rocm
DA3/.venv/bin/python points_to_3dgs.py DA3/outputs/shibuya_4views_rocm/scene_points.ply \
  --output DA3/outputs/shibuya_4views_rocm/scene_3dgs.ply
```

`--dtype float16` uses GPU autocast for mixed-precision inference. Use float32 when prioritizing agreement with the CPU version. If the GPU is unavailable, the script raises an error rather than silently falling back to CPU. Point-cloud creation, PLY output, and simple 3DGS conversion remain CPU operations.

`--repeat 3` runs inference three times with the same loaded model and saves only the final prediction. Per-run times are recorded in `report.json` under `inference_runs`. The GPU is synchronized before and after timing, so the measurements cover execution rather than merely asynchronous kernel submission. `total_seconds` runs from after imports through saving and includes all repetitions when repeat is specified.

#### Inference speed and numerical agreement

Network inference times for four Shibuya Station photos, each 504×378 px, over three consecutive runs:

| Environment | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| CPU float32, 8 threads | 1.86 s | 1.71 s | 1.77 s |
| ROCm float32 | 6.87 s | 0.41 s | 0.35 s |
| ROCm float16 | 1.17 s | 0.25 s | 0.17 s |

The first GPU float32 test includes initialization and first-use kernel preparation. float16 was tested afterward, so these are not comparisons under identical cold-start conditions. Warm float32 inference was about 4–5 times faster than CPU. Four headphone photos produced float32 times of 1.02 / 0.40 / 0.36 seconds and 75,923 object points. Peak GPU allocated memory was about 1.4–1.7 GB; this is not total GPU memory consumption including drivers and other allocations.

Mean relative depth differences from CPU float32 were approximately 0.000034% for Shibuya Station GPU float32, 0.000031% for headphones GPU float32, and 0.0100% for Shibuya Station GPU float16. Processed input images matched. Depth, confidence, intrinsics/extrinsics, and camera rotations were checked for validity, including finite values. The CPU regression check exactly matched the original Shibuya Station prediction arrays. These checks measure differences from the CPU implementation, not accuracy against real-world ground truth.

#### From startup to saving simple 3DGS

After the tests above, new Python processes were launched to measure DA3 inference followed by simple 3DGS conversion on CPU.

| 4 Shibuya Station photos | Full inference process | Full conversion process | Total |
|---|---:|---:|---:|
| ROCm float32 | 5.96 s | 0.85 s | **6.82 s** |
| ROCm float16 | 5.52 s | 0.83 s | **6.34 s** |
| Earlier CPU float32 | 5.49 s | 0.82 s | **6.31 s** |

Each is a single measurement including both Python startups and imports, model loading/initialization, image preprocessing, inference, and point-cloud/3DGS saving. Classification, background removal, and the viewer are excluded. Disk/kernel caches had already been used before the GPU measurements. **These standalone runs did not demonstrate an overall speedup.** Keeping the model resident is useful for translating faster inference into a shorter total time, but these measurements did not use a resident service. The `start_all.sh` workflow described below subsequently added a resident ROCm model.

Measurements and comparisons are saved in `reports/da3_rocm_comparison.json`. Validation outputs are under `DA3/outputs/rocm_test/` in `fp32_headphones/`, `pipeline_float32_shibuya4/`, and `pipeline_float16_shibuya4/`. Previously accepted CPU outputs and the viewer's default list were unchanged.

### Photo-selection GUI (ported from room3dgs)

The room3dgs `index.html` / `app.js` files were copied to add photo-set selection, drag and drop, saving, generation, and viewing to the top page. Instead of the original WorldMirror reconstruction server, `photo_sets.py` runs the current DA3 → point cloud → simple 3DGS pipeline. Original room3dgs files were not modified.

For normal startup, use the script that keeps the ROCm model resident:

```bash
./start_all.sh
```

1. Open http://127.0.0.1:8080/.
2. Enter a set name and select 2–8 photos of the same subject; start with 4.
3. Click “Save this set” (このセットを保存).
4. On the saved card, select CPU or GPU (ROCm), then click “Create 3D” (3Dを作成).
5. When finished, click “View 3D” (3Dを見る). The viewer also provides a PLY download.

Supports JPEG, PNG, WebP, HEIC/HEIF, and MPO, up to 64 MB total and 30 million pixels per image. Photos are saved in the order selected by the browser and renamed on the server. GUI generation currently produces **simple 3DGS of the entire scene, including the background**. SigLIP classification, background removal, and additional photo-based optimization do not run automatically.

When started with `start_all.sh`, new sets default to the warmed-up GPU (ROCm). Starting `viewer_server.py` directly retains CPU as the default. GPU execution requires the environment prepared by `setup_da3_rocm.sh` and access to the GPU, and uses FP32. Only one generation job can run at a time. An error is displayed if another job is running; retry after it finishes. Progress and success/failure are reflected on the card. On completion, the card also shows generation time and Gaussian count.

- New sets: Uploaded photos in `DA3/uploads/<ID>/input/` (HEIC/HEIF and MPO are stored as converted JPEGs; their original containers are not retained), thumbnails in `thumb/`, and status in `meta.json`.
- Generated results: `runs/<run-ID>/` within the same set directory. Regeneration retains earlier results and switches the displayed result only after success. A failed regeneration does not lose the previous PLY.
- Logs: `generation.log` in each run directory. Jobs interrupted by shutdown are marked as errors on the next startup and can be regenerated manually.
- “Remove from list” (一覧から削除) archives photos and results to `DA3/trash/`. Permanent deletion and restoration through the GUI are not implemented.
- Up to 20 new sets are supported. The four existing headphone/Shibuya Station results are separate, read-only entries and cannot be regenerated or removed through the GUI.
- All photos and generated files are covered by the existing `/DA3/` entry in `.gitignore`.

Headless Chromium checks verified selecting and saving four photos, CPU generation, ROCm regeneration, 3D viewing, the PLY download response, and archiving from the list. Generation for the test set took about 6.4 seconds on CPU and 6.8 seconds on ROCm. These are generation-only times, excluding photo upload and browser loading. There were no JavaScript exceptions. The initial five tests also passed for upload validation, path restrictions, file preservation during archiving, rejection of removal during generation, and recovery from interruption.

```bash
DA3/.venv/bin/python -m unittest discover -s tests -p test_photo_sets.py -v
```

The current photo-set suite has seven passing tests, including four-image HEIC conversion and MPO primary-image extraction with orientation correction. For decode failures, the GUI identifies the photo number and detected format, while `run/server.log` records the decoder exception. MPO support resolved the reported iPhone upload failure; HEIC conversion was verified with generated test images.

### Server startup, shutdown, and ROCm initialization

```bash
./start_all.sh
# After startup completes: http://127.0.0.1:8080/

./stop_all.sh
```

`start_all.sh` launches the server in the background and **waits for ROCm initialization, DA3-BASE loading, and warmup to finish before reporting success**. Instead of launching a temporary initialization process and exiting, `da3_runtime.py` keeps the GPU model inside the server. ROCm generation from the GUI reuses the same dedicated thread and model, and point-cloud to simple 3DGS conversion also runs within the same process. New sets default to GPU in the GUI, with CPU also selectable. Existing sets retain their selected execution environment.

Warmup performs two inference runs on synthetic inputs with four images, 504×378 resolution, and float32. It does not create or modify input photos or generated results. Previously unused shapes, such as different photo counts or aspect ratios, may require additional first-use processing. No new weights are downloaded. Run `download_da3.py` and `setup_da3_rocm.sh` beforehand.

- Listening address: `0.0.0.0:8080` by default (external connections enabled). On the PC, `http://127.0.0.1:8080/` also works.
- Logs: `run/server.log`, appended. Readiness endpoint: `/api/health`.
- Control files: `run/server.json` / `run/server.pid`. These and the logs are excluded by `.gitignore`.
- Startup wait: 180 seconds by default. On failure or timeout, the launched process is cleaned up and the script returns exit code 1. It does not automatically switch to CPU if a GPU is unavailable.
- Duplicate startup: If already running with the same configuration, displays the URL and exits. Stop first before changing the configuration.
- Shutdown: Checks the PID, process start time, and startup identifier, then stops the dedicated process group launched by this script. The resident model and any running CPU child processes also terminate. Photos and completed results are not deleted. Sets interrupted during generation are marked with an interruption error on the next startup.
- Even with a stale PID, the script does not search process names to stop other projects in bulk. Stop any older manually launched server from its terminal before switching to these scripts.

Optional arguments:

```bash
./start_all.sh --host 127.0.0.1     # Restrict access to this PC
./start_all.sh --port 8081          # Change the port; HOST/PORT environment variables are also supported
./start_all.sh --cpu                # Skip the resident ROCm model and warmup
./start_all.sh --timeout 300        # Change the startup timeout
```

When started with `--cpu`, selecting ROCm uses the previous per-request process path. Use normal `./start_all.sh` startup for a resident GPU model. The scripts resolve paths relative to the project even when invoked by absolute path from another directory. Management uses Linux `/proc`, process groups, and the Python standard library; it does not use systemd or sudo.

#### Measurements with the resident model

After startup model loading and warmup, four Shibuya Station photos were processed twice through the same API used by the GUI.

| Resident ROCm FP32 | Run 1 | Run 2 |
|---|---:|---:|
| DA3 network inference | 0.356 s | 0.356 s |
| Photo loading → point cloud → simple 3DGS saving | **1.914 s** | **1.923 s** |

Both runs used the same server PID, reported `resident_model=true`, and had zero model-loading time per generation. Upload, HTTP wait, viewer loading, and server startup are excluded. Startup model initialization and warmup took about 4.0 seconds in this test, excluding the preceding Python startup and some imports.

The mean absolute depth difference from the same CPU reference was 3.2×10⁻⁷, and the Gaussian count also matched at 457,229. The CPU CLI path still exactly matched the existing prediction arrays. Results are recorded in `reports/resident_rocm_test.json`. Startup, duplicate startup, shutdown, and cleanup after port-conflict failure were exercised. At that measurement, four tests ensuring unmanaged PIDs are not stopped and five photo-set tests passed.

```bash
DA3/.venv/bin/python -m unittest discover -s tests -p test_server_control.py -v
```

The top of the photo-selection page displays connection URLs built from the PC's current IPv4 addresses and the server port. They refresh every 15 seconds and when the page regains focus. If the server is currently listening only locally, that is also indicated. To connect from an iPhone or another device, run `./stop_all.sh`, then `./start_all.sh`, and open the displayed URL from the same network. The IP display feature does not change the listening configuration by itself.
