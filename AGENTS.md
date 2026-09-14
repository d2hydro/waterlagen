# AGENTS.md

## Project Context

- `waterlagen` is a Python package for downloading, processing, and producing standardized GIS base layers for water-management use cases.
- Package code lives in `src/waterlagen`.
- Command-style workflows live in `scripts`.
- Tests live in `tests`.
- Documentation lives in `docs` and is built with MkDocs.
- The main data domains include AHN rasters, BAG, BGT, BRP, Top10NL, Dijkringen, raster tiles, VRT/COG creation, functional land-use rasters, and derived datasets.
- Python support starts at Python 3.11.
- The project environment is managed with pixi.

## General

- Readability is more important than terseness.
- Keep functions focused and easy to understand.
- Prefer explicit code over clever code.
- Prefer linear workflow code with named intermediate values.
- Never use one-line `if` statements.
- Do not introduce unnecessary abstractions.
- Keep edits scoped to the requested behavior and directly affected modules.
- Preserve existing public APIs unless a breaking change is explicitly requested.
- Before changing behavior, inspect the existing implementation, tests, and relevant documentation.
- Do not make unrelated cleanup changes as part of a focused task.

## Design and Reuse

- Before adding functionality, inspect existing shared helpers and reuse them where appropriate.
- Put behavior shared by multiple downloaders or processors in a common helper instead of duplicating it.
- Keep domain-specific behavior in the domain module.
- Keep generic download, validation, progress, logging, filesystem, and conversion behavior in shared modules.
- Use small private helpers for validation, cache or reuse decisions, and individual processing steps.
- Make cache, reuse, and overwrite behavior explicit in code and docstrings.
- Avoid abstractions that hide important filesystem, download, geospatial, or conversion behavior.

## Static Typing

- Give public functions and methods explicit type annotations, including return types.
- Prefer existing concrete project or library types over `Any` or `Protocol` when code depends on a concrete object.
- Use `Protocol` only when a function intentionally supports multiple implementations or needs a small independent interface.
- Do not introduce `Protocol` only to avoid `Any`; first check whether an existing concrete type or simpler type hint is sufficient.
- Keep typing proportional to the complexity of the code.

## Data Structures

- Prefer dataclasses for fixed-shape configuration or domain data.
- Prefer named objects over tuples when tuple positions have domain meaning.
- Prefer typed objects over dictionaries with a fixed set of known keys.
- Keep domain names recognizable. Examples include raster grids, download metadata, source layers, land-use classes, tiles, bounds, and CRS metadata.

## Geospatial Rules

- Treat `settings.crs` as the configured project CRS. The current default is `EPSG:28992`.
- Do not silently mix CRS definitions.
- Use helpers from `waterlagen._crs` where possible:

  - `format_crs`
  - `same_crs`
  - `read_layer_crs_info`
  - `ensure_dataset_crs`
- When reading GeoPackages with possible measured geometries, prefer `waterlagen._geopandas.read_file` over direct `geopandas.read_file`.
- Validate downloaded GeoPackages before replacing existing files.
- For converted or generated files, prefer writing to a temporary file beside the target and replacing the target atomically after validation.
- Keep raster grid and output decisions explicit.
- Reuse `RasterGrid` and `RasterOutputConfig` instead of duplicating raster profile logic.
- For GeoTIFF output, preserve tiling, compression, overviews, nodata, colormap, and CRS behavior unless the requested change specifically concerns those properties.
- Do not silently alter geometry types, CRS, raster resolution, nodata values, or output schemas.

## Downloads and Data

- Use `pathlib.Path` for filesystem paths.
- Do not hardcode local filesystem paths in package code.
- Use `DataStore` for default data locations, including:

  - `datastore.source_data_dir`
  - `datastore.processed_data_dir`
  - source-specific directories such as `datastore.ahn_dir`, `datastore.bag_dir`, and `datastore.bgt_dir`
- Respect `overwrite=False` behavior.
- Avoid re-downloading or replacing large datasets unless explicitly requested or required by the change.
- Keep generated data, large downloads, logs, caches, and local processing outputs out of commits.
- Network-facing code should expose timeouts and raise clear errors for HTTP failures, malformed payloads, incomplete downloads, and invalid geospatial files.
- Prefer shared helpers for streaming downloads, temporary files, payload validation, progress reporting, and atomic replacement.
- Do not call `zipfile.ZipFile.testzip()` automatically for large archives or cache checks; it reads every member. Prefer structural ZIP validation and validate selected members while processing unless a full CRC scan is explicitly required.

## Logging and Console Output

