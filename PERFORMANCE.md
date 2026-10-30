# Načítání dokumentů

`document_delivery.py` uchovává veřejný katalog 15 sekund a soubory 60 sekund, nejvýše 64 MiB. Souběžné požadavky na stejný zdroj sdílejí jedno načtení. Zápisy manifestu, odstranění souboru a nové připojení OneDrive cache zneplatní. Starší dokončované načtení ji po invalidaci nemůže obnovit.

Před vrácením souboru i odpovědí 304 se kontroluje viditelnost dokumentu a kategorie. Odpověď používá ETag a `Cache-Control: private, no-cache`, takže prohlížeč může uchovat soubor a znovu ověřovat jeho platnost bez opakovaného přenosu celého obsahu. Změny provedené mimo aplikaci se mohou projevit až po vypršení příslušné krátké cache.

Náhled a detail sdílejí jeden načítací příslib PDF. Náhledy mimo obrazovku se odkládají, na pozadí se zpracovává nejvýše jeden. První vykreslená strana se ukáže před dokončením ostatních stran přehledu.
