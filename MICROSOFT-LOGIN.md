# Přihlášení Microsoftem do správy Eduvize

Používá existující aplikaci Microsoft a stejnou registrovanou návratovou adresu
`PUBLIC_BASE_URL/auth/microsoft/callback`. Nevyžaduje novou registraci ani implicitní tok.
Nastavení `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`,
`PUBLIC_BASE_URL`, `DATABASE_URL` již používá připojení OneDrive.

Přihlásit se může jen vlastník již připojeného OneDrivu. Identita se porovnává
podle neměnného Microsoft Graph `/me.id`, nikoli podle e-mailu nebo názvu školy.
Pro více správců nebo škol bude potřeba samostatná explicitní správa oprávnění.
První připojení OneDrivu dál vyžaduje původní klíč Eduvize.

Tok: prohlížeč vygeneruje důkaz S256; Dokumenty zahájí autorizační tok s vlastním
PKCE a náhodným stavem navázaným na Secure/HttpOnly/SameSite=Lax cookie.
Callback ověří Graph identitu a aktuálního vlastníka, vydá jednorázový lístek
s platností 120 sekund, vázaný na původní prohlížeč. Centrální server lístek
vymění u Dokumentů a vytvoří běžnou zrušitelnou relaci se scopes documents/styles.
Stavy a lístky jsou v PostgreSQL; platnosti a jednorázovost přežijí restart.
Microsoft access/refresh token přihlášení se neukládá a nenahrazuje OneDrive připojení.

Ověření: tests/test_microsoft_login.py (PKCE, vlastník, změna vlastníka, cookie,
zrušení a jednorázový lístek); centrální tests/test_admin_sessions.py ověřuje vznik
relace, zachování profilu a odmítnutí neověřené identity a nepovoleného Origin.
Ruční ověření vyžaduje, aby vlastník na Microsoft stránce dokončil své přihlášení.
