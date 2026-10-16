# pynxtools-microstructure: parser audit

Status: **draft, based on static reading of the source** (manual review of the two parsers, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-microstructure`. Nothing here was confirmed by running the parsers on real files unless a section says so. One suspected defect (`bool()` of an `h5py` dataset) could not be tested because `h5py` was not available in the review environment.

This folder documents how the parsers of `pynxtools-microstructure` turn MTex output and Oasis deployment metadata into `NXem` / `NXmicrostructure` instances: how files are recognised, which parts of the HDF5 tree are copied and how, which context is added from YAML, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

The two parsers complement each other and are called by the reader in a fixed order (`reader.py` l. 61–77): the MTex HDF5 file supplies the data and the NXem-shaped structure, the Oasis config file supplies the context MTex output lacks (citation, project, users, start time, canonical file path).

1. **MTex parser** (`nxs_mtex.py`): copies a pre-organised HDF5 file (`/entry1/roi1/ebsd/indexing/…`, `/entry1/profiling`) into the template. The expensive MTex processing (about 2.4k datasets, about 120 h; mtex l. 27–34) is thereby decoupled from metadata completion.
2. **Oasis config parser** (`oasis_config.py`): maps a `*.oasis.specific.yaml` file to citation, project, description, users and start time, and sets a file-path alias to the MTex file.

## Contents

| File | Format | Parser |
|---|---|---|
| [nxs_mtex.md](nxs_mtex.md) | MTex HDF5 `*.mtex.h5` / `*.mtex.hdf5` | `nxs_mtex.py` |
| [oasis_config.md](oasis_config.md) | NOMAD Oasis deployment config `*.oasis.specific.yaml` | `oasis_config.py` |

## Parsers at a glance

Source code: [pynxtools-microstructure on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-microstructure) (links point to the `main` branch; the inspected version is the one of 15th October 2026, the cloned `main` head being `4b06a27` of 15th June 2026). The reader class is `MICROSTRUCTUREReader` with `supported_nxdls = ["NXem"]` (`src/pynxtools_microstructure/reader.py` l. 42), registered as the `microstructure` entry point. It selects files by the suffixes `.mtex.h5` and `.oasis.specific.yaml`. Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| MTex `*.mtex.h5` | EBSD-derived microstructure (points, polylines, crystals, interfaces, triple junctions, IPF and ODF) / `NXem`, `NXmicrostructure*` | `h5py` (reopened per method), `mmap` | [nxs_mtex.py](https://github.com/FAIRmat-NFDI/pynxtools-microstructure/blob/main/src/pynxtools_microstructure/parsers/nxs_mtex.py) |
| `*.oasis.specific.yaml` | deployment and dataset context / `NXem` | `yaml.safe_load` → `flatdict.FlatDict` | [oasis_config.py](https://github.com/FAIRmat-NFDI/pynxtools-microstructure/blob/main/src/pynxtools_microstructure/parsers/oasis_config.py) |

Other folders of the plugin: `mtex/` and `matlab/` (the MTex scripts that create the input), `configurations/` (mapping tables), `nomad/`, `examples/`, `utils/`. They were not reviewed. Helpers are imported from `pynxtools_em` (default config, checksum, mapping functors).

## Context

- Plugin: `pynxtools-microstructure` (public). Application definition: `NXem` with `NXmicrostructure` base classes.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** `nxs_mtex.py` (815 lines) and `oasis_config.py` (165 lines) were read in full from the `main` branch of 15th October 2026. Both documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin.
3. **Conventions.** Line numbers (`mtex l.`, `oasis l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited and external code.** Not read: `MICROSTRUCTUREReader`, `prioritized_axes_heuristic`, the `pynxtools_em` helpers, the mapping tables `OASISCFG_MICROSTRUCTURE_CITATION_TO_NEXUS` and `…_PROJECT_TO_NEXUS`, the MTex scripts, and the default configuration.

## Summary of how the parsers write the template

| Parser | Unit of work | Writing rule | Where |
|---|---|---|---|
| `nxs_mtex.py` | six copy routines: profiling, MTex config, scalars, ROI default plot, phases, microstructure | scalar `dset[()]` (bytes decoded UTF-8); `(1,)` promoted with a warning; arrays as `{"compress", "chunks", "strength"}` with `prioritized_axes_heuristic`; attributes as `…/@name` | mtex l. 53–119 |
| `oasis_config.py` | `parse_example()` | first non-empty citation dict only; project block via mapping table; description `title, \nauthor, \ndoi`; users with a `name`; `start_time` unconditionally; file-path alias | oasis l. 69–148 |

## Cross-cutting observations

1. **Suspected defects in `nxs_mtex.py`.**
   - Triple-junction indices are never copied: `hfive_dataset_to_template` is called with `h5r` in the `trg_dst_name` slot and the string in `obj` (mtex l. 625–633, 645–652).
   - `bool(h5r[...])` of an `h5py` dataset is always true by `h5py` truthiness, so the four flags (`inside_poly`, `methods_advise`, `mosek`, `stop_on_symmetry_mismatch`) are stored as `True` (mtex l. 296; not run, needs a check with real files).
   - `re.match("phase[0-9]+", name)` is not anchored (mtex l. 411).
2. **`supported` is unset for wrong file names** in both parsers (mtex l. 135, oasis l. 51–54), so `parse()` raises `AttributeError` instead of a clear message.
3. **Narrow exception handling.** An empty file makes `mmap.mmap(fileno, 0)` raise `ValueError`, which the `OSError` handler does not catch (mtex l. 145, 149). In the config parser `yaml.YAMLError` and an empty YAML (`safe_load` returns `None`) are not caught, and any `OSError` is reported as "not found" (oasis l. 59–60).
4. **Hard-coded names.** The MTex parser expects `/entry1`, `roi1`, `microstructure1`, `program1…3` (mtex l. 156–160, 198, 226, 469); `entry_id` changes only the target. `depends_on` for `polylines` is forced to `…/microstructure1/points`, which a comment calls an MTex script bug (mtex l. 522–526).
5. **The same description recipe as in other plugins.** The `title, \nauthor, \ndoi` text with a trailing-comma strip, the single-citation `break` and the dead `cite_id` counter are shared with `pynxtools-apm` and `pynxtools-em` (see `oasis_config.py` there); a fix should be applied to all three. A list-valued `author` is written as its Python repr.
6. **Provenance is not recorded.** The SHA-256 of each file is logged and kept on the object but not written to the template (mtex l. 170–173, oasis l. 73–76).
7. **Unconditional `start_time`.** The config's `start_time` is copied without a check whether another source already set it, and without ISO 8601 or time-zone validation (oasis l. 144–148).
8. **Naming and path hazards.** Docstrings mention `*.nxs.mtex` while the code uses `.mtex.h5` (mtex l. 124, 129, 167); `AXISNAME_indices[@axis_x_indices]` has a second `@` inside the brackets (mtex l. 367); `entry_id` is used in absolute `depends_on` strings, which must agree with `ENTRY[entry<id>]` keys (mtex l. 523, 655).
9. **Copy and I/O overhead.** Both arms of the compression `if` are identical (mtex l. 75–93); the file is reopened six times (mtex l. 197–468).
10. **Coupling to `pynxtools_em`.** Default config, checksum and `add_specific_metadata_pint` come from the `pynxtools_em` package, so version skew between the two plugins can break this one.

## Out of scope in this folder

Not documented here: the reader, `configurations/` mapping tables, the MTex and Matlab scripts, `nomad/` and `examples/`, `utils/`, and the `NXem` / `NXmicrostructure` definitions. Findings that depend on them are marked as inferred in the individual documents.
