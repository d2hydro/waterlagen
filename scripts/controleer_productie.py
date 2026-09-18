"""Check an unpacked production environment without downloading source datasets."""

import runpy
import shlex
import tempfile
import tomllib
from importlib.metadata import version
from pathlib import Path


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((project_dir / "pixi.toml").read_text("utf-8"))
    expected = manifest["pypi-dependencies"]["waterlagen"].removeprefix("==")
    installed = version("waterlagen")
    if installed != expected:
        raise RuntimeError(f"Verwacht Waterlagen {expected}, gevonden {installed}")
    if Path.cwd().resolve() != project_dir:
        raise RuntimeError("Open PowerShell in de projectfolder met pixi.toml")

    import numpy as np
    import pcraster
    import rasterio
    from osgeo import gdal_array
    from rasterio.transform import from_origin

    from waterlagen import datastore

    # Import each entry script without starting production, including BAG.
    for task in manifest["tasks"].values():
        command = task if isinstance(task, str) else task.get("cmd", "")
        arguments = shlex.split(command)
        if len(arguments) == 2 and arguments[0] == "python":
            script_path = project_dir / arguments[1]
            if script_path.resolve() != Path(__file__).resolve():
                runpy.run_path(str(script_path), run_name="_production_import_check")

    values = np.array([[1, 2], [3, 4]], dtype="float32")
    with tempfile.TemporaryDirectory(dir=datastore.data_dir) as temporary:
        raster_path = Path(temporary) / "check.tif"
        with rasterio.open(
            raster_path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="float32",
            crs="EPSG:28992",
            transform=from_origin(120000, 480000, 1, 1),
        ) as raster:
            raster.write(values, 1)
        np.testing.assert_array_equal(gdal_array.LoadFile(str(raster_path)), values)
    pcraster.setclone(2, 2, 1, 120000, 480000)
    field = pcraster.numpy2pcr(pcraster.Scalar, values, -9999)
    np.testing.assert_array_equal(pcraster.pcr2numpy(field + 1, -9999), values + 1)
    print(f"Waterlagen {installed}")
    print(f"Gegevensmap: {datastore.data_dir.resolve()}")
    print("Imports en rastercontrole OK; geen brongegevens gedownload")


if __name__ == "__main__":
    main()
