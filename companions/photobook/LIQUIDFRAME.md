# Ente Photobook companion for LiquidFrame

Upstream: https://github.com/ente-toys/photobook
Revision: f31313c771069506d2d49d0e2004009bde65ba51
License: AGPL-3.0 (see LICENSE). This directory is a separate application,
not MIT-licensed LiquidFrame code. Modified 2026-10-17 for this local installation.

Changes: static /photobook base path; system fonts instead of build-time Google
font downloads; prefixed public assets; cloud import disabled; local navigation and flexible editor layout with format/preview/export controls,
source download and an explicit opt-in library-selection importer. Browser
connections are restricted to the local origin by the helper's CSP.

Build from the LiquidFrame root with `node scripts/build-photobook.mjs`.
The script installs the exact locked dependencies using `npm ci --ignore-scripts`,
builds this application, and packages its complete corresponding source, lockfile,
license and build instructions as out/source.zip. The installed UI links it.

HTTP interface: fragment #import=<URI-encoded JSON {library,selection}> carries
only a library ID and selection identifiers. No import occurs until the user
clicks Add selected photos. POST /api/v1/photobook/selection returns a manifest;
GET /api/v1/photobook/photos/{id} produces an edited PNG copy. Session, library,
private-item, trash and source-access checks are enforced by the helper on each
request. The importer appends to the current book and does not alter originals.
Books live in this browser origin's IndexedDB, independently of catalog libraries.
