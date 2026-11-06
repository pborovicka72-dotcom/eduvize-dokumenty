# Potvrzení mazání a ověření použití materiálů

Požadavek uživatele 6. 11. 2026: základní upozornění při mazání jakékoli položky
v celé aplikaci. U souboru navíc ověřit použití v Kiosku a dalších propojených
aplikacích a na použití uživatele výslovně upozornit.

## Implementovaný stav (6. 11. 2026, dosud nenasazeno)

Sdílený modul `eduvize_admin/material_usage.py` eviduje školní vazby z cloudových
konfigurací/historie a současného registru snapshotů Kiosku. Před smazáním evidence
projde úplným přepočtem dostupných zdrojů. Nový společný resolver tím nevzniká;
pro budoucí registr je připravené transakční rozhraní `replace_source`.

Dokumenty mají autorizovaný preflight `/api/admin/documents/{id}/usage`, seznam míst
použití, blokaci používaného souboru a potvrzení s názvem před mazáním. DELETE
vyžaduje potvrzení ID a revizi kontroly a pod společným DB zámkem použití znovu ověří.
Katalog, logické smazání a audit jsou jedna transakce. Změny konfigurací/publikací
nesmějí přidat explicitní odkaz na již odstraněný materiál. Obecné storage DELETE
blokuje obcházení ochrany. Veřejný soubor ověřuje živý stav i při staré procesní cache.

Podrobnosti a hranice pokrytí: `../eduvize-admin/MATERIAL-USAGE.md`. Včetně omezení:
externí a dosud neuložené odkazy nelze zjistit, nepřevedené OneDrive mazání není
povoleno a historické publikované snapshoty jsou dál použitím. Zatím je použitý
nativní potvrzovací dialog prohlížeče; nová centrální dialogová komponenta zůstává
navrženým rozšířením. Samotná změna není důkazem nasazení ani PostgreSQL E2E.

## Chování rozhraní

- Každá mazací akce (soubor, kategorie, položka sestavy, stránka, sestava, výstup,
  kolekce a další zpřístupněné položky) vyžaduje potvrzení názvu, počtu a dopadu.
  Výchozí bezpečná akce je Zrušit. Escape/odchod nic nemaže. Použít společný přístupný
  dialog s řízením fokusu, ne odlišné lokální varianty v každé aplikaci.
- Rozlišit **Odebrat z této sestavy** a **Smazat soubor ze školní knihovny**.
  Odebrání vazby nesmí smazat binární soubor. Smazání kategorie nesmí skrytě smazat její soubory.
- Před smazáním souboru načíst použití: aplikace, název sestavy/stránky, profil,
  koncept/publikace a případně dotčený výstup. Příklad: „Soubor Řád školy.pdf se
  používá v Kiosku Vstupní hala → Dokumenty a ve 2 publikovaných výstupech.“
  Odkazy na úpravu zobrazovat jen podle oprávnění uživatele.
- Navržená první verze při existujících vazbách mazání **zablokuje** a nabídne
  Zobrazit použití / Nahradit soubor / Zrušit. Po odstranění nebo nahrazení vazeb lze
  kontrolu zopakovat. To je doporučené provedení nad rámec minimálního upozornění;
  případné budoucí vynucené smazání vyžaduje explicitní samostatný návrh.
- Nepoužívaný soubor: „Smazat soubor … ze školní knihovny?“ s pravdivou informací
  o koši/obnově podle adaptéru. Dokud není obnova dostupná, neslibovat ji.
- Hromadné mazání ukáže počet a jména, souhrn použití a jasně určený rozsah akce;
  doporučená první verze zruší celou dávku při jediné blokované položce.
- Neúspěšná nebo neúplná kontrola znamená „Použití se nepodařilo ověřit“ a žádné
  smazání; nikdy „soubor není používán“. Nelze spolehlivě zjistit externí odkazy
  mimo spravovanou Eduvizi; toto omezení neskrývat v prohlášení o výsledku.

## Společný serverový návrh

Výše uvedené Documents API již existuje v pracovní změně. Následující body dále
stanovují cílový rozsah společné knihovny a všech konzumentů; ne všechny budoucí
moduly či hromadné operace jsou nyní implementované.

1. Základem je stabilní ID materiálu a školní vlastník, nikoli pouze URL. Evidence
   referencí obsahuje školu, materiál, aplikaci, profil, sestavu/stránku a revizi,
   včetně stavu koncept/publikace. Zachytit přímé použití i nepřímé použití v kolekcích,
   kategoriích a publikovaných snapshotech, případně připnutých verzích.
2. Kiosek, Dokumenty, Galerie, další moduly a serverový registr zapisují reference
   při změně obsahu ve stejné transakci jako konfiguraci/publikaci. Staré uložené URL
   nejprve zmapovat na ID při backfillu; neznámé vazby označit k došetření.
   O historii určit retenci a obnovitelnost tak, aby obnova nevytvořila rozbité odkazy.
3. Autorizovaný preflight vrátí použití, úplnost a verzi kontroly. Požadavek na mazání
   musí mít explicitní potvrzení cíle a očekávanou revizi; preflight ani potvrzení
   nejsou náhradou ověření školního vlastnictví a oprávnění při zápisu.
4. Při mazání znovu ověřit aktuální reference v transakci/uzamčení sdíleném se zápisem
   vazeb. Nová reference mezi dialogem a DELETE musí způsobit konflikt, ne rozbitý výstup.
   Chránit i cestu obecného mazání CloudStorage, galerii a hromadné operace; žádný bypass.
5. Logické smazání a úpravu katalogu provést atomicky; invalidovat katalog a soubory
   až po úspěšném commitu, i mezi procesy. Při chybě ponechat původní funkční stav.
   Fyzické odstranění řešit až následně podle schválené retence; bez automatického purge.
6. Audit zaznamená aktéra, školu, cíle, revizi kontroly a výsledek bez tokenů či obsahu
   souboru. Opakovaný požadavek nevytváří další vedlejší účinky.
7. Cizí škola nesmí získat soubor ani seznam jeho použití. U omezených rolí zobrazit
   pouze oprávněná metadata; případné skryté použití stále blokuje odstranění.

## Pořadí realizace

Nejprve společné ID/evidence a import existujících vazeb; potom serverové ochrany
všech mazacích cest; následně sdílený dialog a zapojení Dokumentů i konzumentů.
Do dokončení přepočtu vazeb neaktivovat tvrzení „nepoužívaný soubor“.
Základní potvrzování všech mazacích akcí lze zavést nezávisle, ale samo neřeší vazby.

## Přijímací testy

- Zrušení každého dialogu nezmění data; název, rozsah a dopad jsou správné, ovládání klávesnicí funguje.
- Nepoužívaný soubor projde pouze po potvrzení; opakovaný request je bezpečný.
- Soubor použitý v jiné stránce Kiosku, jiném profilu, Galerii, konceptu či publikaci
  vyvolá konkrétní upozornění a podle první verze blokaci. Otestovat nepřímé kolekce.
- Odebrání ze sestavy ponechá soubor a ostatní použití. Smazání kategorie nesmaže obsah potichu.
- Nová reference po preflightu, souběžná publikace a změna revize zabrání smazání.
- Neúplný index, výpadek služby nebo chyba transakce nic nesmaže; veřejný výstup funguje dál.
- Přímé API, obecný storage DELETE a dávka neobcházejí ochranu; cizí škola nevidí metadata.
- Cache, náhledy, restart a obnova historie nevrátí odstraněný obsah ani rozbité vazby.
