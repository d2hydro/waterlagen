"""TEMPORARY PROFILING: remove this file to remove all instrumentation.

Runs the unchanged production workflow in a fresh, isolated output directory.
Use pixi run --environment afwateringseenheden python scripts/profile_afwateringseenheden_tile.py.
No source data is downloaded or replaced. Timings are inclusive and nested.
"""

import argparse
import functools
import json
import linecache
import multiprocessing
import os
import sys
import time
import xml.etree.ElementTree as ET
from multiprocessing.synchronize import Event
from pathlib import Path

import numpy as np
import psutil
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from shapely.geometry import box

from waterlagen import datastore
from waterlagen.afwateringseenheden import pcraster as pc
from waterlagen.afwateringseenheden import raster as ra
from waterlagen.afwateringseenheden import tiles
from waterlagen.raster.grid import RasterGrid

BOUNDS = (168000.0, 358000.0, 182000.0, 372000.0)


def sample_process(pid: int, path: Path, stop: Event) -> None:
    """Sample in another process, including while native code holds the GIL."""
    process = psutil.Process(pid)
    with path.open("w") as stream:
        while not stop.is_set():
            try:
                memory = process.memory_info()
                stream.write(
                    json.dumps({"time": time.perf_counter(), **memory._asdict()}) + "\n"
                )
                stream.flush()
            except psutil.NoSuchProcess:
                break
            stop.wait(0.1)


