# Viewer provenance

Copied from `/home/your-user/room3dgs/static/` on 2026-09-21.
Source repository HEAD: `2c64174d5dfb7ce2e7aa18a19f083d2c60444516` (working files copied).

- `viewer.html`, `viewer.js`, `style.css`, `index.html`, `app.js`: room3dgs, Apache-2.0 (license included).
- `splat-viewer.js`: room3dgs-vendored antimatter15/splat, MIT,
  Copyright (c) 2023 Kevin Kwok. https://github.com/antimatter15/splat
  Upstream license: https://raw.githubusercontent.com/antimatter15/splat/main/LICENSE

Local changes: project labels, error reporting, local-only dataset routes,
DA3 camera initialization and viewport-scaled focal lengths. Model list and
Python server are local additions. Original room3dgs files are unchanged.

Orbit controls now use the loaded Gaussian bounding-box center instead of a fixed camera-relative distance (2026-09-21).

Photo selection/upload/set-management GUI (`index.html`, `app.js`) copied from room3dgs and connected to local DA3 CPU/ROCm generation on 2026-09-21. Uploaded datasets are stored locally and removal archives their files.
