# Verification — 14 October 2026

The installed Mac build was tested with Python 3.13.16, Node 26, bundled libvips, ImageMagick 7, and the native JPEG XL tools. Measurements are local observations, not guarantees for other hardware or every camera/codec variant.

## Automated checks

- **41 backend tests passed.** Coverage includes path traversal and symlink confinement; incremental indexing and disconnected/missing sources; source and recipe conflicts; duplicates; API sessions, origin/host checks, and mutation protection; cancellable jobs; resumable exports; failed backup/write protection; atomic original replacement and restoration.
- Imaging checks cover EXIF orientation, transparency and opaque compositing, source ICC round-tripping, 16-bit PNG/TIFF gradients and HSL processing, selected animation frames, 24-megapixel full-resolution export, float derivatives, and preservation of original RGB/16-bit values outside AI cleanup regions.
- A **100,000-entry synthetic SQLite catalog** passed late-page pagination through both SQL and the asset API, with a bounded 120-item response. This exercises catalog scale; a complete 100,000-photo decode/analysis run has not been performed. The gallery virtualizes rows and retains at most 1,800 asset records in its page cache.
- Frontend TypeScript checking and production build passed.
- A harmless upstream Starlette TestClient deprecation warning remains in the test output.

## Actual local AI inference

All five model packs were downloaded from pinned locations and checksum-verified. The inference check then replaced the model downloader's HTTP client with a client that refuses network access. Public-domain NASA sample imagery was used, without processing personal photos for QA.

| Operation | Measured CPU time | Checked result |
| --- | ---: | --- |
| BiRefNet Lite background removal | 9.56 s | Subject mask with aligned dimensions |
| LaMa cleanup | 4.90 s | Pixels outside the painted region exactly unchanged |
| Real-ESRGAN 2× enhancement | 1.08 s | 64×64 input produced 128×128 output |
| CLIP image/text embedding | 2.01 s | Normalized 512-component embeddings |
| YuNet/SFace | 0.06 s | A face detected and embedded |

An additional small enhancement check used this Mac's MPS GPU successfully (1.44 s). CPU is the default. Automatic acceleration falls back to CPU if inference on the selected GPU fails. GPU failure injection and CUDA testing remain unverified.

The model report is `AI-VERIFICATION.json`. Small smoke-test timings are not full-resolution performance estimates. Inpainting and enhancement model inputs are 8-bit sRGB; cleanup retains source float pixels outside its mask, and cutouts retain source RGB with a generated alpha mask. Generated details cannot restore original sensor precision.

## Formats and RAW

**79 of 81 installed writers passed a real encode/read-back probe.** Failing RGF and SVG export are disabled in this installation. `FORMAT-SUPPORT.json` records each installed capability, tested writer, and failure. Formats vary with native codec installations; setup regenerates this report. A small successful probe cannot validate every depth, page, animation, profile, or source combination.

JPEG, PNG, TIFF, WebP, GIF, AVIF, HEIC, JPEG XL, BMP, and ICO round-trips were exercised, alongside installed ImageMagick writers. Validation rejects a PNG masquerading as BMP and verifies native format families, including codec aliases. A public NASA Nikon NEF fixture was developed with LibRaw, previewed, and exported as a full-resolution 16-bit TIFF. RAW support depends on LibRaw's camera support; camera RAW files are import/development sources and cannot be recreated from JPEG.

## Browser verification

The built app and actual localhost helper were exercised in the Codex in-app browser using a separate sample catalog:

- Folder connection, recursive indexing, date-grouped browsing, and local RAW/16-bit previews.
- Manual exposure adjustment, recipe saving, original comparison, and undo/redo.
- Actual background removal, reversible edit history, and transparent **16-bit PNG export**. The export reopened as PNG, 512×512, unsigned 16-bit, with a nonconstant alpha channel.
- Light and dark themes, accessible controls, dialogs, the glass on/off CSS fallback, and real WebGL Liquid Glass rendering using the current photo backdrop. The editor screenshot demonstrates the background-removal result and optical toolbar.
- Gallery thumbnails carry source/recipe versions so saved edits refresh their images.
- The installed launcher starts promptly while large-folder monitoring takes its first recursive snapshot in a background thread; a regression test covers request-thread responsiveness.

Glass is a UI overlay and never enters the helper's rendering recipe or export pipeline. CSS fallback, context-loss handling, hidden-surface pausing, resolution caps, and system reduced-transparency support are implemented. Forced context-loss, prolonged GPU soak testing, reduced-preference simulation, and every desktop browser remain unverified.

