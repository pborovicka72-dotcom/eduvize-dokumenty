# Přihlášení Google – nastavení testu

1. V Google Cloud Console vytvořte projekt a povolte **Google Drive API**.
2. Nastavte OAuth consent screen. Pro testování přidejte svůj Google účet mezi testovací uživatele.
3. Vytvořte OAuth Client ID typu **Web application**.
4. Authorized redirect URI: `https://<váš-backend>.onrender.com/auth/google/callback`.
5. Nasaďte backend podle `render.yaml` a nastavte v Render **GOOGLE_CLIENT_ID**, **GOOGLE_CLIENT_SECRET**, **PUBLIC_BASE_URL** (například `https://<váš-backend>.onrender.com`).
6. V administraci Dokumentů nastavte URL backendu a použijte Přihlásit přes Google.

Neposílejte client secret do GitHubu ani do prohlížeče. OAuth tokeny zůstávají pouze na serveru. Tento prototyp ukládá relace jen do paměti procesu, takže po restartu serveru přihlášení zanikne. Pro ostrý provoz je nezbytné doplnit šifrované persistentní úložiště, správu školních administrátorů, revokaci tokenů, CSRF ochranu a autorizaci publikování. Samotné přihlášení neznamená souhlas s veřejným publikováním dokumentů.

Poznámka: Některé prohlížeče blokují cookies třetích stran mezi GitHub Pages a Renderem. Pro ostré nasazení doporučujeme administraci a API pod stejným webovým původem / reverzní proxy.
