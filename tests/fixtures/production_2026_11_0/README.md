# Updater uit release 2026.11.0

`bijwerken.py`, `bijwerken.cmd.fixture` en `bijwerken.sh` bevatten ongewijzigde bytes uit
tag `2026.11.0`, commit `e96b7c5a3f5b9a5f70ce71719081c4deb2025008`.
Zij blijven staan om de overstap vanuit de daadwerkelijk geleverde oude updater
te testen. Pas deze bestanden niet aan bij wijzigingen aan de nieuwe updater.

De test installeert `bijwerken.cmd.fixture` als `bijwerken.cmd`. De extra extensie
voorkomt dat de algemene Git-ignore voor `*.cmd` de fixture uitsluit.

De overige installatiebestanden en hun metadata worden in de tests synthetisch
gemaakt. Downloads en Pixi-installaties worden daar vervangen door lokale fixtures.
