# Eduvize Design System — fáze 1: Admin UI

Referenční implementace: `eduvize-dokumenty/config.html` (stav 29. 10. 2026).
Jde o přípravu společného základu, nikoli o migraci ostatních aplikací.

## Povinná struktura administrační stránky
1. Hlavička aplikace
2. Nastavení aplikace (veškeré funkční volby)
3. Typ výstupu
4. Výběr šablony Newline Signage Pro a segmentu (použít shodnou komponentu ze Svátků)
5. Závěrečná tlačítka: Použít a otevřít výstup; Kopírovat odkaz; případně Uložit konfiguraci

Pod volbou šablon a segmentů nesmí být další nastavení aplikace.
Výběr NSP má používat původní vizuální komponentu ze Svátků, nikoli její napodobeninu.

## Sdílené soubory
- `admin-tokens.css`: barvy, typografie, rozměry a rozestupy.
- `admin-components.css`: opakovaně použitelné administrační komponenty.
- `admin-theme.json`: výchozí konfigurační hodnoty a základ pro budoucí editor.

## Další kroky
1. Ověřit shodu současné administrace Dokumentů s referenční podobou.
2. Přesunout sdílené soubory do samostatného repozitáře `eduvize-design-system`.
3. Vytvořit centrální editor tématu s náhledem, validací a verzováním.
4. Postupně napojit ostatní administrace bez změn funkční logiky.
5. Samostatně připravit Display UI; výstupní stránky se nyní nemění.

Pro produkční centrální styl je nutné zvolit stabilní hostování a verzování, aby výpadek nebo nekompatibilní změna neovlivnily všechny aplikace.
