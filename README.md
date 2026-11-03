# Eduvize – Dokumenty

Správa a zobrazování školních dokumentů. Tento repozitář vlastní dokumentový
katalog, soubory, kategorie a jejich prezentaci.

Společná administrace je připnutá závislost `vendor/eduvize-admin`.
Fotogalerie je připnutá závislost `vendor/eduvize-fotogalerie` pouze pro zachování
historických API adres. Vlastní vývoj galerie probíhá výhradně v jejím repozitáři.

Stávající adresy `/config`, `/display`, `/api/documents`, OAuth callbacky a profily
škol se nemění. Data zůstávají na stejném OneDrive a ve stejné databázi.

Build: `sh build.sh`; spuštění: `uvicorn app:app`.
Render musí mít přístup k oběma soukromým submodulům. Přesun nesmí být nasazen
před úspěšným checkoutem závislostí a integračními testy. Zálohy původního commitu
umožní návrat bez databázové migrace.