def describe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.ndarray):
        return {"shape": value.shape, "dtype": str(value.dtype), "bytes": value.nbytes}
    if isinstance(value, rasterio.io.DatasetReader):
        return dataset_info(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [describe(item) for item in value]
    return type(value).__name__


def dataset_info(source: rasterio.io.DatasetReader) -> dict[str, object]:
    return {
        "path": source.name,
        "bounds": tuple(source.bounds),
        "shape": source.shape,
        "dtype": source.dtypes,
        "resolution": source.res,
        "crs": str(source.crs),
        "blocks": source.block_shapes,
        "compression": str(source.compression),
        "overviews": source.overviews(1),
        "scales": source.scales,
        "offsets": source.offsets,
        "nodata": source.nodata,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["benchmark", "direct"], default="benchmark")
    args = parser.parse_args()
    output = Path("data/profiling_afwateringseenheden") / (
        time.strftime("%Y%m%d_%H%M%S") + "_" + args.mode
    )
    output.mkdir(parents=True, exist_ok=False)
    print(f"Profiling output: {output.resolve()}", flush=True)
    source_path = datastore.ahn_dir / "dtm_05/dtm_05.vrt"
    watersysteem = datastore.afwateringseenheden_path / "watersysteem.gpkg"
    if not source_path.is_file() or not watersysteem.is_file():
        raise FileNotFoundError(f"Required local inputs: {source_path}, {watersysteem}")
    process = psutil.Process()
    events = (output / "events.jsonl").open("w")

    def emit(record):
        events.write(json.dumps(record, default=str) + "\n")
        events.flush()

    def instrument(module, name):
        original = getattr(module, name)

        @functools.wraps(original)
        def measured(*values, **keywords):
            label = f"{module.__name__}.{name}"
            before_io = process.io_counters()
            before_rss = process.memory_info().rss
            inputs = {
                "args": describe(values),
                "kwargs": {key: describe(value) for key, value in keywords.items()},
            }
            start = time.perf_counter()
            emit({"event": "start", "step": label, "time": start, "inputs": inputs})
            result = None
            try:
                result = original(*values, **keywords)
                return result
            finally:
                end = time.perf_counter()
                after_io = process.io_counters()
                record = {
                    "event": "end",
                    "step": label,
                    "start": start,
                    "end": end,
                    "seconds": end - start,
                    "inputs": inputs,
                    "output": describe(result),
                    "rss_before": before_rss,
                    "rss_after": process.memory_info().rss,
                    "read_bytes": after_io.read_bytes - before_io.read_bytes,
                    "write_bytes": after_io.write_bytes - before_io.write_bytes,
                }
                emit(record)
                if end - start > 0.2:
                    print(f"{label}: {end - start:.3f} s", flush=True)

        setattr(module, name, measured)

    # Selected line timings isolate reads, casts, burn arrays and PCRaster calls.
    # Other functions use wrappers, avoiding per-polygon tracing overhead.
    traced = {
        ra.prepare_watersysteem_rasters.__code__,
        pc._calculate_pcraster_maps.__code__,
        ra._validate_rasters.__code__,
        tiles._has_segment_cells.__code__,
    }
    active = {}

    def trace(frame, event, arg):
        if frame.f_code not in traced:
            return None
        now = time.perf_counter()
        key = id(frame)
        if event in ("line", "return"):
            previous = active.pop(key, None)
            if previous is not None:
                lineno, start = previous
                emit(
                    {
                        "event": "line",
                        "function": frame.f_code.co_name,
                        "file": frame.f_code.co_filename,
                        "line": lineno,
                        "source": linecache.getline(
                            frame.f_code.co_filename, lineno
                        ).strip(),
                        "start": start,
                        "end": now,
                        "seconds": now - start,
                    }
                )
            if event == "line":
                active[key] = (frame.f_lineno, now)
        return trace

    native = pc.require_pcraster()
    for module, names in [
        (
            ra,
            [
                "reproject",
                "_resample_dem",
                "_fill_dem_nodata",
                "_features_in_project_crs",
                "_rasterize_mask",
                "_cast_dem_data",
                "_write_dem",
                "_segment_raster",
                "_write_segment_raster",
                "_validate_rasters",
            ],
        ),
        (
            pc,
            [
                "_calculate_pcraster_maps",
                "_write_raster",
                "_validate_output_grid",
                "_segment_ids_by_fid",
                "_polygonize_subcatchments",
                "_write_subcatchment_geopackage",
            ],
        ),
        (
            tiles,
            [
                "prepare_watersysteem_rasters",
                "calculate_subcatchments",
                "_has_segment_cells",
                "_usable_subcatchments_for_tile",
                "_merge_subcatchments",
                "_write_merged_subcatchments",
            ],
        ),
        (native, ["numpy2pcr", "lddcreate", "subcatchment", "pcr2numpy"]),
        (rasterio, ["open"]),
    ]:
        for name in names:
            instrument(module, name)

    metadata = {
        "bounds": BOUNDS,
        "source": str(source_path),
        "watersysteem": str(watersysteem),
        "rasterio": rasterio.__version__,
        "gdal": rasterio.__gdal_version__,
        "python": sys.version,
        "memory": psutil.virtual_memory()._asdict(),
        "sources": [],
    }
    with rasterio.open(source_path) as source:
        metadata["vrt"] = dataset_info(source)
        window = from_bounds(*BOUNDS, source.transform)
        metadata["window"] = [
            window.col_off,
            window.row_off,
            window.width,
            window.height,
        ]
        root = ET.parse(source_path).getroot()
        for node in root.findall(".//SimpleSource") + root.findall(".//ComplexSource"):
            rectangle = node.find("DstRect")
            if rectangle is None:
                continue
            x, y, w, h = [
                float(rectangle.attrib[key])
                for key in ("xOff", "yOff", "xSize", "ySize")
            ]
            if (
                x + w <= window.col_off
                or x >= window.col_off + window.width
                or y + h <= window.row_off
                or y >= window.row_off + window.height
            ):
                continue
            filename = node.find("SourceFilename")
            path = Path(filename.text)
            if filename.get("relativeToVRT") == "1":
                path = source_path.parent / path
            if not path.is_file():
                raise FileNotFoundError(f"Local VRT source missing: {path}")
            with rasterio.open(path) as tile_source:
                metadata["sources"].append(
                    {**dataset_info(tile_source), "file_bytes": path.stat().st_size}
                )
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    stop = multiprocessing.Event()
    sampler = multiprocessing.Process(
        target=sample_process, args=(os.getpid(), output / "memory.jsonl", stop)
    )
    sampler.start()
    started = time.perf_counter()
    try:
        if args.mode == "benchmark":
            sys.settrace(trace)
            tiles.calculate_afwateringseenheden_tiles(
                box(170000, 360000, 180000, 370000),
                tile_ids=["170000_360000_180000_370000"],
                tile_size_m=10000,
                tile_buffer_m=2000,
                burn_depth_m=100,
                max_fill_depth_m=50,
                resolution_m=2,
                ahn_vrt_path=source_path,
                watersysteem_path=watersysteem,
                output_dir=output / "tiles",
                merged_output_path=output / "merged.gpkg",
                overwrite=True,
            )
        else:
            with rasterio.open(source_path) as source:
                before_io = process.io_counters()
                start = time.perf_counter()
                data = source.read(
                    1,
                    window=from_bounds(*BOUNDS, source.transform),
                    out_shape=(7000, 7000),
                    out_dtype="float64",
                    resampling=Resampling.bilinear,
                    boundless=True,
                    fill_value=source.nodata,
                )
                end = time.perf_counter()
                after_io = process.io_counters()
                emit(
                    {
                        "event": "direct_read",
                        "start": start,
                        "end": end,
                        "seconds": end - start,
                        "output": describe(data),
                        "read_bytes": after_io.read_bytes - before_io.read_bytes,
                        "write_bytes": after_io.write_bytes - before_io.write_bytes,
                        "nodata_cells": int((data == source.nodata).sum()),
                    }
                )
                print(
                    f"Direct window read: {end - start:.3f} s",
                    flush=True,
                )
                grid = RasterGrid.from_bounds(BOUNDS, resolution=2, crs=str(source.crs))
                reference = np.full((7000, 7000), np.nan, dtype=np.float64)
                ra.reproject(
                    source=rasterio.band(source, 1),
                    destination=reference,
                    src_transform=source.transform,
                    src_crs=source.crs,
                    src_nodata=source.nodata,
                    dst_transform=grid.transform,
                    dst_crs=grid.crs,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
                missing = 0
                mismatch = 0
                different = 0
                max_difference = 0.0
                absolute_sum = 0.0
                valid_count = 0
                for row in range(0, 7000, 100):
                    expected = reference[row : row + 100]
                    actual = data[row : row + 100]
                    valid = np.isfinite(expected)
                    direct_valid = actual != source.nodata
                    common = valid & direct_valid
                    differences = np.abs(expected[common] - actual[common])
                    missing += int((~valid).sum())
                    mismatch += int((valid != direct_valid).sum())
                    different += int((differences > 1e-6).sum())
                    max_difference = max(
                        max_difference, float(differences.max(initial=0))
                    )
                    absolute_sum += float(differences.sum())
                    valid_count += differences.size
                emit(
                    {
                        "event": "comparison",
                        "warp_nodata_cells": missing,
                        "nodata_mismatch": mismatch,
                        "different_cells": different,
                        "max_difference_stored_units": max_difference,
                        "mean_absolute_difference_stored_units": absolute_sum
                        / valid_count,
                    }
                )
    finally:
        sys.settrace(None)
        emit({"event": "total", "seconds": time.perf_counter() - started})
        stop.set()
        sampler.join()
        events.close()
        files = {
            str(path.relative_to(output)): path.stat().st_size
            for path in output.rglob("*")
            if path.is_file()
        }
        (output / "files.json").write_text(
            json.dumps(files, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
