---
editorial_status: human
---

# Downloaden van bronbestanden lukt niet

Waterlagen downloadt automatisch de benodigde bronbestanden. Binnen sommige bedrijfsnetwerken kan dit mislukken door de beveiliging van HTTPS-verbindingen, bijvoorbeeld met de foutmelding `CERTIFICATE_VERIFY_FAILED`.

Standaard wordt de identiteit van de downloadserver gecontroleerd (`WATERLAGEN_SSL_VERIFY=true`).

Vraag bij voorkeur uw IT-beheerder om dit op te lossen. Deze kan zo nodig een vertrouwd certificaatbestand (PEM) beschikbaar stellen. U kunt dit in PowerShell instellen met:

```powershell
$env:REQUESTS_CA_BUNDLE = 'C:\certificaten\organisatie-ca-bundle.pem'
```

Start daarna de productie opnieuw vanuit hetzelfde PowerShell-venster.

Als dit niet mogelijk is, kunt u de certificaatcontrole voor downloads door Waterlagen uitschakelen. Voeg hiervoor de volgende regel toe aan het bestand `.env` in uw projectfolder (maak dit bestand aan als het nog niet bestaat):

```dotenv
WATERLAGEN_SSL_VERIFY=false
```

Een procesvariabele met dezelfde naam heeft voorrang op de waarde in `.env`.

Start vervolgens de productie opnieuw.

Let op: hierdoor wordt de identiteit van de downloadserver niet meer gecontroleerd. Gebruik deze instelling alleen als uitzondering binnen een vertrouwde omgeving. Verwijder de regel of zet de waarde op `true` zodra het certificaatprobleem is opgelost.

Deze instelling geldt alleen voor downloads door Waterlagen, niet voor de installatie van software via Pixi.
