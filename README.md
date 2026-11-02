# LiquidFrame

A local photo and media library with a neutral Photos-style interface, Aiko icons, and Liquid Glass controls. Photos, reversible edits, catalog data, and AI inference stay on your computer. The browser connects to a helper on `127.0.0.1`; there are no accounts, analytics, remote processing APIs, or cloud synchronization.

**Development preview, version 0.2.0.** See [FEATURE-STATUS.md](FEATURE-STATUS.md) for implemented features, verification, and remaining work. This project does not claim the complete behavior of Apple Photos, darktable, or PhotoPrism.

## Start

Open `start.command`. The app opens at **http://127.0.0.1:4320**. The old `openphoto` launcher redirects here.

Connect a folder or paste its path. Subfolders are indexed and originals are referenced in place. Single-click selects, double-click or Enter opens the viewer, and **Edit** opens the editor. Use Settings to choose appearance, install models, switch libraries, or configure private views.

## Install on another computer

Requirements: 64-bit Python 3.11 or newer, Node.js 22 LTS or newer for building, and a current desktop browser. Use a supported Python version with available native dependency wheels. Python 3.13 is used by CI and this Mac.

```sh
python3 scripts/setup.py
```

On Windows use `py -3 scripts/setup.py`. Launch with `start.command` on macOS, `start.cmd` on Windows, or `./start.sh` on Linux. After setup, Python serves the built interface; a Node development server is unnecessary.

Optional processing tools:

| Platform | Installation |
| --- | --- |
| macOS | `brew install ffmpeg tesseract exiftool imagemagick jpeg-xl` |
| Linux | Install FFmpeg with matching ffprobe, Tesseract, ExifTool, ImageMagick 7, and optionally libjxl through your distribution. |
| Windows | Install official FFmpeg, Tesseract, ExifTool, and ImageMagick 7 distributions and add their executables to PATH. |

After installing new codecs, rerun `python3 scripts/setup.py --force` to verify their encoders, then restart. Setup reports missing tools without silently replacing their functions. ImageMagick 6's `convert` program is not used. Install darktable separately to enable its optional RAW engine. macOS detection also recognizes `/Applications/darktable.app`.

The optional Mac adapter needs Xcode Command Line Tools:

```sh
.venv/bin/python scripts/build_macos_adapter.py
```

It exposes only implemented runtime capabilities. PhotoKit authorization requires an explicit user action. Network retrieval is disabled; download cloud-only originals through Photos before importing them. Windows/Linux physical-camera adapters and Cinematic focus editing remain unfinished.

## Library and editing

- Multiple libraries and connected folders; virtualized browsing, Years/Months/All Photos, saved sorting and navigation, search, ratings, flags, keywords, favorites, nested album folders, smart albums, and server-side large selections.
- A separate viewer with comparison, filmstrip, zoom, pan, source-component selection, and an information panel. Manual face boxes and reviewable people/pet suggestions stay local.
- Reversible photo recipes: lighting/color, curves/levels, selective color, black and white, crop/straighten/rotation/perspective, sharpening/denoise/vignette, clone/red-eye/blur/pixelation, and presets. RAW development uses LibRaw, with optional isolated darktable XMP processing.
- Local background removal (BiRefNet Lite), cleanup (LaMa), and restoration/upscaling (Real-ESRGAN). Optional CLIP search, YuNet/SFace people, Tesseract OCR, and DETR/DINOv2 pet suggestions. Models download on demand from pinned URLs and are checked by SHA-256.
- Local video playback/proxies, frame previews, trimming, constant playback speed, adjustments, crop, poster selection, and MP4 export. Verified Live Photo identifiers and RAW+JPEG pairs create stacks. Effects include Loop, Bounce, and Long Exposure.
- Offline Natural Earth map/city search, local curation, slideshow projects and playback, rendered slideshow video, and PDF/contact-sheet printing.

