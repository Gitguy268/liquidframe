# macOS Photos (macOS 27): behaviour spec for openphoto

**Purpose.** A clean-room description of *what* Apple Photos does, for an agent improving `~/openphoto`. It contains no Apple code, no decompiled output and no copied UI text. Build each feature in openphoto's own way and voice. Do not copy Apple's icons, artwork or wording.

**How this was made.** From Photos.app's public bundle metadata (Info.plist document types, resource and plug-in file names, names of linked system frameworks), its English UI string tables (used only as a feature inventory) and general product knowledge. No binary was disassembled.

**openphoto status key.** ✅ have · 🟡 partial · ❌ missing · ⛔ out of scope (cloud, Apple-account or device-only; openphoto is local-only by design).

openphoto today (from `backend/openphoto/api.py`, `store.py`, `frontend/src/*.tsx`): connected folders, an asset grid with month groups, favorites, flat albums, presets, a recipe-based editor (exposure, contrast, highlights, shadows, whites, blacks, temperature, tint, saturation, vibrance, sharpen, denoise, vignette, straighten, rotate, flip, crop, one RGB curve, global HSL), RAW develop, AI background removal / cleanup / enhance, people (faces), CLIP semantic search, duplicates, export jobs, backups. No video, map, ratings, keywords, captions, hidden, trash, smart albums or slideshow.

---

## 1. App layout

| Photos behaviour | openphoto |
|---|---|
| One window with a collapsible **sidebar**, a **toolbar** and a content area. The sidebar can be shown or hidden. | 🟡 |
| Sidebar sections: Library; Collections (Memories, Pinned, Favorites, Recently Saved, People & Pets, Trips, Featured Photos, Wallpaper suggestions); Media Types; Utilities; Albums ("My Albums", shared albums); Projects. Users can reorder and collapse sections, and pin any collection. | 🟡 (folders, albums, people, duplicates only) |
| **Media Types** smart collections, built automatically from metadata: Videos, Selfies, Live Photos, Portrait, Panoramas, Time-lapse, Slo-mo, Cinematic, Bursts, Screenshots, Screen Recordings, Spatial, RAW, ProRAW, Animated, Long Exposure. | ❌ (an extension filter only) |
| **Utilities**: Imports (grouped by import session), Duplicates, Hidden (locked until authenticated), Recently Deleted (locked), Receipts/Handwriting/Illustrations/QR codes (detected categories), Recently Edited, Recently Viewed, Recently Shared. | 🟡 (Duplicates only) |
| **Library zoom levels**: Years → Months → All Photos, switched with a segmented control. Years and Months show one curated "key photo" card per period. All Photos is a dense grid with pinch/slider zoom (roughly 1–20+ columns) and an aspect-fit or square-crop toggle. | 🟡 (one grid with month headers) |
| Grid header shows the date range and place names for the visible section. | ❌ |
| **Info panel** (⌘I, floating): title, caption, favorite heart, keywords, date and time, camera/lens/ISO/focal length/aperture/shutter/exposure bias/flash/metering, dimensions, file size, format, file name, faces (named), a mini map with location, and the "Imported on" date. With a multi-selection it shows a summary and lets you edit fields in bulk (shows "Various…" when values differ). | 🟡 (faces in info panel) |
| Toolbar search field with live suggestions. | 🟡 |
| Full-screen mode, dark appearance follows the system. | ✅ (browser) |

## 2. Library and organization

