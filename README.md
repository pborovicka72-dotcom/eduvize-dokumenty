# Eduvize – Dokumenty

Samostatný modul školní informační nástěnky. Bez Google Drive a OAuth.

## Funkce
- Administrace: `/config` – nahrávání PDF/JPG/PNG/WebP (do 20 MB), kategorie, pořadí, viditelnost a mazání.
- Kiosk: `/display` – veřejně viditelné dokumenty, automatické střídání, parametr `seconds` (3–3600), volitelně `layout=signage`.
- API: `/api/documents`, `/api/admin/documents`, `/api/documents/{id}/file`.
- Administrační API používá hlavičku `Authorization: Bearer <DOCUMENTS_ADMIN_TOKEN>`.
- Soubory i databáze SQLite jsou uloženy v `DOCUMENTS_STORAGE_DIR`.

## Nasazení na Render
Konfigurace `render.yaml` vyžaduje **persistent disk** (placená funkce Renderu). Bez disku se soubory po restartu či novém nasazení ztratí. Alternativou je jiné persistentní úložiště nebo hosting. Než aplikaci předáme školám, musí být trvalé úložiště skutečně aktivní.
Nastavte silný tajný `DOCUMENTS_ADMIN_TOKEN` v proměnných prostředí služby. Bez něj administrace odmítne zápis. Administrační klíč nezadávejte do veřejných odkazů.
Pro lokální vývoj: `pip install -r requirements.txt`, `DOCUMENTS_STORAGE_DIR=./data DOCUMENTS_ADMIN_TOKEN=... uvicorn app:app --reload`.

## Bezpečnost a omezení
- Publikované soubory jsou veřejně dostupné; nenahrávejte osobní údaje ani interní dokumenty.
- Pouze PDF a obrázky; Word a PowerPoint nejsou v této verzi podporovány.
- PDF se vykreslují pomocí vestavěného prohlížeče PDF; chování může záviset na zařízení kiosku.
- Základní administrace používá jeden společný tajný klíč. Pro více škol je nutné oddělení tenantů, uživatelů a úložišť.
- Vzhledem k tomu, že backend běží na jiném originu než GitHub Pages, používejte administraci přímo na URL backendu `/config`.
