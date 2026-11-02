# Microsoft login

The former owner-only sign-in has been replaced by school-scoped sign-in.
See [SCHOOL-ACCOUNTS.md](SCHOOL-ACCOUNTS.md) for the identity/storage model,
existing school migration, callback flows, provider prerequisites and isolation tests.

Microsoft sign-in verifies User.Read identity without storing drive tokens.
A separate same-account consent connects each school to its own OneDrive.
Microsoft access/refresh tokens remain encrypted on the server.
