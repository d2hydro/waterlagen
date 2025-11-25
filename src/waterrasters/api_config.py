# %%
import io
import warnings
from typing import Literal

import geopandas as gpd
import requests
from pydantic import BaseModel

warnings.filterwarnings("ignore", ".*non conformant file extension.*", RuntimeWarning)

AHN_VERSION_TYPE = Literal[3, 4, 5, 6]
AHN_CELL_SIZE_TYPE = Literal["05", "5"]
AHN_MODEL_TYPE = Literal["dtm", "dsm"]
AHN_SEVICE_TYPE = Literal["ahn_pdok", "ahn_datastroom"]


class AHNService(BaseModel):
    service: AHN_SEVICE_TYPE = "ahn_pdok"

    def _validate_inputs(
        self, cell_size: AHN_CELL_SIZE_TYPE, ahn_version=AHN_VERSION_TYPE
    ) -> None:
        # validate cell_size (only configurabele for ahn_datastroom)
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
        model_type: AHN_MODEL_TYPE = "dtm",
        cell_size: AHN_CELL_SIZE_TYPE = "05",
        ahn_version: AHN_VERSION_TYPE = 4,
    ):
        """Get tiles url of AHN download service"""
        self._validate_inputs(cell_size, ahn_version)
        if self.service == "ahn_pdok":
            ahn_type = f"{model_type}_{cell_size}m"
            return f"https://service.pdok.nl/rws/ahn/atom/downloads/{ahn_type}/kaartbladindex.json"
        elif self.service == "ahn_datastroom":
            if ahn_version < 6:
                return "https://basisdata.nl/hwh-ahn/AUX/bladwijzer.gpkg"
            else:
                return "https://basisdata.nl/hwh-ahn/AUX/bladwijzer_AHN6.gpkg"
        else:
            raise ValueError(
                "Provide valid values for `model_type`, `cell_size` and `ahn_version`"
            )

    def download_url_field(
        self,
        model_type: AHN_MODEL_TYPE = "dtm",
        cell_size: AHN_CELL_SIZE_TYPE = "05",
        ahn_version: AHN_VERSION_TYPE = 4,
    ):
        self._validate_inputs(cell_size, ahn_version)
        if self.service == "ahn_pdok":
            return "url"
        if self.service == "ahn_datastroom":
            if model_type == "dtm":
                postfix = "M"
            elif model_type == "dsm":
                postfix = "R"
            else:
                raise ValueError(
                    f"{model_type} invalid value for `model_type` (choose dtm or dsm)"
                )
            return f"AHN{ahn_version}_{cell_size}M_{postfix}"

    def get_tiles(
        self,
        model_type: AHN_MODEL_TYPE = "dtm",
        cell_size: AHN_CELL_SIZE_TYPE = "05",
        ahn_version: AHN_VERSION_TYPE = 4,
    ) -> gpd.GeoDataFrame:
        """Get AHN tiles in a GeoDataFrame"""
        self._validate_inputs(cell_size, ahn_version)
        # download data
        url = self.get_tiles_url(
            model_type=model_type, cell_size=cell_size, ahn_version=ahn_version
        )
        response = requests.get(url=url)
        response.raise_for_status()

        # process into GeoDataframe
        if self.service == "ahn_pdok":
            gdf = gpd.GeoDataFrame.from_features(response.json(), crs=28992)
            gdf.set_index("kaartbladNr", inplace=True)
        elif self.service == "ahn_datastroom":
            if ahn_version < 6:
                gdf = gpd.read_file(io.BytesIO(response.content))
                gdf.index = "M_" + gdf.AHN
            else:
                gdf = gpd.read_file(
                    io.BytesIO(response.content), layer="bladindeling_aoi"
                )
                gdf.set_index("bladnaam", inplace=True)

        gdf.index.name = "kaart_index"
        return gdf
