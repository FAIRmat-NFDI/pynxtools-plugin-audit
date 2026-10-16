# pynxtools-igor: parser audit

Status: **draft, based on static reading of the source** (manual review of the reader, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-igor`. Nothing here was confirmed by running the reader on real files unless a section says so.

This folder documents how `pynxtools-igor` turns Igor Pro data into NeXus: how `.ibw` and `.pxp` files are collected and read, how axes, units and wave notes are derived, how entries are built, and how the data are handed to the JSON config. It is one part of the wider pynxtools plugin audit (see "Context" below).

Unlike `pynxtools-xps` and `pynxtools-spm`, `pynxtools-igor` has **no separate parser class and no per-format parser**: the whole plugin is one `MultiFormatReader` subclass in `reader.py`. Parsing happens in `process_ibw_files()` and `process_pxp_files()`, and the JSON config decides which values reach the template. The document is therefore a reader walkthrough, modelled on the `mpes-reader.md` layout, not on the parser walkthroughs.

1. **Collection.** The extension handlers only append `.ibw`/`.pxp` paths to lists.
2. **Loading** (`post_process()`): all `.ibw` files, or exactly one `.pxp` file, are read with `igor2`; every wave becomes an *entry*.
3. **Lookup.** The inherited `MultiFormatReader` walks the JSON config and calls `get_data()`, `get_attr()`, `get_data_dims()` and `get_eln_data()`.

## Contents

| File | Format | Component |
|---|---|---|
| [igor-reader.md](igor-reader.md) | Igor binary wave `.ibw`, Igor packed experiment `.pxp`; optional ELN YAML, JSON config, `.entry` description | `reader.py` (`IgorReader` and helpers) |

## Parsers at a glance

Source code: [pynxtools-igor on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-igor/tree/develop) (links point to the `develop` branch; the inspected version is the one of 15th October 2026). The reader is `IgorReader(MultiFormatReader)`, with `supported_nxdls = ["*"]`, so it can fill any application definition for which a config exists (`reader l.` 108–111, 343). The document has an "At a glance" section.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| Igor `.ibw` | one wave per file, any technique / any NXDL | `igor2.binarywave` | [reader.py](https://github.com/FAIRmat-NFDI/pynxtools-igor/blob/develop/src/pynxtools_igor/reader.py) |
| Igor `.pxp` | many waves in a folder tree, several entries per conversion / any NXDL | `igor2.packed` | same file |
| ELN `.yml` / `.yaml` | extra metadata | `parse_yml` (pynxtools) | same file |
| `.entry` | entry descriptions | `parse_entry_dict()` | same file |

The path `src/pynxtools_igor/reader.py` is the path named in the document. The reader is the only reader in this audit that supports several entries in one conversion. General background for the base class: [Use the MultiFormatReader](https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html).

## Context

- Plugin: `pynxtools-igor` (public). Application definitions: any (`["*"]`); the plugin targets FHI-specific Igor data.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** `reader.py` (344 lines) was read in full from the `develop` branch of 15th October 2026. The document follows the `mpes-reader.md` layout: *Source files reviewed*, *At a glance*, *Formula / transformation*, then standard and special behaviour and *Behaviour to investigate*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin.
3. **Conventions.** Line numbers (`reader l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited code.** Not read: `MultiFormatReader` (it owns the JSON-config walk, `callbacks.entry_name` and the order in which `handle_*`, `post_process()` and `get_*` run), `parse_yml`, the `igor2` library, and the default JSON configs.

## Summary of how the reader builds data, axes and units

| Item | Source | Formula or rule | Where |
|---|---|---|---|
| Axis values | wave header `sfA`, `sfB`, `nDim` | x_i = sfA[d]·i + sfB[d], i = 0 … nDim[d]−1 | `axis_from()`, `reader l.` 56–71 |
| Axis units | wave header, axis wave (`.pxp`), or config key `axisN_units` | `axisN_units` overrides both header and axis-wave units | `reader l.` 239–242, 305–308 |
| Data units | wave header, or config key `data_units` | `data_units` overrides the header | `reader l.` 249–252 |
| Metadata | wave note | `key=value` pairs, split on whitespace | `parse_note()`, `reader l.` 36–50 |
| Entry name | file stem (`.ibw`), wave path (`.pxp`), or `.entry` file | `Path(file).name.split(".")[0]` for `.ibw` | `reader l.` 221 |

## Cross-cutting observations

1. **Wave notes are parsed on whitespace, not lines.** The docstring says newline-separated; `Sample=Au 111` is lost and values containing `=` are dropped (`reader l.` 36–49).
2. **Encodings are assumed.** Notes are decoded as UTF-8 (`reader l.` 45) and units likewise (`reader l.` 89), although Igor can write Mac Roman or Latin-1; `µ` and `°` can raise `UnicodeDecodeError`.
3. **Entry naming collides.** The stem is cut at the first dot (`my.sample.ibw` → `my`) and two files with the same stem overwrite one entry (`reader l.` 221). A later `.entry` of the same name replaces an earlier one without a warning (`reader l.` 172).
4. **Entries without data are listed but never loaded** (`reader l.` 214–218), so config lookups for them return `None`.
5. **`set_config_file()` announces a skip but overwrites** (`reader l.` 144–146).
6. **No shape checks.** An axis wave for `.pxp` is not compared with the data shape (`reader l.` 290–292), nor an error wave with the data.
7. **Silent no-ops.** With no `.ibw`/`.pxp` input `post_process()` returns without a message (`reader l.` 189–208).
8. **Order dependence on the base class.** `get_entry_names()` returns `dict_keys` or `list` depending on the branch, and is only populated after `post_process()` (`reader l.` 181–184).
9. **Truthiness of igor2 records.** `if not data_wave` / `if not axis_wave` relies on the truthiness of the record object (`reader l.` 266, 286).
10. **Memory.** All arrays of all entries are kept in `self.data` at once.

## Out of scope in this folder

Not documented here: `MultiFormatReader` and the JSON-config mechanism, `parse_yml`, the `igor2` package, the default JSON configs shipped with the plugin, and the NeXus application definitions the configs target. Findings that depend on them are marked as inferred in the document.
