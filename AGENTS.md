
## Testovací a ostré nasazení

- Nové funkce připravujte ve větvi a přes pull request. Změny v `main` se automaticky nasazují pouze na `https://test.skola.eduvize.cz`.
- Ostrý provoz `https://skola.eduvize.cz` smí přejít pouze na aktuální úspěšně otestované vydání přes workflow `eduvize-styly/.github/workflows/eduvize-production.yml`.
- Schválení prostředí `production` provádí vlastník projektu. AI agent za něj nekliká na Approve and deploy, neobchází schvalování a neposílá přímé změny na produkční server. Příprava testu není schválení ostrého vydání.
- Nikdy nekopírujte produkční data, Microsoft/OneDrive tokeny, SMTP/CRM údaje ani produkční klíče do testu. Test používá samostatné přístupy.
- Nasazujte stejné obrazy a statické soubory ověřené na testu; při publikaci nic znovu nesestavujte. Databázové změny musí být zpětně kompatibilní; destruktivní migrace vyžadují samostatný schválený plán.
- Provozní postup vlastní `eduvize-admin/deployment/README.md`. Staré vývojové odkazy nemusíme zachovávat. Render nesmí být aktivní závislostí ani přechodovou proxy cílového vydání; staré služby vypínat až po ověření a zajištění dat.

## Kontrakt výstupů a bezpečnost mazání

- Autorita: společný `../EDUVIZE-OUTPUT-CONTRACT.md` (rozhodnutí 6. 11. 2026). Od prvního stabilního vydání nového kontraktu zachovávat vydané adresy. Reset vývojových adres neautorizuje mazání dat.
- Použít jediný sdílený generátor a serverový registr. Nevymýšlet resolver po aplikacích. Veřejný kontext nikdy neodvozovat z relace nebo localStorage; profil není oprávnění.
- Úplnou nezávislost na Renderu dokládat blokováním na klientu i serveru, s prázdnou cache a restartem. Statické přepisy ani HTTP 200 nestačí.
- Každá mazací akce v aplikaci vyžaduje základní potvrzení s názvem a dopadem. Soubor navíc vyžaduje serverové ověření použití v Kiosku a dalších aplikacích a upozornění na nalezené vazby. Podrobnosti a dosud neimplementované části: `DELETION-SAFETY.md`.
- Inventura a plán: `RENDER-MIGRATION.md`. Tento dokument není povolení k nasazení, rušení služeb ani destruktivní migraci.