| Photos behaviour | openphoto |
|---|---|
| **Albums**: create (empty or from a selection), rename, delete (photos stay in the library), duplicate, merge two albums, set a cover photo, remove items from an album. | 🟡 (no duplicate/merge/cover) |
| Album **sort**: custom (drag to reorder), oldest first, newest first, by title. "Keep sorted by…" persists per album. | ❌ |
| **Folders** that hold albums and other folders, nested. Move albums in and out; deleting a folder deletes the albums inside it (with a warning) but never the photos. | ❌ |
| **Smart albums**: saved queries with "match any/all" and N condition rows. Each row is field + operator + value. Fields include album, date captured, date added, date edited, description/caption, face/person, filename, keyword, text, title, photo kind (favorite, hidden, edited, RAW, Live, Portrait, panorama, screenshot, video, burst, etc.), camera model, lens, ISO, aperture, focal length, shutter speed, flash (on/off), location/place. Operators: is / is not, contains / does not contain, starts with, is before / after / in the range / in the last N days-weeks-months-years, greater / less than. The album updates live. | ❌ |
| **Favorites** (heart, `.` key toggles). | ✅ |
| **Star rating / Set Rating / Remove Rating** (present in strings, used by smart albums and print captions). | ❌ |
| **Keywords**: a global Keyword Manager (create, rename, delete, favorite keywords, single-key shortcuts that toggle a keyword on the selection), assigned from the info panel as tokens. | ❌ |
| **Title and caption** per photo, editable in bulk. | ❌ |
| **Hide / unhide**: hidden items leave every view except the Hidden album, which can be hidden from the sidebar and locked behind authentication. | ❌ |
| **Recently Deleted**: deleting moves items there for 30 days, with a days-remaining badge on each thumbnail. Recover or Delete Immediately; "Delete All". Hidden items deleted this way become visible in Recently Deleted. Deleting part of a burst keeps the burst. | ❌ (openphoto never deletes originals, so this would be a catalog-level "remove from library" with undo) |
| **Duplicates**: groups of exact and near-exact copies. "Merge" keeps the best-quality version and merges metadata (albums, keywords, captions, favorites) into it; the other copies go to Recently Deleted. | 🟡 (review-only by design) |
| **Undo/redo** for every library action (rename, move, favorite, keyword, delete, rotate, date change…), with a descriptive label such as "Undo Change Keywords". | ❌ (editor undo only) |
| **Referenced vs managed files**: files can be imported by reference (left in place) and later "consolidated" (copied or moved) into the library. Missing referenced files show an offline badge; "Locate Referenced File…" relinks them. | ✅ (openphoto is reference-only; missing drives are kept) |
| **Multiple libraries**: create, open or switch libraries (holding Option at launch opens a library chooser). One library is the "System Photo Library". Repair Library rebuilds the database. | ❌ |

## 3. Search and intelligence

| Photos behaviour | openphoto |
|---|---|
| Natural-language search across scenes, objects, text in images (OCR), people, places, dates, captions, keywords, file names and media types. The search box tokenises queries into chips ("dog" + "beach" + "2023"), shows result counts per suggestion, and searches inside video frames. | 🟡 (CLIP + filename/EXIF) |
| **Live Text**: select or copy text in photos; detect and link phone numbers, dates and URLs. | ❌ |
| **Visual Look Up / Copy Subject**: identify plants, animals, landmarks and art; lift the subject out as a cutout (drag or copy). | 🟡 (background removal exists in the editor) |
| **People & Pets**: automatic face and pet clustering; name, favorite (pinned to the top), merge, "This is not X" (reject a face), add a face manually, "Feature this person less", hide from People, sort the People view (custom or by name), and set the key photo. Unnamed clusters are suggested with a confirm-additional-photos flow. Groups of people. | 🟡 (name/merge/reassign; no pets, favorites, reject, hide or groups) |
| **Places**: a world map with clustered photo pins, zoom-to-split clusters, a map/satellite toggle and a grid of photos for the visible region. Assign a location manually, hide a location, revert to the original location. | ❌ |
| **Memories**: auto-generated story videos (theme music, titles, Ken Burns motion) from trips, people, pets and dates. Favorite or delete memories, feature less, edit title/subtitle, change music and look, export as video, and "Create Memory" from an album or a prompt. | ❌ |
| **Trips** and **Featured Photos** collections, auto-curated. | ❌ |
| **Moments**: time and location clusters inside All Photos; split or merge moments, edit the moment title. | ❌ |

## 4. Viewer

