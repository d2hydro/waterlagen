# Bladindeling AHN

De Runmaker gebruikt deze bestanden om de tegeldekking lokaal te controleren. Ze bevatten geen maaiveldhoogtes. De bladindeling en publicatiestatus zijn overgenomen op 27 november 2026.

| Bestand | Inhoud en bron |
| --- | --- |
| `top.parquet` | Bladgrenzen en beschikbaarheid per generatie uit de [AHN4-index van PDOK](https://service.pdok.nl/rws/ahn/atom/downloads/dtm_05m/kaartbladindex.json), de [AHN5-bladwijzer](https://basisdata.nl/hwh-ahn/AUX/bladwijzer.gpkg) en de [AHN5-publicatielijst](https://basisdata.nl/hwh-portal/20230609_tmp/links/nationaal/Nederland/AHN5_DTM05.json). |
| `kilometer.parquet` | Kilometerbladen uit de [AHN6-bladwijzer](https://basisdata.nl/hwh-ahn/AUX/bladwijzer_AHN6.gpkg). |
| `ahn6.json.gz` | Startlijst met gepubliceerde tegels uit de [AHN6-publicatielijst](https://basisdata.nl/hwh-portal/20230609_tmp/links/nationaal/Nederland/AHN6_KM_DTM05.json). De actuele lijst komt in de datastore. |

Bronhouders zijn de deelnemers aan het Actueel Hoogtebestand Nederland. Het Waterschapshuis publiceert de bladwijzers en tegellijsten.
