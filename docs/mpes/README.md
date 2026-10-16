# pynxtools-mpes: parser audit

Status: **draft, based on static reading of the source** (manual review of the reader, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-mpes`. Nothing here was confirmed by running the reader on real files unless a section says so.

This folder documents how `pynxtools-mpes` turns a binned multidimensional photoelectron spectroscopy (MPES) HDF5 file into the `NXmpes` and `NXmpes_arpes` data models: which HDF5 layout is required, how signal, axes, units and metadata are put into one `xarray.DataArray`, how the JSON config and the ELN reach the NeXus template, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

Like `pynxtools-igor`, `pynxtools-mpes` has **no separate parser class and no per-vendor parser**: the plugin is one `MultiFormatReader` subclass in `reader.py`. Upstream processing (outside this repository) is expected to bin the events and write the normalised HDF5 file; the reader is an adapter from that structure to NeXus. The document is therefore a reader walkthrough.

1. **Collection.** The extension handlers store the HDF5 file as an `xarray.DataArray`, load the ELN YAML and register the JSON config.
2. **Lookup.** The inherited `MultiFormatReader` walks the JSON config and calls `get_data()`, `get_data_dims()`, `get_attr()` and `get_eln_data()`.

## Contents

| File | Format | Component |
|---|---|---|
| [mpes-reader.md](mpes-reader.md) | normalised MPES HDF5 (`.h5`, `.hdf5`); optional ELN YAML and JSON config | `reader.py` (`MPESReader` and helpers) |

## Parsers at a glance

Source code: [pynxtools-mpes on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-mpes/tree/develop) (links point to the `develop` branch; the cloned head is `118ce65` of 13th October 2026). Documentation: [pynxtools-mpes docs](https://fairmat-nfdi.github.io/pynxtools-mpes/). The reader is `MPESReader(MultiFormatReader)` with `supported_nxdls = ["NXmpes", "NXmpes_arpes"]` (`src/pynxtools_mpes/reader.py` l. 163–167), registered as the `mpes` entry point. The extension map is `.yml`/`.yaml` → ELN, `.json` → config, `.h5`/`.hdf5` → data (`reader l.` 173–179).

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| MPES HDF5 `.h5`, `.hdf5` | binned photoemission data (energy, momentum, delay …) / `NXmpes`, `NXmpes_arpes` | `h5py` → `h5_to_xarray()` | [reader.py](https://github.com/FAIRmat-NFDI/pynxtools-mpes/blob/develop/src/pynxtools_mpes/reader.py) |
| ELN `.yml` / `.yaml` | extra metadata | `parse_yml(..., parent_key="/ENTRY")` (pynxtools) | same file |
| JSON config `.json` | field-by-field mapping | interpreted by `MultiFormatReader` | same file |

The package also contains NOMAD integrations (`nomad/apps`, `nomad/example_uploads`, `nomad/north_tools`) that were not reviewed. Unlike the parser-based plugins, no SPE, SES or EMD parsers live here; binning is expected upstream.

## Context

- Plugin: `pynxtools-mpes` (public). Application definitions: `NXmpes`, `NXmpes_arpes`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** `reader.py` (about 250 lines) was read in full from the `develop` branch. The document in this folder follows the *Source files reviewed*, *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings* layout.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin.
3. **Conventions.** Line numbers (`reader l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited code.** Not read: `MultiFormatReader` (it owns the JSON-config walk and template population), `parse_yml`, the default JSON configs, and the NOMAD integration code.

## Summary of how the reader builds the data array

| Item | Source | Rule | Where |
|---|---|---|---|
| Signal | `/binned/BinnedData` | read as the array values | `h5_to_xarray()`, `reader l.` 62–131 |
| Coordinates and dims | `/axes/ax0`, `/axes/ax1`, … and their `name` attribute | one coordinate per axis, named by `attrs["name"]` | `reader l.` 62–131 |
| Axis units | `/axes/ax{N}` attribute `unit` | falls back to `""` on `KeyError`/`TypeError` | `reader l.` 112–118 |
| Data units, long name | `BinnedData` attributes `units`, `long_name` | fall back to `""` | `reader l.` 120–131 |
| Metadata | `/metadata` | nested dict via `recursive_parse_metadata()`; keys containing `VSet` renamed by dropping the last three characters | `reader l.` 33–60, 95–109 |
| ELN | YAML | loaded with `parent_key="/ENTRY"` | `handle_eln_file()`, `reader l.` 193–200 |

## Cross-cutting observations

1. **The HDF5 layout is fixed.** The reader fails unless `/binned/BinnedData` and `/axes` exist; there is no alternative dataset naming or layout, and only one `xarray` is kept, so several data files cannot be merged.
2. **Missing `/metadata` raises.** `metadata` is `None` when the group is absent, but the next statement is `"file" in metadata.keys()` (`reader l.` 99), which raises `AttributeError` for `None`. The earlier walkthrough read this as a working guard; it is not, so check it with a file without `/metadata`.
3. **Axis units are read by position.** Units come from `ax{axis}` (`reader l.` 112–118) while the coordinates iterate every entry in `/axes`; a non-standard axis name loses its unit silently (empty string).
4. **The `VSet` rename is broad.** Any key in `metadata["file"]` containing `VSet` is renamed by cutting its last three characters (`reader l.` 101–109), not only lens-voltage keys, and an existing target key is overwritten.
5. **Silent lookup failures.** `get_data()` and `get_attr()` may return `None` after a warning; whether the NeXus field is then omitted, empty or invalid depends on the converter and the config.
6. **ELN lookup convention.** `get_eln_data()` takes both `key` and `path` but uses `path`, so config authors must know which one `MultiFormatReader` passes for `@eln` entries (`reader l.` 201–207).
7. **No validation in the reader.** Type, shape and unit of the extracted values are not compared with the NeXus definition.
8. **Binned data only.** Raw event lists cannot be read; they must be binned upstream, and the binning parameters reach NeXus only through the metadata.
9. **The JSON config is essential.** Without a suitable config the staged xarray and ELN data are not placed in the template.

## Out of scope in this folder

Not documented here: `MultiFormatReader` and the JSON-config mechanism, `parse_yml`, the default JSON configs shipped with the plugin, the NOMAD apps, example uploads and NORTH tool, the upstream binning code that writes the HDF5 file, and the `NXmpes` / `NXmpes_arpes` application definitions. Findings that depend on them are marked as inferred in the document.