| Photos behaviour | openphoto |
|---|---|
| Double-click opens a single-item viewer. Arrow keys go to the previous/next item, space plays video/Live, Escape returns to the grid, and the grid scroll position is kept. | 🟡 (opens the editor directly) |
| Filmstrip of thumbnails along the bottom (show/hide). | ❌ |
| Zoom to 100% or fit, pinch or slider zoom, pan by dragging. | ✅ (editor) |
| **Compare** two to four selected photos side by side. | ❌ |
| **Live Photos**: hover or press to play; effects Live / Loop / Bounce / Long Exposure; turn Live off; choose a new key frame. | ❌ (no video) |
| **Video**: play/scrub, mute toggle, trim (in/out handles), set poster frame, save a frame as a photo, save a trim as a new clip, Slo-mo speed-ramp range, Cinematic focus-point editing (click to change focus, auto/manual tracking toggle). | ❌ |
| **Bursts**: one stack; "Make a Selection…" picks the keepers, then "Keep Everything" or "Keep Only Selection". | ❌ |
| **RAW+JPEG pairs** are one asset. "Use RAW as Original" / "Use JPEG as Original"; Duplicate RAW as HEIC. | 🟡 (RAW develop; no pairing) |
| **Slideshow**: instant slideshow from a selection, plus saved slideshow projects with theme, music, duration (fit to music or a fixed time), transition, scale-to-fit, loop, and export to video. | ❌ |

## 5. Editing

General model: **non-destructive**. Edits are stored as an adjustment stack. The original is always kept. Revert to Original removes all edits. Edited items show an "Edited" badge and appear in a Recently Edited collection. **Show original**: hold `M` (Photos) to see the original. (openphoto uses `B`, which is fine.)

Editor layout: three tabs at the top — **Adjust**, **Filters**, **Crop**. Plus a toolbar with Auto Enhance, rotate, favorite, Done/Revert, a "Show photo without edits" button and an "Edit With → external app" menu. Edit extensions (third-party editors) appear as extra tools.