- In package modules, use `waterlagen.logger.get_logger(__name__)` and avoid `print()`.
- Scripts may use concise console output for workflow progress, especially where tests already assert it.
- Download progress may write to stdout when the relevant function exposes a `progress` option.
- Progress output must identify what is being downloaded or processed; a percentage without a file or operation name is insufficient.
- Log user-visible workflow steps at INFO level, including download, reuse or skip, extraction, conversion, validation, processing, and completion.
- Use DEBUG only for diagnostic details not required to understand normal workflow progress.
- Prefer structured logger arguments, for example:
  `logger.info("Downloading %s to %s", description, target_path)`.
- Put shared download progress and logging behavior in `_downloads.py` instead of implementing downloader-specific variants.
- Do not configure logging at import time in library modules. Configure logging in scripts or application entry points.

## Tests

- Add or update focused tests for behavior changes.
- Prefer small synthetic GeoPackages, rasters, fixtures, mocks, and monkeypatching over tests requiring large downloads or external services.
- Keep network calls out of unit tests unless a test is explicitly intended as an integration test.
- Use pytest fixtures such as `tmp_path` for temporary files; do not assume system temp directories are writable.
- When modifying download, CRS, raster, processing, or functional land-use behavior, run the directly related tests when practical.
- Test externally visible behavior rather than internal implementation details where possible.
- A successful test run does not replace checking whether functional documentation must also change.

## Documentation Principles

Waterlagen documentation serves three distinct audiences:

1. users of datasets produced with Waterlagen;
2. users who want to produce those datasets themselves;
3. contributors developing Waterlagen.

Keep these concerns separated.

- User-facing documentation is written in Dutch.
- Code, identifiers, filenames, and API names retain their actual names.
- Documentation is built with MkDocs from `docs/`.
- Organize user documentation around concepts and workflows, not around the internal Python module structure.
- Keep functional documentation separate from Python API reference documentation.
- Avoid duplication. Define information in its canonical location and link to it elsewhere.
- When public behavior, processing methods, inputs, outputs, or workflows change, update the corresponding documentation in the same change.
- Do not document intended behavior that is not actually implemented unless it is explicitly identified as planned or conceptual.

## Documentation Structure

Use the following conceptual structure:

```text
docs/
├── index.md
├── over/
│   ├── index.md
│   └── ai-gebruik.md
├── bronnen/
│   ├── index.md
│   └── ...
├── bewerkingen/
│   ├── index.md
│   └── ...
├── produceren/
│   ├── index.md
│   └── ...
├── reference/
│   └── ...
└── bijdragen/
    ├── index.md
    ├── ontwikkelomgeving.md
    ├── conventions.md
    └── ai-agents.md
```

The visible MkDocs navigation may use Dutch labels even where technical directory names such as `reference` are English.

## Documentation: Sources

External datasets and services used by Waterlagen are documented under `docs/bronnen/`.

A source page is the canonical location for information about an external source.

Each source page should describe, where applicable:

- what the source contains;
- the organization responsible for publishing or maintaining it;
- the dataset, product, version, or service used by Waterlagen;
- relevant authoritative external URLs;
- relevant service or download endpoints;
- relevant spatial or temporal characteristics;
- important source-specific limitations;
- which Waterlagen processing workflows use the source.

Rules:

- Prefer authoritative publisher, dataset, API, or service URLs over third-party descriptions.
- Verify external URLs when adding or changing source documentation.
- External source URLs belong on source pages.
- Do not duplicate source URLs across processing pages unless there is a specific functional reason.
- Do not describe Waterlagen processing logic in detail on a source page.
- Link from source pages to relevant processing pages where useful.

New source pages should follow the established source-page template and heading structure.

## Documentation: Processing

Functional processing performed by Waterlagen is documented under `docs/bewerkingen/`.

A processing page explains what Waterlagen does with one or more sources and what the resulting dataset represents.

Each processing page should describe, where applicable:

- purpose;
- input sources;
- functional processing steps;
- relevant parameters or assumptions;
- resulting datasets, layers, rasters, or files;
- important output attributes or characteristics;
- limitations and interpretation considerations.

Rules:

- Refer to external input datasets by linking to their canonical page under `docs/bronnen/`.
- Do not repeat external source URLs from source pages.
- Describe processing functionally rather than as a walkthrough of Python implementation details.
- A reader should be able to understand how the resulting data was produced without reading the source code.
- Do not copy API documentation into processing pages.
- Link to instructions for producing the dataset when appropriate.
- Update the processing page when a code change materially changes how the resulting dataset is produced or interpreted.

New processing pages should follow the established processing-page template and heading structure.

## Documentation: Producing Datasets

Instructions for users who want to run Waterlagen themselves belong under `docs/produceren/`.

This documentation includes:

