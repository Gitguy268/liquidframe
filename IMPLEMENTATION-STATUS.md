# Working notes

This file is retained for continuity. Public setup and acceptance information is in README.md, FEATURE-STATUS.md, and VERIFICATION.md.

The project has been renamed to `.`; `~/openphoto` holds compatibility launchers. Preserve `.openphoto-data`, all models/results/recipes/protected backups, and the existing SQLite recovery snapshot. Original migration baseline: 22,195 assets, three recipes, one root, no original-replacement backups.

Source was staged under `Documents/Codex/2026-10-14/cr/work/liquidframe-build`. Deployment must back up/checkpoint the real catalog and compare catalog/recipe counts before/after. Do not overwrite `.venv`, data, `.git`, or the local library registry with staging artifacts. Use only the isolated public-sample catalog for UI screenshots; the real library references the user's home folder.

Known remaining scope is explicitly listed in FEATURE-STATUS.md. Do not describe the full original behavior specification or all platforms as completed merely because the current build and automated tests pass.
