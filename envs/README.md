# Waterlagen @VERSION@ produceren

Dit pakket hoort bij release **@TAG@**. Het installeert Waterlagen **@VERSION@**
uit PyPI en bevat de bijbehorende openbare productiescripts. Een Git-checkout of
toegang tot een private repository is niet nodig.

Installeer [Pixi](https://pixi.prefix.dev/latest/installation/) en pak de ZIP uit.
De uitgepakte map met `pixi.toml`, `pixi.lock` en `scripts` is uw **projectfolder**.
U mag deze map een eigen naam geven, bijvoorbeeld `mijn-waterlagen`.

Open die map in Windows Verkenner. Klik in de adresbalk, typ `powershell` en
druk op Enter. Op Linux opent u een shell in dezelfde map.
Voer de volgende opdrachten uit, steeds gevolgd door Enter:

```powershell
pixi install --locked
pixi run --locked controleer
```

De controle toont de Waterlagen-versie, importeert de scripts en test een klein
raster met GDAL, Rasterio en PCRaster. Er worden geen brongegevens gedownload.

## Een productie starten

Kies één opdracht en voer die vanuit uw projectfolder uit:

| Productie | Opdracht | Meegeleverd script |
|---|---|---|
| Afwateringseenheden (standaard Aa en Maas) | `pixi run --locked afwateringseenheden` | `scripts/afwateringseenheden.py` |
| Functioneel landgebruik (landelijk) | `pixi run --locked landgebruik` | `scripts/functioneel_landgebruik.py` |
| Inwoners per woon-VBO (landelijk) | `pixi run --locked inwoners` | `scripts/inwoners.py` |
| Personenauto's per woon-VBO (landelijk) | `pixi run --locked auto` | `scripts/auto.py` |

Voor afwateringseenheden kiest u een waterschap met de waterbeheercode.
Met `--workers` kunt u het aantal werkprocessen beperken:

```powershell
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2
```

Hier worden voor Aa en Maas maximaal twee rekentegels tegelijk verwerkt. Gebruik
`--workers 1` bij weinig werkgeheugen; de productie kan dan langer duren.
De overige rekeninstellingen liggen vast. Zie
[Afwateringseenheden produceren](https://d2hydro.github.io/waterlagen/produceren/afwateringseenheden/)
voor uitleg; `pixi run --locked afwateringseenheden --help` toont de beschikbare
opties.

Inwoners en auto's halen eerst BAG-light op met `scripts/bag.py`.
Bestaande bronbestanden worden waar mogelijk hergebruikt. Dit zijn volledige
producties: landelijke downloads en berekeningen kunnen veel tijd en schijfruimte
vragen.
Controleer de geproduceerde datasets inhoudelijk voordat u ze gebruikt.

Na productie van zowel inwoners als auto's kunt u de totalen vergelijken met
`pixi run --locked statistiek_inwoners_autos`.

De meegeleverde `.datastore` bevat `DATA_DIR=./data`. Daardoor staan downloads en
resultaten onder `data` in uw projectfolder. Pas alleen deze instelling aan als
u een andere opslaglocatie wilt. Bewaar ook dit bestand bij het verplaatsen van
de projectfolder. Start opdrachten vanuit de map met `pixi.toml`.

Bewaar `pixi.toml` en `pixi.lock` samen en gebruik `--locked`: het lockbestand legt
de dependencyversies voor Windows en Linux vast. Internet is nodig voor de eerste
installatie en voor brongegevens. Scripts blijven bewerkbare voorbeelden; Pixi
installeert het Waterlagen-pakket van de release, niet een lokale ontwikkelversie.

Zie [Zelf produceren](https://d2hydro.github.io/waterlagen/produceren/) voor de
handleiding en toelichting op inputs en resultaten. De online handleiding kan
nieuwer zijn dan dit pakket; deze README hoort bij de gedownloade release.
