import io
import warnings
from typing import Literal

import geopandas as gpd
from pydantic import BaseModel

from waterlagen._http import get as http_get

AHN6_ROOT_URL = "https://basisdata.nl/hwh-ahn/AHN6/"
AHN6_DTM_URL = AHN6_ROOT_URL + "02a_DTM_50cm/"

DEFAULT_HTTP_TIMEOUT = 60.0


class AHNService(BaseModel):
    service: Literal["ahn_pdok", "ahn_nl"] = "ahn_nl"

    def _validate_inputs(
        self, cell_size: Literal["05", "5"], ahn_version: Literal[3, 4, 5, 6]
    ) -> None:
        # validate cell_size (only configurable for ahn.nl)
        if cell_size not in ["05", "5"]:
            raise ValueError(f'`cell_size` should be "05" or "5" not {cell_size}')
        if cell_size == "5" and self.service == "ahn_pdok":
            raise ValueError(
                'Only `cell_size="05"` is valid input with `service`="ahn_pdok"'
            )
        if ahn_version not in [3, 4, 5, 6]:
            raise ValueError(
                f"`ahn_version={ahn_version}` is not valid. Only versions 3-6 are implemented(!)"
            )
        if ahn_version != 4 and self.service == "ahn_pdok":
            raise ValueError(
                'Only `ahn_version=4` is valid input with `service`="ahn_pdok"'
            )

    def get_tiles_url(
        self,
        model: Literal["dtm", "dsm"] = "dtm",
        cell_size: Literal["05", "5"] = "05",
        ahn_version: Literal[3, 4, 5, 6] = 4,
    ):
        """Get tiles url of AHN download service"""
        self._validate_inputs(cell_size, ahn_version)
        if self.service == "ahn_pdok":
            ahn_type = f"{model}_{cell_size}m"
            return f"https://service.pdok.nl/rws/ahn/atom/downloads/{ahn_type}/kaartbladindex.json"
        elif self.service == "ahn_nl":
            if ahn_version < 6:
                return "https://basisdata.nl/hwh-ahn/AUX/bladwijzer.gpkg"
            else:
                return "https://basisdata.nl/hwh-ahn/AUX/bladwijzer_AHN6.gpkg"
        else:
            raise ValueError(
                "Provide valid values for `model`, `cell_size` and `ahn_version`"
            )

    def download_url_field(
        self,
        model: Literal["dtm", "dsm"] = "dtm",
        cell_size: Literal["05", "5"] = "05",
        ahn_version: Literal[3, 4, 5, 6] = 4,
    ):
        self._validate_inputs(cell_size, ahn_version)
        if self.service == "ahn_pdok":
            return "url"
        if self.service == "ahn_nl":
            if ahn_version < 6:
                if model == "dtm":
                    postfix = "M"
                elif model == "dsm":
                    postfix = "R"
                else:
                    raise ValueError(
                        f"{model} invalid value for `model` (choose dtm or dsm)"
                    )
                return f"AHN{ahn_version}_{cell_size}M_{postfix}"
            else:
                return f"{model}_{cell_size}"

    def get_tiles(
        self,
        model: Literal["dtm", "dsm"] = "dtm",
        cell_size: Literal["05", "5"] = "05",
        ahn_version: Literal[3, 4, 5, 6] = 4,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
    ) -> gpd.GeoDataFrame:
        """Fetch the AHN tile index from the configured service.

        Parameters
        ----------
        model : {"dtm", "dsm"}, optional
            Terrain or surface model, by default "dtm".
        cell_size : {"05", "5"}, optional
            Raster resolution of 0.5 or 5 metres, by default "05".
        ahn_version : {3, 4, 5, 6}, optional
            AHN version, by default 4. PDOK only supports version 4.
        timeout : float, optional
            Connection and read inactivity timeout in seconds. Defaults to
            ``DEFAULT_HTTP_TIMEOUT``; this is not a total download time limit.

        Returns
        -------
        geopandas.GeoDataFrame
            Tile geometries and download attributes indexed by tile identifier.

        Raises
        ------
        requests.RequestException
            If the index request fails or times out. This request is not retried.
        """
        self._validate_inputs(cell_size, ahn_version)
        # download data
        url = self.get_tiles_url(
            model=model, cell_size=cell_size, ahn_version=ahn_version
        )
        response = http_get(url=url, timeout=timeout)
        response.raise_for_status()

        # process into GeoDataframe
        if self.service == "ahn_pdok":
            gdf = gpd.GeoDataFrame.from_features(response.json(), crs=28992)
            gdf.set_index("kaartbladNr", inplace=True)
        elif self.service == "ahn_nl":
            if ahn_version < 6:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        ".*non conformant file extension.*",
                        RuntimeWarning,
                    )
                    gdf = gpd.read_file(io.BytesIO(response.content))
                gdf.index = "M_" + gdf.AHN
            else:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        ".*non conformant file extension.*",
                        RuntimeWarning,
                    )
                    gdf = gpd.read_file(
                        io.BytesIO(response.content), layer="bladindeling_aoi"
                    )
                years = gdf["jaar"].astype("Int64").astype("string")
                sheets = gdf["bladnaam"].astype("string")
                # The publisher removed leading zeroes from the X coordinate
                # in the file names starting with the 2026 publication.
                names = sheets.where(gdf["jaar"] == 2025, sheets.str.lstrip("0"))
                prefix = f"AHN{ahn_version}_" + years + "_"
                for field, (folder, code) in {
                    "dtm_05": ("02a_DTM_50cm", "M"),
                    "dtm_5": ("02b_DTM_5m", "M5"),
                    "dsm_05": ("03a_DSM_50cm", "R"),
                    "dsm_5": ("03b_DSM_5m", "R5"),
                }.items():
                    gdf[field] = (
                        AHN6_ROOT_URL + folder + "/" + prefix + code + "_" + names + ".TIF"
                    )
                gdf.set_index("bladnaam", inplace=True)

        gdf.index.name = "kaart_index"
        return gdf
