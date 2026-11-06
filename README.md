# Eduvize – Dokumenty

Správa a zobrazování školních dokumentů: katalog, soubory, kategorie a prezentace.
Společnou administraci vlastní `eduvize-admin`; Fotogalerii `eduvize-fotogalerie`.
Obě jsou připnuté závislosti pod `vendor/`; distribuované vydání je sestavuje
z autoritativních zdrojů podle `eduvize-admin/deployment/README.md`.

## Závazný směr od 6. 11. 2026

Produkce `https://skola.eduvize.cz` a test `https://test.skola.eduvize.cz` musí
fungovat bez Renderu, i po restartu a bez cache. Žádná Render proxy, fallback
ani čekání na probuzení není přípustné. Jde o požadavek, nikoli potvrzení migrace.

Autoritou je společný `../EDUVIZE-OUTPUT-CONTRACT.md`. Staré vývojové adresy
nemusíme zachovávat; školní data a materiály se tím nemažou. Od prvního stabilního
vydání kontraktu jsou adresy stálé. Dokumenty integrují jediný společný generátor
a serverový registr; přesný resolver ještě musí být společně určen.
Kontext veřejného výstupu určí registr, nikoli relace nebo localStorage.
Kopírování nepublikuje koncept ani nevytváří další výstup. Publikace je atomická.

## Úložiště a stav implementace

Primární úložiště převedených a nových škol je cloud Eduvize v PostgreSQL,
včetně binárních souborů přes `CloudStorage`. OneDrive je volitelný import.
Starší nepřevedené instalace mají v runtime dosud původní větev; její odstranění
vyžaduje ověřenou migraci dat. Cloud sám nedokazuje nezávislost databáze na Renderu.
Škola může mít více profilů; materiály jsou společné škole, zobrazení patří profilu.

[Inventura a konkrétní plán migrace](RENDER-MIGRATION.md) odděluje nálezy ve zdrojích,
sestavení a dosud neověřenou produkci. [Pravidla mazání](DELETION-SAFETY.md)
stanovují potvrzení každé mazací akce a kontrolu použití souborů napříč aplikacemi;
implementace nyní pokrývá uložené cloudové konfigurace/historii a registr snapshotů
Kiosku; limity a navazující zapojení společného registru popisuje
`../eduvize-admin/MATERIAL-USAGE.md`. Změna zatím není nasazená. Browser a PostgreSQL ověření v samostatné testovací
instanci: [protokol](verification/MATERIAL-ACCEPTANCE.md).

## Vývoj a vydání

Lokální build: `sh build.sh`; start: `uvicorn app:app`.
Checkout musí obsahovat obě soukromé závislosti; nedostupné závislosti nelze
nahrazovat prázdnými balíčky. `render.yaml` je historický nasazovací předpis,
ne cílová infrastruktura ani cesta pro nové vydávání.

Vývoj ve větvi a přes PR, nejprve test a pilotní výstupy. Produkci schvaluje vlastník
přes společný release proces; publikují se stejné ověřené artefakty. Rollback aplikace
nesmí přepsat novější data. Zálohovat databázi včetně souborů a ověřit obnovu.
