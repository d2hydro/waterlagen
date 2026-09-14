# Afwateringseenheden

De DEM-dekking is de vereniging van de volledige rechthoekige rasterextents
(`dataset.bounds`) van alle onderliggende TIFFs in de VRT. Overlap telt eenmaal.
De coverage-bepaling leest uitsluitend georeferentiemetadata, geen pixelwaarden
of NoData-maskers. Ook NoData aan de rand of binnen een TIFF valt binnen dekking
en wordt door de bestaande interpolatie gevuld. NoData buiten alle TIFF-extents
blijft NoData.

Bronextents worden in het geheugen gecachet op basis van bestandsversie,
sidecarversies en doel-CRS en op het gevraagde doelgrid gerasteriseerd.
Bij `overwrite=False` worden geldige rasterparen met de actuele coverage-tag
`source_extents_v1` hergebruikt. Ontbrekende of oudere tags leiden tot regeneratie.

::: waterlagen.afwateringseenheden
