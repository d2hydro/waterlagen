# AGENTS.md

## Project Context

- `waterlagen` is a Python package for downloading and processing GIS base layers for water-management use cases.
- The package code lives in `src/waterlagen`; command-style workflows live in `scripts`; tests live in `tests`; documentation lives in `docs` and is built with MkDocs.
- The main data domains are AHN rasters, BAG/BGT/BRP/Top10NL/Dijkringen vector data, raster tiles, VRT/COG creation, and functional land-use rasters.
- Python support starts at Python 3.11. The project environment is managed with pixi.

## General

- Readability is more important than terseness.
- Keep functions focused and easy to understand.
- Prefer explicit code over clever code.
- Never use one-line `if` statements.
- Do not introduce unnecessary abstractions.
- Keep edits scoped to the requested behavior and the directly affected modules.
- Preserve existing public APIs unless the user explicitly asks for a breaking change.

## Static Typing

- Give public functions and methods explicit type annotations, including return types.
- Prefer existing concrete project or library types over `Any` or `Protocol` when the function depends on a concrete object.
- Use `Protocol` only when a function intentionally supports multiple implementations or needs a small independent interface.
- Do not introduce `Protocol` only to avoid `Any`; first check whether an existing concrete type or simpler type hint is sufficient.
- Keep typing proportional to the complexity of the code.

## Data Structures

- Prefer dataclasses for fixed-shape configuration or domain data.
- Prefer named objects over tuples when tuple positions have domain meaning.
- Prefer typed objects over dictionaries with a fixed set of known keys.
- Keep domain names recognizable: examples include raster grids, download metadata, source layers, land-use classes, tiles, bounds, and CRS metadata.

## Geospatial Rules

- Treat `settings.crs` as the configured project CRS. The current default is `EPSG:28992`.
- Do not silently mix CRS definitions. Use helpers from `waterlagen._crs` where possible:
  - `format_crs`
  - `same_crs`
  - `read_layer_crs_info`
  - `ensure_dataset_crs`
- When reading GeoPackages with possible measured geometries, prefer `waterlagen._geopandas.read_file` over direct `geopandas.read_file`.
- Validate downloaded GeoPackages before replacing existing files.
- For converted or generated files, prefer writing to a temporary file beside the target and replacing the target atomically after validation.
- Keep raster grid and output decisions explicit. Reuse `RasterGrid` and `RasterOutputConfig` instead of duplicating raster profile logic.
- For GeoTIFF output, preserve tiling, compression, overviews, nodata, colormap, and CRS behavior unless the requested change is specifically about those properties.

## Downloads and Data

- Use `pathlib.Path` for filesystem paths.
- Do not hardcode local filesystem paths in package code.
- Use `DataStore` for default data locations:
  - `datastore.source_data_dir`
  - `datastore.processed_data_dir`
  - source-specific directories such as `datastore.ahn_dir`, `datastore.bag_dir`, and `datastore.bgt_dir`
- Respect `overwrite=False` behavior. Avoid re-downloading or replacing large datasets unless explicitly requested or required by the change.
- Keep generated data, large downloads, logs, caches, and local processing outputs out of commits.
- Network-facing code should expose timeouts and raise clear errors for HTTP, malformed payloads, incomplete downloads, and invalid geospatial files.

## Logging and Console Output

- In package modules, use `waterlagen.logger.get_logger(__name__)` and avoid `print()`.
- Scripts may use concise console output for workflow progress, especially where tests already assert it.
- Download progress may write to stdout when the relevant function exposes a `progress` option.
- Do not configure logging at import time in library modules. Configure logging in scripts or application entry points.

## Documentation

- Public functions should have NumPy-style docstrings when they are part of the package API or exposed in MkDocs reference pages.
- Private helpers should have a concise docstring when their behavior is not immediately obvious.
- Keep user-facing documentation in Dutch unless the surrounding page is already English.
- When adding or changing public functionality, update the relevant page under `docs` if behavior, parameters, outputs, or workflows change.
- MkDocs reference pages use `mkdocstrings` with `docstring_style: numpy`.

## Tests

- Add or update focused tests for behavior changes.
- Prefer small synthetic GeoPackages, rasters, fixtures, mocks, and monkeypatching over tests that require large downloads or external services.
- Keep network calls out of unit tests unless the test is explicitly designed as an integration test.
- For temporary files in tests, use pytest fixtures such as `tmp_path`; do not assume system temp directories are writable.
- When modifying download, CRS, raster, or functional land-use behavior, run the directly related tests when practical.

## Commands

- Use pixi commands from the repository root.
- Run targeted tests with `pixi run pytest <test-file-or-node>`.
- Run coverage with `pixi run test-cov`.
- Format Python files with `pixi run ruff format <file>`.
- Lint Python files with `pixi run ruff check <file>`.
- Build docs with `pixi run --environment docs docs-build`.
- Serve docs locally with `pixi run --environment docs docs-serve`.

## What Was Not Carried Over From The Reference

- Dash-specific and JavaScript-specific instructions are not relevant here unless this repository later gains a frontend.
- A strict ban on all `print()` calls is too strong for the current state of this repository because scripts and download progress use stdout intentionally.
- The reference repository mentions a project `Settings` class for all configuration. In this repository, use both `settings` for general settings and `DataStore` for data paths.

## Open Points To Clarify

- Decide whether this repository wants strict Ruff enforcement in CI or only local Ruff usage.
- Decide whether mypy is expected to be run routinely; it is installed in the dev environment but no mypy task is currently defined.
- Decide which tests, if any, are allowed to contact external data services.
- Decide how stable source dataset names should be handled, especially date-stamped datasets such as BRP.
