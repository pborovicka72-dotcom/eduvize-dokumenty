# Eduvize – Dokumenty (OneDrive testovací verze)

Dokumenty PDF/JPG/PNG/WebP se nahrávají z administrace přímo na OneDrive pomocí Microsoft Graph. Ve složce `Eduvize-Dokumenty` se ukládají soubory a `manifest.json` s kategoriemi, pořadím a viditelností.

## Render
Nastavte proměnné `MICROSOFT_CLIENT_ID`, `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_SECRET`, `PUBLIC_BASE_URL` (například `https://eduvize-dokumenty-api.onrender.com`) a silný `DOCUMENTS_ADMIN_TOKEN`. Přesměrování v Microsoft Entra musí přesně odpovídat `PUBLIC_BASE_URL/auth/microsoft/callback`. Instalujte závislosti přes `pip install -r requirements.txt`.

Otevřete `/config`, vložte administrační klíč, klikněte **Připojit OneDrive**, autorizujte účet a po návratu znovu zadejte klíč. Poté lze nahrávat dokumenty. Kiosk je na `/display`, podporuje `?seconds=15&layout=signage`.

**Omezení testovací verze:** Obnovovací token je pouze v paměti procesu. Restart Renderu vyžaduje nové připojení OneDrivu; do té doby kiosk nemůže číst soubory. Pro ostrý provoz je nutné zabezpečené trvalé uložení tokenu, nezávislé na procesu, víceuživatelská správa a ověření souhlasu správce tenanta. Zobrazené dokumenty jsou veřejné. Nahrávejte pouze dokumenty určené ke zveřejnění. Pro více instancí služby současně tento prototyp není vhodný.
