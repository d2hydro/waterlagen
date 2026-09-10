"""TEMPORARY: benchmark DEM coverage only; delete this script to remove profiling.

Run with pixi run --environment afwateringseenheden python scripts/profile_dem_coverage.py.
Writes isolated outputs under data; never runs lddcreate or downloads input data.
"""

import json
import time
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import box

from waterlagen import datastore
from waterlagen.afwateringseenheden import raster as ra
from waterlagen.afwateringseenheden._coverage import _source_extent, _vrt_sources

BOUNDS = (168000.0, 358000.0, 182000.0, 372000.0)


def main() -> None:
    root = Path("data/profiling_afwateringseenheden") / time.strftime(
        "%Y%m%d_%H%M%S_coverage"
    )
    root.mkdir(parents=True)
    print(root.resolve(), flush=True)
    source_path = datastore.ahn_dir / "dtm_05/dtm_05.vrt"
    sources = _vrt_sources(
        source_path, (source_path.stat().st_mtime_ns, source_path.stat().st_size)
    )
    intersecting_sources = 0
    for path in set(sources):
        with rasterio.open(path) as dataset:
            if box(*dataset.bounds).intersection(box(*BOUNDS)).area:
                intersecting_sources += 1
    watersysteem_path = datastore.afwateringseenheden_path / "watersysteem.gpkg"
    original_coverage = ra._coverage_mask
    original_fill = ra._fill_dem_nodata
    original_warp = ra.reproject
    original_gdal_fill = ra.fillnodata
    records = {}
    arrays = {}

    def coverage(source, grid):
        started = time.perf_counter()
        result = original_coverage(source, grid)
        records["coverage_seconds"] = time.perf_counter() - started
        arrays["coverage"] = result
        print("coverage", records["coverage_seconds"], flush=True)
        return result

    def warp(*args, **kwargs):
        started = time.perf_counter()
        result = original_warp(*args, **kwargs)
        records["read_resampling_seconds"] = time.perf_counter() - started
        print("read/resampling", records["read_resampling_seconds"], flush=True)
        return result

    def gdal_fill(image, **kwargs):
        records["actual_interpolation_targets"] = int((kwargs["mask"] == 0).sum())
        assert np.all(kwargs["mask"][~arrays["coverage"]] != 0)
        assert np.all(image[~arrays["coverage"]] == kwargs["nodata"])
        return original_gdal_fill(image, **kwargs)

    def fill(data, mask=None):
        arrays["before"] = data
        started = time.perf_counter()
        result = original_fill(data, mask)
        records["interpolation_seconds"] = time.perf_counter() - started
        arrays["after"] = result
        print("interpolation", records["interpolation_seconds"], flush=True)
        return result

    ra._coverage_mask = coverage
    ra.reproject = warp
    ra._fill_dem_nodata = fill
    ra.fillnodata = gdal_fill
    _source_extent.cache_clear()
    _vrt_sources.cache_clear()
    try:
        for label in ("cold", "warm"):
            records.clear()
            arrays.clear()
            start = time.perf_counter()
            output = ra.prepare_watersysteem_rasters(
                box(*BOUNDS),
                burn_depth_m=100,
                ahn_vrt_path=source_path,
                watersysteem_path=watersysteem_path,
                output_dir=root / label,
                resolution_m=2,
                overwrite=True,
            )
            records["prepare_seconds"] = time.perf_counter() - start
            valid = np.isfinite(arrays["before"])
            covered = arrays["coverage"]
            after_valid = np.isfinite(arrays["after"])
            candidates = covered & ~valid
            assert np.array_equal(arrays["before"][valid], arrays["after"][valid])
            assert not after_valid[~covered].any()
            assert after_valid[covered].all()
            assert records["actual_interpolation_targets"] == int(candidates.sum())
            records.update(
                source_tiffs=len(set(sources)),
                intersecting_source_tiffs=intersecting_sources,
                bounds=BOUNDS,
                shape=valid.shape,
                coverage_cells=int(covered.sum()),
                valid_before=int(valid.sum()),
                nodata_before=int((~valid).sum()),
                nodata_inside_before=int(candidates.sum()),
                nodata_outside_before=int((~covered & ~valid).sum()),
                valid_after=int(after_valid.sum()),
                nodata_after=int((~after_valid).sum()),
                nodata_inside_after=int((covered & ~after_valid).sum()),
                nodata_outside_after=int((~covered & ~after_valid).sum()),
                interpolated=int((~valid & after_valid).sum()),
                valid_values_unchanged=True,
                extent_cache=_source_extent.cache_info()._asdict(),
            )
            with rasterio.open(output.dem_path) as dem:
                profile = dem.profile.copy()
                values = dem.read(1, masked=True)
                assert np.array_equal(~np.ma.getmaskarray(values), after_valid)
                assert dem.bounds == BOUNDS
                assert dem.res == (2, 2)
                records["stored_valid_after"] = int(values.count())
            profile.update(
                dtype="uint8",
                nodata=None,
                count=2,
                tiled=True,
                blockxsize=512,
                blockysize=512,
                compress="deflate",
            )
            diagnostic_before = np.zeros(valid.shape, dtype="uint8")
            diagnostic_before[valid] = 1
            diagnostic_before[candidates] = 2
            diagnostic_after = diagnostic_before.copy()
            diagnostic_after[candidates & after_valid] = 3
            with rasterio.open(
                root / label / "coverage_diagnostic.tif", "w", **profile
            ) as dest:
                dest.write(diagnostic_before, 1)
                dest.write(diagnostic_after, 2)
                dest.set_band_description(1, "before_interpolation")
                dest.set_band_description(2, "after_interpolation")
                dest.update_tags(
                    classes="0=outside;1=original_valid;2=covered_nodata;3=interpolated"
                )
            (root / f"{label}.json").write_text(
                json.dumps(records, indent=2), encoding="utf-8"
            )
            print(json.dumps(records, indent=2), flush=True)
    finally:
        ra._coverage_mask = original_coverage
        ra.reproject = original_warp
        ra._fill_dem_nodata = original_fill
        ra.fillnodata = original_gdal_fill


if __name__ == "__main__":
    main()
