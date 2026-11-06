# Ověření evidence použití a bezpečného mazání

Datum: 6. 11. 2026. Výsledek: **prošlo**. Produkce nebyla měněna.

Test proběhl v samostatném dočasném kontejneru na VPS na síti `eduvize-test-internal`,
v samostatném schématu databáze `eduvize_test` na PostgreSQL 18.6. Chrome se připojoval
přes SSH tunel na loopback port 18121. Kanonické nasazení test.skola.eduvize.cz ani
běžící pilot galerie nebyly nahrazeny. Dvě syntetické školy/profily byly nezbytné pro
ověření izolace a existovaly jen v tomto vlastním schématu; nepoužívaly produkční data.

## Výsledky

- Souběh skutečných nezávislých PostgreSQL spojení: obě vynucená pořadí publish/DELETE,
  starší Kiosek, 12 souběžných dvojic a uvolnění vazby po odvolání registru. Nikdy
  neuspěla současně publikace chybějícího média a jeho smazání.
- Browser: 11 kontrol. Nahrání syntetického obrázku a dvoustránkového PDF, otevření
  z publikovaného Kiosku bez správní relace, skutečné textové pixely PDF, zoom a návrat
  do přehledu, návrat do nabídky, správný profil/licence administračního náhledu,
  blokace používaného souboru s místem použití, zrušení potvrzení, potvrzené smazání
  nepoužívaného souboru včetně veřejného 404, cizí škola 404, zachování ostatního
  výstupu a obě orientace. Některé související akce tvoří jednu kontrolu.
- Žádné JavaScriptové chyby, žádné neúspěšné aplikační požadavky opravené verze,
  žádné pokusy o Render. PDF.js byl použit z dosavadního cdnjs zdroje; nejde o test
  úplného offline provozu. Samostatně označená původní referenční stránka vyvolala
  známé 402 náhledu, které opravená verze již nevyvolává.
- Rozložení: porovnáno původní `HEAD:config.html` a pracovní verze pod stejnou `/config`
  cestou, se stejnými daty, relací, viewportem a společnými styly. Zachováno pořadí,
  skupiny, souřadnice a rozměry devíti existujících ovládacích prvků (tolerance 2 px).
  Hlavní přihlašovací obrazovka se neupravovala; test používal syntetickou správní relaci.

## Opravy z ověřování

Kontrola doplnila skutečný společný registr a vložené base64/gzip konfigurace Kiosku.
Mazání přebírá writer lock společného registru před školním souborovým zámkem.
Příslušné souběhové důkazy jsou v `material-concurrency-postgresql.json`.

Browser odhalil závod při vytváření náhledu Dokumentů: náhled se mohl vytvořit ještě
před ověřením správní relace, bez profilu školy, a zůstat v neplatném licenčním kontextu.
`link()` nyní dočasně použije explicitní profil z URL a po ověření relace nebo změně
profilu se náhled obnoví. Ovládací prvky se nepřesouvaly. Regrese:
`tests/preview-profile.test.mjs` a kontrola aktivní licence ve skutečném browser testu.

## Důkazy a opakování

- `material-concurrency-postgresql.json`: výsledky PostgreSQL a SHA256 zdrojového archivu.
- `material-browser/browser-result.json`: kroky, síťové statusy bez hlaviček/tokenů,
  omezení testu, použitý obraz a SHA256 testovaných pracovních souborů.
- `material-browser/layout-comparison.json`: porovnání původního rozložení.
- PNG ve `material-browser`: skutečný dokument, PDF, blokace mazání a výstup na výšku.
- Ověřovací kód: `../tools/verify_material_kiosk_browser.py`,
  `../tools/material_acceptance_app.py`, `../../eduvize-admin/tools/verify_material_concurrency.py`.

Pro opakování připravit oddělený testovací kontejner s testovou konfigurací a balíčky
Admin/Dokumenty; browser runner připouští jen localhost/127.0.0.1. Připojit `/acceptance`
a read-only kopii veřejných assetů `/public`; runtime schema musí mít vlastní náhodný
prefix `material_browser_`. Nikdy nepoužít produkční konfiguraci. Testovací transport
validace relace používá skutečný SessionStore přímo; neověřuje Microsoft callback.

## Úklid

Před úklidem ověřeny všechny vazby ve vlastním schématu: 2 vlastní školy, 2 profily,
3 snapshoty Kiosku a 15 cloudových záznamů, žádný cizí vlastník. Browser byl ukončen,
tyto výstupy nebyly používány jiným testem a jejich adresy existovaly pouze v izolované
instanci. Kontejner byl zastaven, vlastní schéma odstraněno jeho shutdownem a následný
parametrizovaný SQL dotaz potvrdil `to_regnamespace(...) IS NULL`. SSH tunel byl uzavřen.
Ostatní testovací a produkční profily ani služby se neměnily. Zdrojový testovací balíček
v domovském adresáři VPS neobsahuje přístupy ani školní obsah a není běžící službou.

Před vydáním změn je nadále nutné společné PR/release Admin a Dokumentů a obvyklé
schválení vlastníkem. Tento protokol není potvrzením nasazení na sdílený test ani produkci.
