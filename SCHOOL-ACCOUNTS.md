# School accounts and storage

One verified provider identity currently owns one school, with exactly one profile.
The school ID and profile ID are generated once and survive storage/provider changes.
The first enabled provider is Microsoft. Google and Eduvize identities have reserved
provider identifiers but no public login/linking endpoint until their verification
services are configured. Identities are never automatically linked by email.

`school_accounts.py` owns the school/identity registry and storage binding in PostgreSQL.
`SchoolProfileStore` checks profile ownership before delegating to the current OneDrive
adapter. A future cloud adapter can replace `ProfileStore` without changing school IDs,
profile IDs, admin sessions or kiosk links. Actual school settings/files remain on
OneDrive for this release; the registry is not a new general-purpose file cloud.

Microsoft login requests User.Read only and creates a school-scoped central session.
It neither persists Graph tokens nor grants central theme publishing permissions.
Connecting storage is a separate, browser-bound PKCE OAuth flow requesting
User.Read, Files.ReadWrite and offline_access. The server compares the immutable
Graph /me.id to that school's Microsoft identity before saving encrypted tokens.
Tokens are keyed by school ID; no school can replace another school's connection.
The launch URL is single-use (60 seconds), and callback state is single-use (10 minutes).
Both flows use the existing registered Microsoft callback URI.

School-scoped sessions carry schoolId and the fixed profileId through handoffs.
They cannot change their profile, create/copy profiles, obtain operator scopes, or
publish central styles. The existing operator-key login remains an explicit service
maintenance function, not a school account or the future Eduvize user login.

## Migration

The old OneDrive owner is verified once with Graph and pinned in the registry.
Its original encrypted token record (`microsoft`), profile
`c0e094dbb91b4139a150a86efc87001b`, documents and kiosk URLs are preserved in place.
Other schools receive generated IDs and independent token records. No files are moved
or deleted. A failed initial verification blocks migration instead of silently creating
a second profile for the original owner. Existing operator sessions remain valid;
Microsoft users should sign in again to obtain school-scoped sessions.

## Public displays

`edu-profile` routes public document catalogs and files to the correct school's adapter.
Unknown explicit IDs return 404, never the original school's content. Links without
that parameter preserve the original installation for compatibility. Display endpoints
continue to expose only visible published content; profile IDs are public routing IDs,
not credentials. Administration always authorizes ownership using the verified session,
never a query parameter. Document caches and request token dictionaries are isolated
by school, including concurrent requests.

## External Microsoft configuration

The Entra application must allow accounts from other school tenants (and personal
accounts only if desired), The school login/storage flows use the Microsoft `common` authority; new school
refreshes use it too. MICROSOFT_TENANT_ID is retained only for the original connection
so the existing deployment can migrate without environment changes. Tenant policies may require their administrator's consent.
The existing registration was verified in Entra on 2026-11-02 as allowing any Entra
tenant plus personal Microsoft accounts. No registration permission or tenant policy
was changed.

## Validation

Run `python -m unittest discover -s tests -v` in this repository and the equivalent
central styles tests. School tests cover separate identities, repeat onboarding,
legacy preservation, foreign profile reads/writes, per-school concurrent token context,
separate document caches, and same-account versus wrong-account storage consent.
