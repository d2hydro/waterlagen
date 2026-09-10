"""Temporary benchmark instrumentation; production functions remain unchanged.

Run in the afwateringseenheden pixi environment. All outputs live under data.
Use discover, serial, or parallel; each run has unique output directories.
"""

import argparse
import functools
import hashlib
import json
import logging
import multiprocessing
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import psutil
import rasterio
from shapely.geometry import box
from shapely.ops import unary_union

from waterlagen import _geopandas as wgpd
from waterlagen import datastore
from waterlagen.afwateringseenheden import (
    _coverage,
    pcraster as pc,
    raster as ra,
    tiles,
)
from waterlagen.raster.grid import RasterGrid


@dataclass(frozen=True)
class Job:
    name: str
    size: int
    center: tuple[int, int]
    source: str
    watersysteem: str
    output: str


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def bounds(center: tuple[int, int], size: int, buffer: int = 0) -> tuple[int, ...]:
    x, y = center
    half = size // 2 + buffer
    return x - half, y - half, x + half, y + half


def discover(root: Path) -> None:
    source = datastore.ahn_dir / "dtm_05/dtm_05.vrt"
    watersysteem = datastore.afwateringseenheden_path / "watersysteem.gpkg"
    paths = _coverage._vrt_sources(source, _coverage._file_version(source))
    extents = []
    for path in paths:
        with rasterio.open(path) as dataset:
            assert str(dataset.crs) == "EPSG:28992"
            extents.append(box(*dataset.bounds))
    coverage = unary_union(extents)
    segments = wgpd.read_file(watersysteem, layer="hydroobject_segment")
    preferred = segments.union_all().centroid
    minx, miny, maxx, maxy = coverage.bounds
    candidates = []
    for x in range(int(minx) + 12000, int(maxx) - 12000 + 1, 1000):
        for y in range(int(miny) + 12000, int(maxy) - 12000 + 1, 1000):
            if coverage.covers(box(*bounds((x, y), 20000, 2000))):
                candidates.append((x, y))
    candidates.sort(key=lambda p: (p[0] - preferred.x) ** 2 + (p[1] - preferred.y) ** 2)
    if not candidates:
        raise ValueError("No fully covered 24 km square in available TIFF extents")
    center = candidates[0]
    checks = []
    with rasterio.open(source) as dataset:
        for size in (5000, 10000, 20000):
            area = bounds(center, size, 2000)
            grid = RasterGrid.from_bounds(area, resolution=2, crs="EPSG:28992")
            mask = _coverage._coverage_mask(dataset, grid)
            assert mask.all()
            checks.append(
                dict(
                    size=size,
                    bounds=area,
                    cells=mask.size,
                    coverage_cells=int(mask.sum()),
                    source_tiffs=sum(
                        e.intersection(box(*area)).area > 0 for e in extents
                    ),
                    segment_features=int(segments.intersects(box(*area)).sum()),
                )
            )
    info = dict(
        center=center,
        source=str(source),
        watersysteem=str(watersysteem),
        checks=checks,
        source_tiffs=len(paths),
        candidates=len(candidates),
        cpu_physical=psutil.cpu_count(logical=False),
        cpu_logical=psutil.cpu_count(),
        memory=psutil.virtual_memory()._asdict(),
        platform=platform.platform(),
        python=sys.version,
        rasterio=rasterio.__version__,
        gdal=rasterio.__gdal_version__,
        pcraster=getattr(pc.require_pcraster(), "__version__", "unknown"),
        thread_environment={
            k: os.environ.get(k)
            for k in (
                "GDAL_NUM_THREADS",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "PCRASTER_NR_WORKER_THREADS",
            )
        },
        production_hashes={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path("src/waterlagen/afwateringseenheden").glob("*.py")
        },
    )
    save(root / "discovery.json", info)
    print(json.dumps(info, indent=2), flush=True)


