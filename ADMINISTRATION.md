# Administration and document ownership

New uploads carry `scope=documents` (Documents administration) or `scope=kiosk` (Kiosk uploader). Missing scope on older entries means Documents; no existing files are migrated or deleted.

The public and administrator catalog defaults to Documents. The Kiosk uploader requests its own catalog. Direct document viewers resolve both catalogs, so existing public file links remain valid. File visibility is still checked before downloads. Reordering affects only the selected catalog; category visibility in Documents does not hide Kiosk attachments.

Documents opens on the category overview. PDF navigation is manual. Background catalog refresh preserves an open document and its page/zoom. Date/time/logo panels belong to Kiosk, not Documents.

Styles live in the central design system: `documents.css`, `documents-admin.css`, and the shared `document-upload.css/js`. The administration includes an interactive preview above its forms, plus Newline segment previews in the output settings.
