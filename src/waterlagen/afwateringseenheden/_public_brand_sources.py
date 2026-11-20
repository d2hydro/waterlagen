"""Names and file layouts of supported public burn sources."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicBrandSource:
    provider: str
    layer: str
    filename: str


PUBLIC_BRAND_SOURCES = {
    "bgt_duikers": PublicBrandSource("bgt", "bgt_duiker", "bgt_duikers.gpkg"),
    "bgt_waterdelen": PublicBrandSource("bgt", "bgt_waterdeel", "bgt_waterdelen.gpkg"),
    "bgt_wegdelen": PublicBrandSource("bgt", "bgt_wegdeel", "bgt_wegdelen.gpkg"),
    "top10nl_waterdeel_vlak": PublicBrandSource(
        "top10nl", "top10nl_waterdeel_vlak", "top10nl_Compleet.gpkg"
    ),
    "top10nl_waterdeel_lijn": PublicBrandSource(
        "top10nl", "top10nl_waterdeel_lijn", "top10nl_Compleet.gpkg"
    ),
    "osm_duikers": PublicBrandSource("osm", "osm_culvert", "osm_culverts.gpkg"),
    "osm_canals": PublicBrandSource("osm", "osm_canals", "osm_canals.gpkg"),
    "osm_ditches": PublicBrandSource("osm", "osm_ditches", "osm_ditches.gpkg"),
    "osm_drains": PublicBrandSource("osm", "osm_drains", "osm_drains.gpkg"),
    "osm_streams": PublicBrandSource("osm", "osm_streams", "osm_streams.gpkg"),
}