def run_job(job: Job) -> dict:
    output = Path(job.output)
    output.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(
        filename=output / "workflow.log",
        level=logging.INFO,
        force=True,
        format="%(asctime)s %(process)d %(name)s %(message)s",
    )
    process = psutil.Process()
    timings = {}
    original_functions = []
    events = (output / "events.jsonl").open("w", encoding="utf-8")
    metrics = {}

    def wrap(module, name, label):
        original = getattr(module, name)
        original_functions.append((module, name, original))

        @functools.wraps(original)
        def measured(*args, **kwargs):
            start = time.perf_counter()
            cpu = process.cpu_times()
            events.write(json.dumps(dict(event="start", step=label, time=start)) + "\n")
            events.flush()
            try:
                result = original(*args, **kwargs)
                elapsed = time.perf_counter() - start
                timings[label] = timings.get(label, 0) + elapsed
                if label == "coverage":
                    metrics["coverage_cells"] = int(result.sum())
                if label == "interpolation":
                    metrics["valid_dem_cells"] = int(np.isfinite(result).sum())
                    metrics["nodata_before"] = int((~np.isfinite(args[0])).sum())
                after_cpu = process.cpu_times()
                events.write(
                    json.dumps(
                        dict(
                            event="end",
                            step=label,
                            seconds=elapsed,
                            time=time.perf_counter(),
                            cpu_seconds=after_cpu.user
                            + after_cpu.system
                            - cpu.user
                            - cpu.system,
                            rss=process.memory_info().rss,
                        )
                    )
                    + "\n"
                )
                events.flush()
                return result
            except Exception:
                logging.exception("Benchmark step failed: %s", label)
                raise

        setattr(module, name, measured)

    native = pc.require_pcraster()
    for module, name, label in [
        (tiles, "prepare_watersysteem_rasters", "prepare"),
        (ra, "reproject", "dem_read_resampling"),
        (ra, "_coverage_mask", "coverage"),
        (ra, "_fill_dem_nodata", "interpolation"),
        (ra, "_features_in_project_crs", "vector_read"),
        (ra, "_rasterize_mask", "vector_rasterize"),
        (ra, "_segment_raster", "segment_rasterize"),
        (ra, "_write_dem", "dem_write"),
        (ra, "_write_segment_raster", "segment_write"),
        (ra, "_validate_rasters", "raster_validation"),
        (native, "lddcreate", "lddcreate"),
        (native, "subcatchment", "subcatchment"),
        (pc, "_polygonize_subcatchments", "polygonize"),
        (pc, "_write_raster", "pcr_raster_write"),
        (pc, "_write_subcatchment_geopackage", "polygon_write"),
        (tiles, "_usable_subcatchments_for_tile", "clip_boundary"),
        (tiles, "_merge_subcatchments", "merge"),
        (tiles, "_write_merged_subcatchments", "merge_write"),
    ]:
        wrap(module, name, label)

    # Only trace the short orchestration function to isolate NumPy burn expressions.
    # Native lddcreate is timed by its wrapper, without line tracing its internals.
    trace_state = {}
    burn_seconds = 0.0
    import inspect

    source_lines, first_line = inspect.getsourcelines(ra.prepare_watersysteem_rasters)
    burn_start = first_line + next(
        i for i, line in enumerate(source_lines) if "burn_depth =" in line
    )
    burn_end = first_line + next(
        i for i, line in enumerate(source_lines) if "            _write_dem(" in line
    )

    def trace(frame, event, arg):
        nonlocal burn_seconds
        if frame.f_code is not ra.prepare_watersysteem_rasters.__code__:
            return None
        now = time.perf_counter()
        previous = trace_state.pop(id(frame), None)
        if previous is not None and burn_start <= previous[0] < burn_end:
            burn_seconds += now - previous[1]
        if event == "line":
            trace_state[id(frame)] = (frame.f_lineno, now)
        return trace

    start = time.perf_counter()
    cpu_before = process.cpu_times()
    io_before = process.io_counters()
    try:
        sys.settrace(trace)
        core = bounds(job.center, job.size)
        result = tiles.calculate_afwateringseenheden_tiles(
            box(*core),
            tile_size_m=job.size,
            origin_x=core[0],
            origin_y=core[1],
            tile_buffer_m=2000,
            burn_depth_m=100,
            max_fill_depth_m=50,
            resolution_m=2,
            ahn_vrt_path=Path(job.source),
            watersysteem_path=Path(job.watersysteem),
            output_dir=output / "tiles",
            merged_output_path=output / "merged.gpkg",
            overwrite=True,
        )
        total = time.perf_counter() - start
        sys.settrace(None)
        assert len(result.tile_results) == 1
        tile_result = result.tile_results[0]
        assert tile_result.subcatchments is not None
        timings["burn"] = burn_seconds
        timings["vector_read_rasterize_burn"] = sum(
            timings[k]
            for k in ("vector_read", "vector_rasterize", "segment_rasterize", "burn")
        )
        timings["polygonize_write"] = sum(
            timings[k]
            for k in ("polygonize", "pcr_raster_write", "polygon_write", "merge_write")
        )
        after_cpu = process.cpu_times()
        after_io = process.io_counters()
        metrics.update(
            job=asdict(job),
            pid=os.getpid(),
            start=start,
            end=start + total,
            total=total,
            timings=timings,
            core_bounds=core,
            cells=((job.size + 4000) // 2) ** 2,
            features=len(result.merged_subcatchments),
            buffered_features=len(tile_result.subcatchments.subcatchments),
            boundary_issue=tile_result.has_boundary_issue,
            peak_wset=process.memory_info().peak_wset,
            cpu_seconds=after_cpu.user
            + after_cpu.system
            - cpu_before.user
            - cpu_before.system,
            io_read_bytes=after_io.read_bytes - io_before.read_bytes,
            io_write_bytes=after_io.write_bytes - io_before.write_bytes,
        )
        save(output / "result.json", metrics)
        print(
            f"Completed {job.name}: total={total:.3f}s ldd={timings['lddcreate']:.3f}s",
            flush=True,
        )
        return metrics
    finally:
        sys.settrace(None)
        for module, name, original in reversed(original_functions):
            setattr(module, name, original)
        events.close()


def run_batch(root: Path, jobs: list[Job], workers: int) -> None:
    parent = psutil.Process()
    samples = (root / "samples.jsonl").open("w", encoding="utf-8")
    started = time.perf_counter()
    results = []
    failures = []
    peak_rss = 0
    minimum_available = psutil.virtual_memory().available
    # Explicit spawn isolates PCRaster global clone/options and GDAL handles.
    with ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    ) as executor:
        futures = {executor.submit(run_job, job): job for job in jobs}
        remaining = set(futures)
        last_status = started
        while remaining:
            records = []
            for process in [parent, *parent.children(recursive=True)]:
                try:
                    memory = process.memory_info()
                    cpu = process.cpu_times()
                    io = process.io_counters()
                    records.append(
                        dict(
                            pid=process.pid,
                            rss=memory.rss,
                            private=memory.private,
                            cpu=cpu.user + cpu.system,
                            read_bytes=io.read_bytes,
                            write_bytes=io.write_bytes,
                            threads=process.num_threads(),
                        )
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            now = time.perf_counter()
            memory = psutil.virtual_memory()
            peak_rss = max(peak_rss, sum(r["rss"] for r in records))
            minimum_available = min(minimum_available, memory.available)
            samples.write(
                json.dumps(
                    dict(
                        time=now,
                        processes=records,
                        available=memory.available,
                        system_cpu_percent=psutil.cpu_percent(),
                        disk=psutil.disk_io_counters()._asdict(),
                    )
                )
                + "\n"
            )
            samples.flush()
            for future in list(remaining):
                if future.done():
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        failures.append(
                            dict(job=asdict(futures[future]), error=repr(exc))
                        )
                    remaining.remove(future)
            if now - last_status >= 30:
                print(
                    f"{root.name}: elapsed={now - started:.0f}s pending={len(remaining)} RSS={sum(r['rss'] for r in records) / 1e9:.2f}GB",
                    flush=True,
                )
                last_status = now
            time.sleep(0.1)
    samples.close()
    save(
        root / "batch.json",
        dict(
            workers=workers,
            wall_seconds=time.perf_counter() - started,
            peak_total_rss=peak_rss,
            minimum_available_ram=minimum_available,
            results=results,
            failures=failures,
        ),
    )
    if failures:
        raise RuntimeError(f"{len(failures)} benchmark jobs failed; see batch.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["discover", "serial", "parallel"])
    parser.add_argument(
        "--root", type=Path, default=Path("data/benchmark_afwateringseenheden_scaling")
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--size", type=int, default=5000)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.mode == "discover":
        discover(args.root)
        return
    metadata = json.loads((args.root / "discovery.json").read_text())
    batch = args.root / f"{time.strftime('%Y%m%d_%H%M%S')}_{args.mode}_{args.workers}w"
    batch.mkdir()
    if args.mode == "serial":
        if args.workers != 1:
            raise ValueError("Tile-size benchmarks must run serially")
        sizes = [5000, 5000, 10000, 10000, 20000, 20000]
        centers = [tuple(metadata["center"])] * len(sizes)
    else:
        sizes = [args.size] * args.jobs
        x, y = metadata["center"]
        # Four adjacent distinct tiles; same workload and order for every worker count.
        centers = [
            (x + dx * args.size // 2, y + dy * args.size // 2)
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1))
        ]
        centers = [centers[i % 4] for i in range(args.jobs)]
        with rasterio.open(metadata["source"]) as source:
            for center in centers:
                grid = RasterGrid.from_bounds(
                    bounds(center, args.size, 2000), resolution=2, crs="EPSG:28992"
                )
                assert _coverage._coverage_mask(source, grid).all()
    jobs = [
        Job(
            f"{size // 1000}km_{i + 1}",
            size,
            center,
            metadata["source"],
            metadata["watersysteem"],
            str(batch / f"{size // 1000}km_{i + 1}"),
        )
        for i, (size, center) in enumerate(zip(sizes, centers))
    ]
    save(batch / "jobs.json", [asdict(job) for job in jobs])
    print(f"Benchmark output: {batch.resolve()}", flush=True)
    run_batch(batch, jobs, args.workers)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
