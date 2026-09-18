# Productieomgeving

Deze map bevat `pixi.toml` en `pixi.lock` voor **Waterlagen 2026.2.1 uit PyPI**.
Bewaar beide bestanden samen. U kunt deze map ook los kopiëren naar uw eigen
werkmap; de broncode van Waterlagen is niet nodig.

Installeer Pixi volgens de [installatiehandleiding](../docs/produceren/installatie.md)
en open een terminal in deze map. Voer uit:

```powershell
pixi install --locked
pixi run controleer
```

Bij succes verschijnen `Waterlagen 2026.2.1` en `Imports OK`.
Deze controle download geen brongegevens.

Sla het script uit [Eerste dataset produceren](../docs/produceren/eerste-dataset.md)
op als `eerste_dataset.py` naast de twee Pixi-bestanden en voer het uit met:

```powershell
pixi run python eerste_dataset.py
```

Gegevens worden standaard opgeslagen in `data` onder deze map. Voer opdrachten
steeds vanuit deze map uit. De Pixi-bestanden in de hoofdmap zijn voor ontwikkeling.
