# Eduvize – Dokumenty

Samostatný modul pro správu a zobrazování školních dokumentů. Dokumenty se ukládají na OneDrive prostřednictvím Microsoft Graph; manifest určuje kategorie, pořadí a viditelnost.

## Stránky a API
- Administrace: https://eduvize-dokumenty-api.onrender.com/config
- Zobrazení: https://eduvize-dokumenty-api.onrender.com/display
- Veřejné dokumenty: `/api/documents`

## Nasazení
Render spouští FastAPI. Konfigurace prostředí: `MICROSOFT_CLIENT_ID`, `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_SECRET`, `PUBLIC_BASE_URL`, `DOCUMENTS_ADMIN_TOKEN`, `DATABASE_URL` a `TOKEN_ENCRYPTION_KEY`. Přesměrování Microsoft Entra musí odpovídat `PUBLIC_BASE_URL/auth/microsoft/callback`.

OAuth tokeny se při správném nastavení databáze a šifrovacího klíče ukládají šifrovaně do PostgreSQL. Nezveřejňovat přístupové klíče ani soukromé dokumenty.

## Architektura
Tento repozitář vlastní správu dokumentů, OneDrive integraci a vlastní administraci. Společné barvy, komponenty administrace a Newline šablony načítá z `eduvize-styly`. Neudržovat zde další kopii centrálního editoru nebo geometrie segmentů.

Změny CSS administrace testovat odděleně od zobrazovací stránky a ověřovat také vodorovné a svislé šablony Newline.