| Photos behaviour | openphoto |
|---|---|
| **Auto Enhance** (one click, analyses the image and sets Light/Color/etc.). Toggle off with "Remove Auto Enhancements". | ✅ (`/auto`) |
| **Copy Edits / Paste Edits**: copy the full adjustment stack and paste it onto one or many selected photos, choosing which groups to include. | 🟡 (presets) |
| **Default adjustments**: "Add to Default Adjustments" makes a panel always visible. "Save as Default" stores a panel's current values. | ❌ |
| Each adjustment group has an on/off checkbox, an "Auto" button, a reset arrow, a collapsed master slider and an expanded detail view. | 🟡 (simple vs advanced) |
| **Light**: master slider plus Brilliance, Exposure, Highlights, Shadows, Brightness, Contrast, Black Point. | 🟡 (no Brilliance or Brightness, as separate) |
| **Color**: master slider plus Saturation, Vibrance, Cast. | 🟡 (no Cast) |
| **Black & White**: master slider plus Intensity, Neutrals, Tone, Grain. | ❌ |
| **White Balance**: modes Neutral Gray (eyedropper), Skin Tone (eyedropper and face strength), Temperature/Tint (sliders + eyedropper). RAW presets: Daylight, Cloudy, Shade, Tungsten, Fluorescent, Flash, Kelvin, Custom, Auto. | 🟡 (temperature/tint; no eyedroppers) |
| **Curves**: separate RGB, Red, Green and Blue curves; black-point, mid-point and white-point eyedroppers; add-point mode with a crosshair cursor; Auto. | 🟡 (one RGB curve) |
| **Levels**: luminance and per-channel RGB histogram with black / shadow / mid / highlight / white handles for input and output; Auto. | ❌ |
| **Definition** (local contrast): Intensity. | ❌ |
| **Selective Color**: six colour swatches plus a custom hue picker (eyedropper). Each has Hue, Saturation, Luminance and Range. | 🟡 (global HSL only) |
| **Noise Reduction**: Amount. For RAW: Luminance, Detail, Color noise. | ✅ |
| **Sharpen**: Intensity, Edges, Falloff. | 🟡 (amount only) |
| **Vignette**: Strength, Radius, Softness. | 🟡 (amount only) |
| **Red-eye**: auto, or click each eye. | ❌ |
| **Retouch** (brush): click and drag over spots; Option-click sets the source area; size slider. | 🟡 (AI cleanup mask) |
| **Clean Up** (generative): click, brush or circle objects to remove; protect faces (pixelate a face to redact it); reset. | ✅ (LaMa cleanup) |
| **Portrait / Depth**: change the focus point and depth (f-number) after capture; portrait lighting looks Natural, Studio, Contour, Stage, Stage Mono, High-Key Mono, with intensity. | ❌ (needs depth data) |
| **Histogram** panel (toggle). | ✅ |
| **Filters**: a grid of named looks (vivid, dramatic, warm, cool, mono, silvertone, noir and so on) with a live thumbnail of the current photo, plus an intensity slider. Filters apply to many photos at once from the grid. | 🟡 (presets; build openphoto's own named looks) |
| **Crop tab**: free crop handles, straighten dial (±45°), vertical and horizontal **perspective** keystone, aspect presets (Freeform, Original, Square, 16:9, 3:2, 4:3, 5:4, 5:7, 8:10, Custom W×H, Landscape/Portrait toggle), flip, rotate, a one-click auto-level-and-crop button, and reset. | 🟡 (no perspective, aspect presets or auto-straighten) |
| **Styles** (newer "photographic styles" re-render for supported photos). | ❌ |
| **Edit video**: same Adjust/Filters/Crop tools applied to video frames, plus trim. | ❌ |
| **Edit With** external app, with a round trip back into the library. | ❌ |
| Unsaved/incompatible edit warnings: e.g. "Continue editing JPEG?" when a RAW+JPEG pair is opened; "Reprocess RAW" when the RAW engine changes. | 🟡 (source revisions) |

## 6. Import and export

| Photos behaviour | openphoto |
|---|---|
| **Import** from folders, files, cameras, cards and phones. A review grid shows new items vs already-imported ones, with an option to import into an album, "Keep Folder Organization" (turns subfolders into albums), and "Delete items after import". A duplicate prompt offers Import / Don't Import / Apply to all. A progress and error panel lists unsupported files. | 🟡 (connect folders; no device import) |
| Drag-and-drop files into the window or onto an album. | ❌ |
| **Imports** collection, grouped by import session and date. | ❌ |
| Sidecars understood: XMP (keywords/ratings/captions), AAE (edits), and Live Photo pairs (image + MOV). | 🟡 (EXIF only) |
| **Export (modified)**: format (JPEG, TIFF, PNG, HEIC), JPEG quality (low/medium/high/max), colour profile, size (full, small, medium, large, custom max edge), include title/keywords/caption, include location; movie quality; file name (current title, current file name, sequential with prefix); subfolder format (none, moment name). | 🟡 (no title/sequential naming or moment folders) |
| **Export Unmodified Original**: the original bytes plus an optional XMP sidecar with IPTC; file name and subfolder rules as above. | 🟡 |
| Export a Live Photo as GIF; export a frame of a video; export a memory or slideshow as a movie. | ❌ |
| File-naming tokens: image date/day/month/year/time, current date, counter or sequence number, album name, project name, original file name, version name, custom text. | ❌ |
| Errors are collected per item; "Export completed with errors" shows a list. Quitting during an export asks for confirmation. | ✅ (job errors) |

## 7. Metadata editing

| Photos behaviour | openphoto |
|---|---|
| **Adjust Date and Time**: change capture time for one or many photos. Multi-select shifts all of them by the same offset relative to the first, with a time-zone picker. | ❌ |
| **Assign Location**: type to search places, or drop a pin; works on multiple photos. Hide location. Revert to original location. | ❌ |
| Title, caption and keywords as in §2, written to export metadata. | ❌ |
| Rename (title only, not the file). | ❌ |

## 8. Printing and projects

| Photos behaviour | openphoto |
|---|---|
| **Print**: printer, paper size presets (4×6, 5×7, 8×10, 10×15 cm, 13×18 cm, 20×25 cm, 2L, 6P, custom), layout (Standard, Contact Sheet, Custom), Fit vs Fill, and optional captions from metadata (title, description, keywords, filename, date, camera, ISO, flash, rating). | ❌ (the browser print dialog could cover a basic version) |
| **Projects** via extensions (books, calendars, cards). | ⛔ |

## 9. Sharing and sync (described for completeness)

| Photos behaviour | openphoto |
|---|---|
| iCloud Photos sync, "Optimize Mac Storage", Download Originals. | ⛔ |
| Shared Albums (invite, comments, likes, public website). | ⛔ |
| Shared Library (with participants, auto-share rules, a per-item "Shared/Personal" toggle). | ⛔ |
| Share sheet (Mail, Messages, AirDrop, Notes). | ⛔ (a "Reveal in Finder / copy file" action is the local equivalent) |

## 10. Settings

| Photos behaviour | openphoto |
|---|---|
| **General**: library location / make it the System Photo Library; "Importing: copy items to the Photos library" toggle; metadata (persons/pets shown); autoplay videos and Live Photos; show Memories/Holiday events; HDR display (show full dynamic range); sharing options; reset suggested Memories and People. | 🟡 |
| **iCloud** and **Shared Library** panes. | ⛔ |

## 11. Keyboard shortcuts (stable, well-known Photos defaults)

The live menu-bar dump was **not** captured (Terminal lacked Accessibility permission), so this list is the documented subset. Grant Accessibility and re-run the menu dump if you need the complete table.

| Action | Keys | openphoto |
|---|---|---|
| Get Info | ⌘I | ❌ |
| Edit / exit edit | Return | 🟡 |
| Adjust / Filters / Crop tab | A / F / C | ❌ |
| Auto Enhance | ⌘E | ❌ |
| Show original while held | M | ✅ (`B` toggle) |
| Rotate counter-clockwise / clockwise | ⌘R / ⌥⌘R | ❌ |
| Favorite | . | ❌ |
| Hide | ⌘L | ❌ |
| Delete (to Recently Deleted) | ⌫ | ❌ |
| Delete immediately from library | ⌘⌫ | ❌ |
| New album with selection | ⌘N | ❌ |
| New empty album | ⌥⌘N / ⇧⌘N | ❌ |
| Copy / paste edits | ⇧⌘C / ⇧⌘V | ❌ |
| Duplicate | ⌘D | ❌ |
| Select all / none | ⌘A / ⇧⌘A | 🟡 |
| Zoom in / out (grid and viewer) | ⌘+ / ⌘− | 🟡 |
| Show/hide sidebar | ⌥⌘S | ❌ |
| Search | ⌘F | ✅ (⌘K) |
| Export | ⇧⌘E | ❌ |
| Import | ⇧⌘I | ❌ |
| Adjust date and time | (menu) | ❌ |
| Slideshow / play | (menu) / Space | ❌ |
| Undo / redo | ⌘Z / ⇧⌘Z | 🟡 (editor only) |

## 12. Supported formats (Photos' Info.plist)

The package types are Photos, Aperture and iPhoto libraries. All other files are opened as a generic viewer ("*"). Sidecars: XMP, AAE, SLM (slow-motion). Private Live Photo bundles. Image I/O handles everything else: HEIC/HEIF, JPEG, PNG, TIFF, GIF, WebP, AVIF, JPEG XL, DNG/ProRAW and most camera RAWs, PSD (flattened), and video formats H.264/HEVC/ProRes. openphoto's `FORMAT-SUPPORT.json` already exceeds this for stills. The gap is **video and Live Photo pairs**.

---

## Suggested priority for openphoto (local-only, biggest gaps first)

1. **Library hygiene**: hide/unhide, a catalog-level Recently Deleted with undo, ratings, keywords, titles and captions, and library-wide undo.
2. **Smart albums and folders of albums**: they use metadata openphoto already indexes.
3. **Viewer mode** separate from the editor: arrow-key navigation, filmstrip, compare, info panel (⌘I) with bulk edit.
4. **Editor parity**: per-channel curves, Levels, Selective Color, Black & White, Definition, white-balance eyedroppers, Sharpen/Vignette detail controls, perspective crop with aspect presets and auto-straighten, copy/paste edits with a group chooser, and named filters with intensity.
5. **Places map** from EXIF GPS (Leaflet + OSM tiles would break the local-only promise; use offline tiles or a vector world map) and **Adjust Date/Location**.
6. **Video and Live Photo** playback, trim and poster frame.
7. **Memories/slideshows**: export a slideshow as video.
8. **Keyboard shortcuts** from §11.

Check each against openphoto's privacy rules in `README.md` (loopback-only, no remote APIs) before building.
