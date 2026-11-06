# Inventura závislostí Dokumentů a plán migrace

Stav 6. 11. 2026. Audit zdrojů, nikoli potvrzení provozní nezávislosti.
Závazná autorita: `../EDUVIZE-OUTPUT-CONTRACT.md`; produkční postup vlastní
`eduvize-admin/deployment/README.md`. Případné starší požadavky na kompatibilitu
vývojových URL nebo přechodovou Render proxy jsou tímto kontraktem překonány.

## Rozsah a důkazy

Kontrolovány aktuální lokální zdroje Dokumentů a dostupné samostatné pracovní kopie
Admin a Stylů. Revize, soubory a řádky všech nalezených Render výskytů obsahuje
`render-dependency-inventory.json`. Jde o kandidáty včetně dokumentace a testů,
ne počet aktivních síťových závislostí. Sken vylučuje `.git`, `vendor` a binární soubory.

Checkout soukromých submodulů přes HTTPS selhal na chybě autentizace. Jejich připnuté
revize proto nejsou automaticky totožné s kontrolovanými samostatnými kopiemi.
Fotogalerie a Kiosek nejsou v této pracovní kopii dostupné jako autoritativní repozitáře.
Kopie galerie ve Stylech byla prohledána, ale nenahrazuje audit vlastníka galerie.
Nečteny produkční secrets, DB, uložené školní konfigurace ani stav serveru.
Nebyl proveden živý callback, odchozí síťový záznam, restart ani test blokování Renderu.
Inventura runtime a uložených vazeb musí být doplněna před přijetím migrace.

## Nálezy a požadované řešení

| Oblast / důkaz ve zdrojích | Nález a dopad | Cílové řešení / vlastník |
| --- | --- | --- |
| `app.py`: CORS; `design_system_redirect` | Povolené Render origins a přímý redirect na API Stylů. CORS sám nevolá Render, redirect ano. | Centrální konfigurace prostředí, vlastní origin; Dokumenty + Admin. |
| `config.html`, `index.html` | GitHub Pages skripty/CSS a preconnect k Render Stylům; načtené skripty mají další závislosti. Preconnect není datové API, ale z cílového výstupu odstranit. | Verzionované lokální assety stejného vydání; Styly + release. |
| `index.html`: first-paint styl | Chybějící profil se bere také z relace/localStorage. Porušuje cílový veřejný kontext. | Kontext jedině z registru výstupu; profilový cache klíč podle resolveru. |
| Admin `web/design-system/admin-auth.js`, `admin-launcher.js` | Centrální auth, status, předání relace a rozpoznání cílů jsou navázané na staré hosty. | Sdílená konfigurace originů a interních služeb bez fallbacku. |
| Admin `eduvize_admin/admin_sessions.py` | DOCUMENTS default na Renderu; serverové ověření statusu a výměna email identity, allowlisty a cíle návratů. | Interní endpoint Documents a Administration podle prostředí; kontrola callbacku i returnTo. |
| Admin `eduvize_admin/runtime.py:212` | Serverový POST propojení Microsoft identity na Render Admin. `PUBLIC_BASE_URL` určuje callback; skutečná hodnota není v auditu známa. | Vlastní auth služba, samostatná registrace testu, prověřit obnovu tokenů. |
| `active-theme.js`, `branding.js`, `branding-admin.js` | Načítání vzhledu a brandingu z Render Stylů. | Same-origin API, aktivní styl správného profilu. |
| `configuration-profiles.js`, `generated-links.js`; Admin `generated_links.py` | Konfigurace a evidence odkazů používají Render API a staré mapy hostů. | Jediný společný generátor + serverový registr, žádná samostatná varianta Dokumentů. |
| `output-modes.js`, `broadcast-license.js`, `licensing-client.js` | Veřejný stav vysílání/licencí přes Render Admin; týká se i nepřihlášeného výstupu. | Lokální licenční služba a odpovídající veřejné API. |
| `update-settings.js`, `update-runtime.js`; Admin plánovací runtime | Ukládání a běhové obnovy používají Documents na Renderu. | API a plánovače na vlastní infrastruktuře; inventura externích automatizací/webhooků. |
| `app.py`: Graph volání, `CloudStorage`, `DATABASE_URL` | Cloud je adaptér za Graph-like rozhraním; legacy instalace mohou stále používat OneDrive. Umístění DB nelze určit ze zdroje. | Ověřit cloudReady každé školy, DB/soubory/zálohy mimo Render, kontrolní součty a obnovu. |
| `kiosk_remote.py` | Ovládání běží uvnitř Dokumentů, stav v DB; mobilní URL míří na GitHub Pages. | Lokální ovládání, oddělené capability oprávnění, revize odkazů a párování bez Renderu. |
| `app.py`: gallery router; kopie `fotogalerie/gallery-common.js` ve Stylech | Sdílený dokumentový backend hostuje i historická API galerie; kopie galerie má Render Documents API. | Koordinovat galerii a Kiosek, nevypnout používané API bez nového zapojení. |
| `render.yaml`, `build.sh`, `.gitmodules` | Historický Render předpis a dvě privátní závislosti; build nesmí záviset na dostupném Renderu. | Zmrazený zdrojový manifest a dostupné balíčky ve společném release. |
| Admin `deployment/single-host.py`, `compile-release.py` | Přepisují URL a Python konstanty; single-host navíc zachovává staré CORS/targets. | Prověřit výsledný artefakt, poté nahradit skryté přepisy explicitní centrální konfigurací. |
| Admin `deployment/worker.py`, `bootstrap.py`, `Caddyfile.test` | Již existuje lokální build, oddělený test a interní routování Documents. Není důkazem stavu nasazeného serveru. | Zachovat release proces; zkontrolovat skutečný manifest, konfiguraci a odchozí síť. |
| Testy, staré MD, host mapy | Historické řetězce nejsou samy aktivní závislost. | Označit/odstranit zbytečné compatibility fixtures, zákaz aktivních hostů testovat v artefaktu. |

