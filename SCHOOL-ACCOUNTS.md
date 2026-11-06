# Školy, profily a úložiště

Aktualizováno 6. 11. 2026. Tento popis nahrazuje původní omezení na jediný profil
a povinné ukládání školních materiálů na OneDrive.

Škola vlastní identity, materiály a více profilů. Identita a připojení úložiště jsou
oddělené. Identity se nesmějí automaticky spojovat podle shody e-mailu.
Oprávnění školy a profilu se ověřují na serveru; veřejný identifikátor není oprávnění.
Materiály jsou společné škole, nastavení zobrazení patří profilu.

Primární cloudové úložiště nových a převedených škol používá PostgreSQL a
`CloudStorage`; soubory jsou v BYTEA. OneDrive je volitelný zdroj kopírovaných
importů, přehrávání cloudové kopie jej nevyžaduje. Dosud existující legacy větev
runtime neznamená, že byly převedeny všechny školy.

Převod ověřuje soubory a vazby před přepnutím, původní soubory archivuje a nemaže.
Podrobný postup a historický záznam: `eduvize-admin/CLOUD-MIGRATION.md`.
Migrace úložiště a migrace hostingu jsou odlišné úlohy; provozní umístění databáze
a záloh je nutné ověřit samostatně.

Microsoft přihlášení a připojení OneDrivu mají oddělené souhlasy a šifrované
serverové tokeny. Callback odvozuje runtime z `PUBLIC_BASE_URL`; registrace Entra
musí odpovídat vlastní doméně příslušného prostředí. Test vyžaduje vlastní integraci,
nikoli produkční tokeny. Žádná cesta callbacku, propojení identity nebo obnovy tokenu
nesmí vyžadovat Render. Jejich živé ověření není tímto dokumentem potvrzeno.

Aktuální veřejné API ještě používá `edu-profile`. Cílové výstupy přebírají kontext
ze společného serverového registru podle `../EDUVIZE-OUTPUT-CONTRACT.md`.
Původní implicitní směrování a vývojové URL není nutné zachovat. Nový resolver není
tímto dokumentem implementován. Zachovat školní data a interní reference materiálů.

Ověřit dvě školy, dva profily, cizí relaci/localStorage, nepřihlášený výstup,
zamítnutí cizích zápisů a souběžné požadavky. Kompletní matice a limity auditu:
`RENDER-MIGRATION.md`.
