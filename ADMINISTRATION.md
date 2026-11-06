# Administration and document ownership

New uploads carry `scope=documents` (Documents administration) or `scope=kiosk` (Kiosk uploader). Missing scope on older entries means Documents; no existing files are migrated or deleted.

The public and administrator catalog defaults to Documents. The Kiosk uploader requests its own catalog. Current direct document viewers resolve both catalogs. Historical development-link preservation is no longer a target requirement; stable links issued under the new shared contract must remain stable. File visibility is still checked before downloads. Reordering affects only the selected catalog; category visibility in Documents does not hide Kiosk attachments.

Documents opens on the category overview. PDF navigation is manual. Background catalog refresh preserves an open document and its page/zoom. Date/time/logo panels belong to Kiosk, not Documents.

Styles live in the central design system: `documents.css`, `documents-admin.css`, and the shared `document-upload.css/js`. The administration includes an interactive preview above its forms, plus Newline segment previews in the output settings.

## New output contract (6 November 2026)

The shared `../EDUVIZE-OUTPUT-CONTRACT.md` supersedes development URL compatibility.
Integrate the shared generator/registry; do not invent a Documents resolver.
Public context comes from the registered output, never an administrator session or
localStorage. Drafts and published revisions remain separate. Contents and active
profile style change at the same stable URL. Target deployments have no Render dependency.
See `RENDER-MIGRATION.md` for the observed implementation gaps.

## Deletion

Every destructive UI action requires confirmation naming its target and effect.
Deleting a file additionally requires a server-side usage check across Kiosk and
all connected applications, with a specific warning listing affected uses.
The document button now performs authorized usage preflight, displays locations,
blocks used materials and requires confirmation. DELETE rechecks usage under the
school database lock and updates the catalog and file atomically. This is implemented
in the working change, not yet deployed. Shared integration and limits are documented
in `../eduvize-admin/MATERIAL-USAGE.md`.
See `DELETION-SAFETY.md` for the proposed shared implementation and acceptance tests.