Další externí služby: PDF.js a worker se načítají z cdnjs; Microsoft identity/Graph
jsou legitimní volitelné integrace. Nejde o Render, ale evidence dostupnosti je má
obsahovat. Pro reprodukovatelné vykreslení doporučeno přibalit připnutý PDF.js worker.
Word/PowerPoint se nyní exportují do PDF uživatelem; vlastní převodní služba nebyla
v tomto repozitáři nalezena. Případné externí konverze ověřit v runtime inventuře.

## Konkrétní migrační postup a výstupy etap

1. **Zmrazit důkazy a rozdělit vlastnictví.** Koordinátor Admin vlastní originy,
   resolver/generátor, auth a release. Dokumenty vlastní katalog/prohlížeč/API;
   Galerie a Kiosek své reference. Získat autoritativní revize všech balíčků.
   Doplnit anonymizovaný inventář aktivních uložených URL, DB a úložišť, webhooků,
   cronů, token refresh a redirectů. Výstup: manifest závislostí a seznam potřebných výstupů.
2. **Zajistit data a test.** Ověřit zálohu a zkušební obnovu DB včetně BYTEA,
   konfigurací, identit a klíčů bezpečnou cestou se správou serveru. Do testu pouze
   syntetické dvě školy/dva profily a vlastní testovací identity. Evidovat nepřevedené
   školy; změna URL jejich data nepřevede. Žádné kopírování produkčních secrets do testu.
3. **Odstranit provozní vazby.** Nasadit do testu centrální konfiguraci veřejného originu
   a interních API. Upravit sdílené auth, licence, styly, plány a odkazy, potom Dokumenty.
   Zkontrolovat výsledné JS/HTML/Python/JSON, HTTP Location, CORS/CSP a callback registrace.
   Nepřidávat onrender fallback. Release compiler musí být součástí ověřovaného manifestu.
4. **Integrovat společný kontrakt.** Po společném určení resolveru připojit registr
   škola/profil/aplikace/sestava/režim/publikovaná revize. Explicitní tvorba s retry bez
   duplicit, koncept oddělený od publikace, atomické přepnutí revize. Změna obsahu/stylu
   drží URL. Stanovit první stabilní vydání a registr. Potřebné vývojové odkazy znovu
   vydat a nahradit vložení v kioscích; zachovat materiály a interní reference.
5. **Zapojit bezpečné mazání.** Společná evidence použití a potvrzovací komponenta dle
   `DELETION-SAFETY.md`; přepočítat existující vazby v konceptech i publikacích. Bez
   úplného backfillu neoznačovat soubory za nepoužívané. Neprovádět purge během migrace.
6. **Prokázat nezávislost.** Na testu blokovat `*.onrender.com` v prohlížeči i odchozí
   síti serveru (včetně redirectů a případných přímých IP cest). Vyčistit browser,
   service-worker a aplikační cache, restartovat služby. Ověřit celý průchod od
   přihlášení/uploadu po skutečný PDF/obrázek/video, import, styl, licenci, plán a ovládání.
   Samotný /health nebo HTTP 200 nepostačuje. U neověřeného callbacku vykázat omezení.
7. **Pilot a schválené vydání.** PR, úspěšný test, síťové důkazy a pilot. Vlastník schválí
   konkrétní release ID pro produkci; nasadit stejný artefakt a ověřit skutečný obsah.
   Předem připravit návrat aplikace bez obnovy staré DB přes nová data.
8. **Ukončení Render služeb.** Až po prokázání nezávislosti všech konzumentů, zálohách
   a koordinaci správy serveru. Odstranění historických manifestů/registrací provést
   samostatně. Nevypínat službu jen proto, že doména nebo statický sken vypadají správně.

## Přijímací matice

Každý záznam: release ID, prostředí, scénář, očekávání, výsledek, anonymizovaný důkaz.

- Generátor: režim/geometrie, retry, kopie/otevření bez duplicit a zveřejnění konceptu.
- Kontext: dvě školy/dva profily, čistý nepřihlášený browser i záměrně cizí localStorage/relace.
- Obsah: katalog, kategorie a scope, přímé otevření z Kiosku, PDF náhled/detail/zoom,
  obrázek a video včetně Range požadavků, import bez následné závislosti na OneDrivu.
- Publikace: koncept vs revize, souběžná editace, chyba zápisu, odvolání/404/410 bez demo fallbacku.
- Styl a geometrie: změna správného profilu bez změny URL, web/NSP/kiosek, obě orientace a malé segmenty.
- Mazání: matice z `DELETION-SAFETY.md`, cache nesmí vrátit odstraněný či skrytý obsah.
- Bez Renderu: klientský HAR bez tokenů + serverový egress log, prázdná cache, restart,
  callbacky a plánované úlohy; žádná závislost schovaná ve starém obsahu nebo redirectu.
- Prostředí: test nepoužívá produkční účty/API/soubory, stejné zmrazené artefakty pro vydání.

## Zbývající omezení

Původní inventura byla dokumentační přípravou. Navazující pracovní změna již
implementuje evidenci použití a bezpečné mazání (viz `DELETION-SAFETY.md`),
ale neimplementuje nový resolver a nepřepíná infrastrukturu. Přístup k soukromým závislostem,
živá inventura DB/konfigurace a úplné E2E jsou otevřené kroky. Požadavek na monitoring
v kontraktu sám nezřizuje automatickou kontrolu.
