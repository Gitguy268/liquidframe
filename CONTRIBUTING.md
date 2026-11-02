# Contributing to LiquidFrame

## Run locally

Follow README setup instructions, install the `test` extra, run `python -m pytest -q`, and build the frontend with `npm --prefix frontend run build`. Use an isolated `LIQUIDFRAME_DATA` directory and a public or expressly authorized sample folder. Never use your private library as a test fixture.

## Architecture

- `frontend/src/App.tsx`: library shell and navigation; `Gallery.tsx`: bounded paginated gallery; `Viewer.tsx`: browsing; `Editor.tsx` / `AdvancedControls.tsx`: reversible photo editing; `VideoEditor.tsx`: video editing.
- `backend/openphoto/workspaces.py`: immutable per-library contexts. Background jobs must capture their context; never replace a global path while another job runs.
- `catalog.py`: queries, selections, metadata, albums, history, trash. `store.py`: SQLite, confinement, revision checks, recipe persistence, cache.
- `imaging.py` / `adjustments.py`: float photo processing; `media.py`: FFmpeg processing; `models.py` / `intelligence.py`: local inference; `native.py`: optional external adapters; `deliveries.py`: export/projects/print.
- `api.py` retains compatible endpoints. `api_more.py` contains additional domains. The internal package name remains `openphoto`; `liquidframe` is the public launch alias.

## Changes and review

Describe the user-visible problem and resulting behavior. Add meaningful regression tests for processing, privacy, migrations, original protection, large-catalog queries, or recovery changes. Build/type-check UI changes and verify them in both themes, with keyboard navigation, narrow layout, and glass disabled. Record untested platform behavior clearly.

Keep pixels separate from UI decoration. Never export glass, selection overlays, text-recognition boxes, or retouch guides. Keep source precision/ICC behavior explicit. Do not overwrite originals without the existing backup and validation flow. Never silently change the requested file encoding.

Private access must be checked at every file, derivative, query, aggregate, export, project, and job boundary, including after an item is hidden. Avoid private filenames in unlocked-independent logs and job messages. Do not add telemetry or outbound photo-processing requests.

Use additive, restart-safe migrations and back up an existing catalog before changes. Preserve old recipes' rendering behavior. Use server-side selection snapshots for large operations, bounded pages/caches, and cancellation/progress for long work.

## Dependencies and licensing

Pin imported source revisions and retain license notices. Models/data packs require revision, SHA-256, byte size, source, and license in their manifest. Do not copy GPL/AGPL code into the MIT application. Optional separately installed tools must stay optional and report actual capabilities.

## Reports

Include OS, browser, app version, installed optional tool versions, reproduction steps, and expected behavior. Use public samples, synthetic fixtures, or privately retained samples. Remove private paths, faces, GPS information, and personal media from public reports. Follow SECURITY.md for suspected vulnerabilities.