## Platform and installation status

macOS setup, launch, processing, models, and browser workflows were checked locally. Windows/Linux launchers and a three-platform GitHub Actions workflow are included, but Windows/Linux runtime and remote CI have not been executed. Filesystem permission/traversal/source-change/recovery failures have automated coverage; physically unplugging a drive and real power-loss fault injection were not performed.

The app binds to loopback, serves all interface assets locally, and has no outbound photo-processing API. Model downloads are the intended network operation. No packet-capture audit was performed. The existing connected catalog, recipes, downloaded models, and recovery data are preserved when installing into the final project directory.

## LiquidFrame 0.2 update — 15 October 2026

The original 41 tests remain. The expanded suite includes catalog migrations/context isolation, private-view expiry and dynamically private project jobs, trash suppression, query/viewer ordering, selection revisions, source-protected batch export, advanced adjustment masks/validation, real Tesseract OCR, synthetic FFmpeg trim/speed/audio, slideshow output and PDF printing. The latest final run is recorded below after source staging completes.

Additional actual checks:

- DETR ResNet-50 and DINOv2-small ONNX inference on a public test cat: detection confidence 0.99475 and a 384-component embedding. Both pinned files were content-hash verified; test-only media are not bundled.
- Installed darktable 5.4.0 developed a public NASA NEF to a 4286×2844 unsigned 16-bit TIFF, preserving source SHA-256. A separate attempted package-manager install was unavailable; the existing signed application was used.
- The optional Swift adapter compiled and reported PhotoKit/depth availability and Cinematic-focus unavailability. Photos authorization stayed off. No personal Photos library or physical device was accessed.
- A 100,000-entry catalog with 100,000 public-sample hardlinks was created in 36.71 seconds. Browser browsing reached the last page (2,940,328px scroll position) with 38 mounted tiles. Select-all reported 100,000 without loading all asset objects. This does not establish a precise memory ceiling or concurrent-indexing throughput.
- Light/dark public-sample library, persistent sidebar, explicit viewer entry, information/face-region UI, expanded export options, and keyboard navigation were checked in the in-app browser. A dialog foreground-color inheritance bug found in the light theme was corrected. A thumbnail cache file-race was corrected to ignore temporary files and handle concurrent disappearance.

Known limitations are maintained in FEATURE-STATUS.md; they are not counted as verified capabilities. In particular, HDR processing, Apple camera modes, physical devices, Windows/Linux runtime/CI and prolonged GPU/cache testing remain unverified or incomplete.

Final staged check on 15 October 2026: **58 tests passed**, including the original 41. Frontend TypeScript and production build passed. The main interface bundle is about 457 kB before compression (134 kB gzip); MapLibre is loaded separately when Places opens (about 1.04 MB before compression). A build warning remains for the optional MapLibre chunk. The test run reports a Starlette/httpx deprecation warning; no test failures.

Final privacy/recovery regressions also passed: hiding a photo revokes access through an earlier asset object, person/pet mutations require private authorization when their group contains private items, slideshow jobs retain their source dependencies after project deletion, and disconnecting a folder preserves recipes and is undoable.

## Ente Photobook integration — 17 October 2026

- All **63 backend tests passed**, including five new companion tests. These cover local session/mutation checks, static routes and missing assets, scoped CSP/source download, edited PNG copying without source modification, selection exclusions/limits, cross-library isolation, and hidden/trash/video rejection even with an active private lease.
- LiquidFrame TypeScript/production build and the separately pinned Photobook Next.js static production build passed. The companion build emits an upstream async-WebAssembly target warning in the disabled Ente cloud-import dependency.
- The localhost helper and in-app browser were exercised using three generated geometric images in an isolated library: Projects launcher, explicit selection import, restored browser book after reload, page editing/preview navigation, and PDF export completing without console errors. The Projects card was visually checked in dark mode.
- The companion uses local system fonts and prefixed local image/WASM/ICC assets. Its scoped CSP allows hash-matched hydration scripts and local WASM; it does not allow remote connections. LiquidFrame's existing CSP remains unchanged elsewhere. Source ZIP contains the complete modified companion source, dependency lockfile, license and build instructions.
- No personal photos/catalog were used for this verification. Windows/Linux and other browser engines, exhaustive formats/print color validation, narrow layouts, light theme and keyboard-only navigation were not exercised for this addition.