- installation;
- environment requirements;
- configuration;
- getting started;
- running production workflows;
- examples.

Rules:

- Keep installation and execution instructions separate from functional descriptions of sources and processing.
- Link to `docs/bronnen/` and `docs/bewerkingen/` instead of repeating their content.
- Examples should use current public APIs and realistic workflows.
- Prefer a clear path from installation to producing a first useful dataset.

## Documentation: API Reference

Technical Python API documentation is kept separate from functional documentation.

- Public functions and methods exposed as package API or in MkDocs reference pages use NumPy-style docstrings.
- Private helpers should have concise docstrings when their behavior is not immediately obvious.
- MkDocs reference pages use `mkdocstrings` with `docstring_style: numpy`.
- API reference pages describe Python interfaces, parameters, return values, exceptions, and technical behavior.
- Do not use API reference pages as the primary functional explanation of a dataset, source, or processing workflow.
- Link between functional documentation and API reference where that materially helps the reader.

## Documentation: Contributing

Contributor documentation belongs under `docs/bijdragen/`.

It should explain:

- how to set up the development environment;
- how to run tests, linting, formatting, and documentation locally;
- contribution workflow;
- shared development conventions;
- how AI coding agents are used in this repository.

`docs/bijdragen/conventions.md` is the canonical location for development conventions that apply equally to human and AI contributors.

`AGENTS.md` contains operational instructions specifically needed by AI coding agents.

Do not unnecessarily duplicate the same convention in both files. Where a convention is fully documented in `conventions.md`, reference it from `AGENTS.md` when that is sufficient for an agent to act correctly.

When using an AI coding tool that does not automatically discover `AGENTS.md`, contributors should explicitly provide or reference these repository instructions.

## Documentation: AI Transparency

Waterlagen is developed with assistance from AI coding agents.

The project must be transparent about this while accurately representing human responsibility for the software and resulting datasets.

- Maintain one canonical explanation of AI use under `docs/over/ai-gebruik.md`.
- Clearly state that AI coding agents are used to assist with development.
- Clearly state that code, methods, and produced datasets are reviewed and validated by humans.
- Do not imply that AI-generated code or datasets are accepted or published without human verification.
- Do not imply that human validation guarantees absence of defects.
- Keep the full explanation in the canonical AI-use page and link to it from appropriate prominent locations instead of duplicating the full statement throughout the documentation.
- A concise AI label may be shown on the homepage or another appropriate shared location.
- Contributor documentation may separately explain how contributors should work with AI coding agents; do not duplicate the project transparency statement there unnecessarily.

## Documentation Templates

- Use a consistent template for source pages.
- Use a consistent template for processing pages.
- Keep equivalent headings consistent across pages.
- Omit a template section only when it genuinely does not apply.
- Do not introduce page-specific sections merely to expose implementation details that belong in API reference documentation.
- Prefer links between canonical pages over copied explanations.
- When introducing a new type of documentation page, first determine whether it fits an existing documentation category and template.

## Documentation Changes

When code changes, explicitly consider whether documentation also needs to change.

In particular:

- a new external dataset or service normally requires a source page;
- a changed external dataset, endpoint, or version may require updating its source page;
- a new derived dataset or substantial processing workflow normally requires a processing page;
- a change to processing that affects interpretation or output requires updating its processing page;
- a new public workflow may require producing instructions or an example;
- a public API change requires corresponding docstrings and API reference updates;
- contributor workflow changes require contributor documentation updates.

Do not create documentation changes for purely internal refactors when externally visible behavior remains unchanged.

## Sources of Truth

Use canonical locations and avoid maintaining the same information in multiple places.

In particular:

- external data information and URLs → `docs/bronnen/`;
- functional transformation and processing → `docs/bewerkingen/`;
- installation and dataset production → `docs/produceren/`;
- Python interfaces → API reference and docstrings;
- shared contributor conventions → `docs/bijdragen/conventions.md`;
- AI-agent operational instructions → `AGENTS.md`;
- explanation of project-wide AI use → `docs/over/ai-gebruik.md`.

When information belongs elsewhere, link to the canonical location instead of copying it.

## Commands

Run project commands from the repository root using pixi.

- Targeted tests:
  `pixi run pytest <test-file-or-node>`
- Coverage:
  `pixi run test-cov`
- Format Python:
  `pixi run ruff format <file>`
- Lint Python:
  `pixi run ruff check <file>`
- Build documentation:
  `pixi run --environment docs docs-build`
- Serve documentation locally:
  `pixi run --environment docs docs-serve`

Before considering a change complete, run the relevant targeted tests and checks when practical. For documentation changes, build the documentation and resolve broken links, navigation errors, or MkDocs warnings introduced by the change.
