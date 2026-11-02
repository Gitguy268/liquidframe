# Third-party notices

LiquidFrame's project-owned code is MIT. Dependency code, native libraries, models, and sample media retain their own licenses. No Ente AGPL code or convert-gitguy268 GPL modules are copied into this project.

## Bundled UI assets

- Aiko, https://github.com/tw93/aiko, revision `6ae2c093d5bed31096354b72806374ab0848a2db`. The upstream README declares MIT. SVG viewBox, fill/stroke, and other presentation attributes are preserved. See `frontend/public/licenses/aiko.txt`.
- Liquid Glass Studio, https://github.com/iyinchao/liquid-glass-studio, revision `f7b28c36305a862f5cffed3ddd51511cf1204f56`. Copyright © 2024 Charles Yin, MIT. Original renderer and shader sources are bundled under `frontend/src/vendor/liquid-glass`; the generated shader module expands local includes. The integration adds lifecycle management, local photo backdrops, and accessibility fallbacks. Full MIT text: `frontend/public/licenses/liquid-glass.txt`.
- The welcome photo depicts colorful buildings, by Adrian Newell on Unsplash, distributed by the Liquid Glass Studio demo. It is sample media under the Unsplash license, separately from the renderer's MIT license. No Apple sample photos or videos are included.

## Processing libraries and models

- pyvips: MIT; libvips: LGPL-2.1-or-later; the pyvips-binary distribution used here declares LGPL-3.0-or-later. rawpy: MIT; bundled LibRaw: LGPL-2.1/CDDL. Binary wheels omit optional GPL demosaicing packs. Consult the installed distributions for native library notices.
- ImageMagick: ImageMagick license; LittleCMS: MIT. ImageMagick is a separately installed program. Optional JPEG XL programs: BSD-3-Clause.
- ONNX Runtime: MIT; OpenCV: Apache-2.0; PyTorch: BSD-3-Clause; Transformers: Apache-2.0; FastAPI: MIT; React: MIT; Vite: MIT; NumPy/SciPy: BSD-3-Clause; Pillow: HPND; watchdog: Apache-2.0.
- BiRefNet Lite ONNX: MIT, model revision and SHA-256 values recorded in `backend/openphoto/models.json`.
- LaMa ONNX from Carve: Apache-2.0, original model by advimman/lama. The 512×512 FP32 export uses opset 17.
- CLIP ViT-B/32: original OpenAI model and code MIT; quantized ONNX conversion by Xenova. Model revision and hashes are pinned in the manifest.
- YuNet: MIT; SFace: Apache-2.0, as declared by their OpenCV Zoo model directory licenses. Model versions and hashes are pinned.
- Real-ESRGAN: BSD-3-Clause, Copyright © 2021 Xintao Wang. The enhancement architecture is adapted from `SRVGGNetCompact`; original license is included in `frontend/public/licenses/real-esrgan.txt`. General/weak-denoise v0.2.5.0 weights are pinned by SHA-256.
- The optional inference test downloads NASA's public-domain astronaut Eileen Collins image from scikit-image v0.25.2. It is not added to a user's library automatically.

Models are optional assets downloaded on demand from the fixed URLs in the manifest. Their licenses are shown in Settings. Dependencies are not relicensed as MIT by this project.


## Reference projects and immutable revisions

The following references informed independently written catalog/media behavior. Their licenses do not replace the license of this application. No source modules from these repositories are currently vendored into the Python/React application.

| Project | Revision | Use and license boundary |
| --- | --- | --- |
| SilicaRAW | `c8e7e4c595ea69721c4bb51049b020969b9aed94` | Catalog, culling, history, migration and action-journal patterns. MIT license retrieved at that revision; full notice in `frontend/public/licenses/silicaraw.txt`. |
| darktable | `37d514c78c59e6ce3e5910223df160c6c4c53242` | CLI/XMP behavior reference. The optional separately installed GPL program is invoked with isolated staging/configuration; its code is not bundled or relicensed. Installed engine version is recorded separately. |
| PhotoPrism | `ac655ec1c5dc1b4beb0e85616892889352cf2d11` | Metadata/media-stacking/indexing behavior reference; AGPL source is not copied. |
| OwnPhotos | `180de5746468ec64b725723e03657dc21317f3a9` | Event/face-review patterns; independently implemented against the current local model stack. MIT notice retrieved at that revision in `frontend/public/licenses/ownphotos.txt`. Obsolete dependencies and external geocoding services are not integrated. |
| PcPhotos | `80a547f23a8f5030ec7c29bf434d36faddb0536f` | Behavioral reference only; no repository license was identified. No code, icons, artwork, or assets are copied. |

- MapLibre GL JS: BSD-3-Clause. Natural Earth geography and city points are public-domain data, prepared from `nvkelso/natural-earth-vector` revision `ca96624a56bd078437bca8184e78163e5039ad19`. Bundled local map data contain 243 city points and coarse country boundaries; satellite tiles are not bundled.
- DETR ResNet-50 quantized ONNX (Xenova) and DINOv2-small quantized ONNX (Xenova): Apache-2.0; pinned revisions, byte sizes, and SHA-256 values are in the model manifest.
- Argon2-cffi: MIT; ReportLab: BSD. Tesseract: Apache-2.0; ExifTool: Artistic/GPL dual licensing. These command-line tools are installed separately. FFmpeg licensing depends on the user's build and enabled components; it is not included in the source distribution.
- Test-only cat media downloaded from the Hugging Face documentation-images dataset are not bundled or installed in the user's library. Screenshots should use NASA/public-domain or separately attributed public samples.

Installed production web dependency license metadata and available full license/notice files are bundled under `frontend/public/licenses/npm/`. Setup refreshes them from the exact installed lockfile dependencies before building.

## Ente Photobook companion

Source: https://github.com/ente-toys/photobook, pinned revision
`f31313c771069506d2d49d0e2004009bde65ba51`. License: AGPL-3.0.
This is a separate static application under `companions/photobook/`, not a module
imported into LiquidFrame's MIT frontend. Copyright and license are retained in
that directory. Local changes and build instructions are in `LIQUIDFRAME.md`;
the running companion offers its full corresponding source at
`/photobook/source.zip`. Dependencies remain pinned in its own package-lock.json.
