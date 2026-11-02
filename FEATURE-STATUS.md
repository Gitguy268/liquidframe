# LiquidFrame feature status — 17 October 2026

This is a development preview. “Implemented” identifies working code paths, not complete parity with a mature photo application. The supplied behavior reference remains the acceptance target. A code path, a synthetic test, and verification on a physical device are separate claims.

## Implemented and exercised

- Ente Photobook companion in Projects, optional selected-photo import as edited PNG copies (up to 100 at a time, 6000 px long edge), local browser persistence, layout/crop/caption editing, preview and upstream PDF/PNG ZIP exports. Separate AGPL source and downloadable source offer; cloud import disabled. Books are independent of catalog libraries/private locking.

- Local browser/helper architecture, referenced folders, reversible recipes, original protection/restore, immutable library contexts, additive migration, loopback/origin/session protection, and private asset/derivative/job access checks.
- Neutral light/dark library; collapsible sidebar with fixed settings/activity; Years/Months/All Photos; grid zoom/aspect fit; saved navigation/sorting/scroll; separate viewer/editor, filmstrip, comparison, metadata inspector, keyboard actions, and large server-side selections.
- Titles/captions/keywords/ratings/flags/labels/locations/time shifts; smart-album conditions; nested album folders; album creation/membership/rename/delete history and recoverable folder disconnection; 30-day catalog trash and rescan suppression.
- Existing float/ICC/RAW processing plus curves/levels, selective color, black and white, details, perspective, crop handles, source-coordinate retouch, and filters. BiRefNet/LaMa/Real-ESRGAN inference and reversible derivatives.
- Local OCR and QR text display; CLIP search; reviewable people and pet/object suggestions; real DETR/DINOv2 cat detection/embedding; manual face-region selection; sampled video-frame indexing/query paths.
- Local FFmpeg/ffprobe discovery, video metadata, browser sources/proxies, frame preview/extraction, poster choice, trim/constant speed/adjustments/crop, and MP4 export. Synthetic video tests check dimensions, duration, audio presence, and unchanged source bytes.
- Source-component stacks, verified-identifier Live Photo association, and local Loop/Bounce/Long Exposure rendering paths.
- Natural Earth offline geography and 243 city points, location queries/assignment, time/place/quality curation, editable collection names and project selection.
- New-copy batch export with format read-back, precision/profile/dimensions/background, naming/subfolders, original components/sidecars, XMP, and metadata controls. Original-copy mode preserves source bytes including metadata.
- Slideshow project editing, browser playback, fade/cut, gentle motion, original generated instrumental, video export, PDF/contact-sheet layouts.
- Optional darktable XMP development on an isolated copy. A real NASA NEF produced an unsigned 16-bit TIFF; source hash stayed unchanged. Engine fingerprints are recorded for saved recipes.
- Optional Swift bridge builds and reports PhotoKit/depth runtime capabilities without requesting Photos permission. Network retrieval remains disabled.

## Remaining work before the complete approved scope can be called finished

- Complete action journaling for every organization operation; single-transaction duplicate merges with title/caption/metadata conflict review; complete folder/album move/merge/cover/custom-order controls and reorderable sidebar sections.
- Multiple simultaneous search chips, all metadata/object/QR facets, offline subject lookup beyond available object categories, richer multi-day trip/moment correction, and full people/pet group/favorite/key-photo/hiding controls.
- Selective copy/paste edit UI, per-group automatic/default adjustment controls, more complete RAW presets/XMP round trips, true source-resolution tiled inspection, and retouch after existing straighten/perspective transforms. Current retouch explicitly requests that those operations be applied later.
- HDR-to-SDR tone mapping and measured color verification; HDR export is unavailable. Current HDR input handling must not be represented as validated HDR processing. Speed ramps, frame-accurate multi-codec trim acceptance, and robust proxy playback coverage in Safari/Firefox remain to be completed.
- Ambiguous Live Photo association review, full key-frame/effect persistence/export UX, burst keeper review, actual depth/Portrait editor integration, Cinematic focus, and licensed/authorized Apple camera-mode fixtures.
- Import duplicate review/folder-to-album controls, complete relink/consolidation UI, Windows Portable Devices and Linux camera/MTP import adapters, physical camera/card tests, Apple-adjusted sidecar rendering, and damage-recovery workflows beyond integrity checks/backups.
- User-selected music, titles/subtitles, crossfades/fit-to-music, exact slide/video preview parity, and the full print fit/fill/custom-layout workflow. Browser slideshow preview currently excludes music; it is present in rendered exports.
- More accessibility polish (including every advanced curve), forced GPU/context-loss and reduced-preference simulations, prolonged rendering/cache soak tests, and a full 100k concurrent-indexing memory/performance measurement. The browser did reach the last page and select all 100,000 fixture entries with only 38 rendered tiles.
- Executed macOS/Windows/Linux CI, clean-machine setup checks, signed desktop distribution, and public repository/release configuration. CI definitions and launch scripts are included; remote CI and Windows/Linux hardware have not run in this session.

## Verification scope

The original 41-test suite is retained. Added tests cover library isolation, private histories/endpoints/jobs, migration, trash suppression, smart queries/snapshots, advanced masks/controls, actual OCR/video/audio, slideshow/PDF output, source revisions, and viewer query order. See VERIFICATION.md for the most recent exact results and the distinction between old baseline inference and new checks.

No personal media were inspected for UI quality assurance. Public samples and an isolated synthetic 100,000-entry/file fixture were used. The large generated file fixture was moved outside the home-folder library after the browser check.