Some advanced workflows remain incomplete; consult the feature status instead of assuming every Photos feature is supported. A browser preview is an 8-bit display image, not the export master. Photo processing uses floating-point linear light and ICC handling, with 16-bit PNG/TIFF output where supported. AI stages use model sRGB precision; a 16-bit container does not restore source precision. The photo processing limit is 160 megapixels.

## Photobooks

Open **Projects → New photobook** to use the separately licensed Ente Photobook companion in a new tab. Or select up to 100 photos and choose **More actions → Create photobook from selection**, then confirm **Add selected photos to book**. Current edits are rendered as PNG copies up to 6000 pixels on the long edge; hidden items, trash and videos are rejected. You can also choose or drop local image files in the companion.

The editor retains upstream layouts, cropping, captions, book preview and PDF/PNG ZIP exports. It saves its current book in this browser, independently of LiquidFrame libraries. Reopening resumes that book; imported selections append to it. Export your book before clearing browser storage. Browser copies are not covered by LiquidFrame private-view locking. Cloud album import is disabled in this local edition.

Setup builds the companion automatically. To rebuild it alone, run `node scripts/build-photobook.mjs`. Its pinned source, dependencies, AGPL license and local modifications live separately in `companions/photobook/`; the editor offers a download of its corresponding source.

## Export and protection

Exports create new copies by default, with verified encodings, naming tokens, subfolders, output dimensions, color profiles, quality, precision, transparency background, metadata/location choices, and optional XMP. Animation/pages require conversion-only preservation or an explicit single-frame acknowledgment. Camera RAW is imported/developed; JPEG cannot be converted back into camera sensor RAW.

Unmodified-original export preserves source bytes and paired stack components. Embedded metadata/location remain part of a byte-identical original. Edited-copy export provides removal controls.

The editor's original-replacement option separately requires acknowledgment, a verified byte-exact backup, source-change checks, validated output, and atomic replacement. RAW files cannot be replaced with rendered pixels. Protected backups are never automatically purged. Restoration refuses to overwrite an externally changed replacement.

Removing an item moves it to a 30-day **catalog trash**. Expiration removes catalog membership and keeps a suppression record. Source files and protected backups are not automatically deleted.

## Local data and privacy

This upgraded installation retains `.openphoto-data/` for compatibility; a fresh installation uses `.liquidframe-data/`. It contains `catalog.sqlite3`, recipes/history, model packs, previews, derivatives, and backups. Additional libraries use `.liquidframe-data/` in their chosen folder; `.liquidframe-libraries.json` records local locations. `LIQUIDFRAME_DATA` overrides default storage; `OPENPHOTO_DATA` remains supported.

Back up the complete data directory while the helper is stopped, plus your separately referenced originals. Preview and temporary directories are regenerable. Models can be downloaded again. Preserve derivatives and protected backups alongside SQLite: the database alone is not a full media/edit backup.

Private views use a local Argon2id passcode, lock on reload/library changes, and expire after ten minutes of inactivity. Their endpoints and derivatives require authorization and are not browser-cacheable. This protects app access; other programs running as your operating-system user can still access source files. It is not filesystem encryption.

The helper checks session/origin/host access, binds to loopback, confines file operations to connected folders, blocks traversal and symlink escapes, and restricts codec delegates/protocols. Initial setup/model downloads need internet access. Installed processing and map data work locally afterward.

## Develop and contribute

```sh
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build
.venv/bin/python -m liquidframe --no-browser --port 4320
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [VERIFICATION.md](VERIFICATION.md), and [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). The legacy `python -m openphoto` command remains compatible. CI defines macOS, Windows, and Linux jobs; a configured workflow does not mean those remote jobs have been run.

LiquidFrame-owned code is MIT. The separate Ente Photobook companion is AGPL-3.0. Dependencies, models, map data, and sample media retain their own licenses. Apple artwork/fonts, unlicensed PcPhotos code/assets, and GPL/AGPL reference-project modules are not bundled as MIT code.
