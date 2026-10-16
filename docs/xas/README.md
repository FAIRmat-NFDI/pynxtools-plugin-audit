# pynxtools-xas: parser audit

Status: **draft, based on static reading of the source** (manual review of the five parsers, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-xas`. Nothing here was confirmed by running the parsers on real files unless a section says so.

This folder documents how each parser of `pynxtools-xas` turns X-ray absorption spectra into the `NXxas` family of data models: how a file is recognised, which library reads it, where energy, intensity, element and edge come from, which unit conversions and heuristics are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

All five parsers derive from `_XASParser` (`pynxtools_xas/parsers/base.py`, **not supplied**) and produce the same output: `self._data[<sanitised entry name>] = ParsedSpectrum(energy, intensity, metadata)`. A JSON config (`config_xas_fluo.json`, `config_xas_trans.json`, `config_specs_xy.json`, **not supplied**) then maps the metadata keys to the template. The parsers differ in how much they have to infer:

1. **Fixed layout, translated by a key map:** `esrf_trans.py` and `oscars_xdi.py` (flatten the group, pop energy and intensity, map keys).
2. **Fixed layout, raw paths left to the config:** `myspot_trans.py` (no element, edge or sample information in the file).
3. **Inference from names:** `esrf_fluo.py` (two layouts, element and edge from channel names, shared between entries).
4. **Delegation:** `specs_xy.py` (the file is read by the `pynxtools-xps` SPECS XY parser and adapted).

## Contents

| File | Format | Parser |
|---|---|---|
| [esrf_fluo.md](esrf_fluo.md) | ESRF Bliss/SPEC HDF5, fluorescence-yield XAS (ID21, µXANES) | `esrf_fluo.py` |
| [esrf_trans.md](esrf_trans.md) | ESRF BM beamline HDF5, transmission EXAFS | `esrf_trans.py` |
| [myspot_trans.md](myspot_trans.md) | BESSY II mySpot Bliss-numbered HDF5 | `myspot_trans.py` |
| [oscars_xdi.md](oscars_xdi.md) | HDF5 derived from XDI files (OSCARS-prepared) | `oscars_xdi.py` |
| [specs_xy.md](specs_xy.md) | SPECS SpecsLab Prodigy `.xy` (electron-yield NEXAFS) | `specs_xy.py` |

## Parsers at a glance

Source code: [pynxtools-xas on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-xas) (links point to the `develop` branch; the inspected version is the one of 15th October 2026, the cloned branch head being `d7dcad5` of 13th October 2026; `specs_xy.md` states the `main` branch). The reader class is `XASReader`, registered as the `xas` entry point, with `supported_nxdls` `NXxas`, `NXxas_tey`, `NXxas_trans`, `NXxas_herfd`, `NXxas_pey`, `NXxas_pfy` and `NXxas_tfy` (`src/pynxtools_xas/reader.py` l. 52–60). Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| ESRF fluorescence `.h5` / `.hdf5` | fluorescence-yield XAS / `NXxas` | `h5py` | [esrf_fluo.py](https://github.com/FAIRmat-NFDI/pynxtools-xas/blob/develop/src/pynxtools_xas/parsers/esrf_fluo.py) |
| ESRF BM transmission `.h5` / `.hdf5` | transmission EXAFS / `NXxas_trans` | `h5py` + `flatten_hdf5_group` | [esrf_trans.py](https://github.com/FAIRmat-NFDI/pynxtools-xas/blob/develop/src/pynxtools_xas/parsers/esrf_trans.py) |
| mySpot (BESSY II) `.h5` / `.hdf5` | transmission XAS / `NXxas_trans` (shared config) | `h5py` + `flatten_hdf5_group` | [myspot_trans.py](https://github.com/FAIRmat-NFDI/pynxtools-xas/blob/develop/src/pynxtools_xas/parsers/myspot_trans.py) |
| OSCARS / XDI-derived `.h5` / `.hdf5` | transmission XAS / `NXxas_trans` | `h5py` + `flatten_hdf5_group` | [oscars_xdi.py](https://github.com/FAIRmat-NFDI/pynxtools-xas/blob/develop/src/pynxtools_xas/parsers/oscars_xdi.py) |
| SPECS Prodigy `.xy` | electron-yield NEXAFS / `NXxas` | `pynxtools_xps` `SPECSXYParser` | [specs_xy.py](https://github.com/FAIRmat-NFDI/pynxtools-xas/blob/develop/src/pynxtools_xas/parsers/specs_xy.py) |

Shared helpers (`base.py`, `hdf5_utils.py`, `datetime_utils.py`, `versioning.py`) live in the same folder and were not reviewed in full.

## Context

- Plugin: `pynxtools-xas` (public). Application definitions: the `NXxas` family (see above).
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** Each parser was read in full. The five documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin, so every "Scanner findings" section says so.
3. **Conventions.** Line numbers (`fluo l.`, `trans l.`, `myspot l.`, `xdi l.`, `xy l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited code.** Not read: `_XASParser` (including `map_metadata_fields` and `_data`), `ParsedSpectrum`, `VendorType`, `parse_datetime`, `flatten_hdf5_group`, `sanitize_entry_name`, the three JSON configs, and the `pynxtools_xps` SPECS XY parser. Their roles are inferred from usage.

## Summary of how the parsers obtain energy, intensity and identity

| Format | Marker / detection | Energy | Intensity | Element and edge |
|---|---|---|---|---|
| ESRF fluorescence | a top-level `NXentry` that yields a scan (fluo l. 195–205) | *plotselect* axis or `avg_energy`; keV → eV if `max|E| < 100` (fluo l. 79) | plotselect signal or channel matching `avg_<element>_<line>` / `…_corr_norm` | inferred from channel names, then taken from the first sibling entry that has one (fluo l. 268–283) |
| ESRF transmission | `instrument/ExafsElement` in a top-level group (trans l. 50–58) | `instrument/Emono/value`, ×1000 (keV → eV) unconditionally | `instrument/mu_trans/data` | from `ExafsElement` and the key map |
| mySpot | `NXentry` with 1D `measurement/dcm_p_energy` longer than one point (myspot l. 34–41) | `measurement/dcm_p_energy`, keV → eV by assumption | `measurement/normalised_roi_5` | none in the file; from ELN via the config |
| OSCARS XDI | `computed_mu` in a top-level group (xdi l. 59, 68) | `energy`, no conversion | `computed_mu` | mapped; missing edge energies back-filled from sibling entries (xdi l. 97–101) |
| SPECS `.xy` | forwarded to the XPS parser (xy l. 93–94) | energy dimension of the XPS spectrum | repeated scans averaged with errors | from the region name by regex (xy l. 28, 47) |

## Summary of time-stamp and unit handling

| Format | Time zone | Unit conversion | Notes |
|---|---|---|---|
| ESRF fluorescence | via `parse_datetime` | keV → eV by magnitude heuristic | bytes/str handling repeated per field (fluo l. 224–247) |
| ESRF transmission | via `parse_datetime`, only for `str` | unconditional ×1000 | `units` attribute documented but never checked |
| mySpot | `Europe/Berlin` for offset-less strings (myspot l. 27–28, 76–78) | keV → eV assumed | `bytes` timestamps not converted |
| OSCARS XDI | `America/Chicago` (APS) assumed (xdi l. 26) | none | only `str` values parsed |
| SPECS `.xy` | `parse_datetime` without `tzinfo` (xy l. 67) | none | energy axis meaning not checked |

## Cross-cutting observations

These points appear in more than one parser. Each is a candidate for a single check or fix.

1. **Unit conversion is by assumption.** ESRF transmission and mySpot multiply keV by 1000 without reading a unit attribute (trans l. 69; myspot l. 64–66), ESRF fluorescence uses a magnitude heuristic that misreads soft X-ray scans below 100 eV (fluo l. 79), OSCARS leaves the unit unstated (xdi l. 71), and SPECS never checks whether the axis is photon, kinetic or binding energy (xy l. 77).
2. **Edge naming is inconsistent.** `esrf_fluo.py` emits `"L"` or `"M"` (fluo l. 62), `specs_xy.py` maps `L` to `"L2,3"` and `M` to `"M4,5"` (xy l. 35, 47) and passes other strings such as `L3` through unchanged. The NXDL edge enumeration should be checked against what each parser emits.
3. **Fixed time zones.** `Europe/Berlin` (mySpot), `America/Chicago` (OSCARS) and an undefined default (SPECS) are applied to naive timestamps; non-string (`bytes`, NumPy) timestamps stay unparsed in several parsers.
4. **Fixed keys fail hard.** ESRF transmission pops `instrument/Emono/value` and `instrument/mu_trans/data` after matching only on `ExafsElement` (trans l. 72–73); mySpot hard-codes `normalised_roi_5` (myspot l. 67); OSCARS pops `energy` without default (xdi l. 71). A different export raises `KeyError` and aborts the whole file instead of skipping the scan.
5. **Matching versus parsing disagree.** `matches_file` checks one condition and `_parse` assumes more; mySpot's matcher raises `AttributeError` when the energy node is a group and is caught as "not this format" (myspot l. 39), and ESRF transmission catches `Exception` broadly in `matches_file` (trans l. 57).
6. **`NX_class` comparison with `"NXentry"`** fails if `h5py` returns `bytes` (fluo l. 200, 212; myspot l. 37). Verify with real files.
7. **Name collisions after sanitising.** `sanitize_entry_name` may map different scan names (for example `1.1` and `1_1`) to the same key; later entries overwrite earlier ones in fluo l. 250, trans l. 80, myspot l. 80, xdi l. 73 and xy l. 99–102.
8. **Memory and double reads.** The transmission-family parsers flatten every array of every scan though two are used (trans l. 68; myspot, xdi likewise); `esrf_fluo.py` reads each file twice, once to match and once to parse.
9. **Sibling propagation.** Element, edge and edge energy are copied between entries on a "first one wins" basis (fluo l. 268–283, xdi l. 97–101), which mixes scans of different elements in one file.
10. **The SPECS parser is not XAS-specific.** `matches_file` is true for every SPECS `.xy`, including XPS files, so dispatch relies on vendor, extension and an explicit technique setting outside this file (xy l. 93–94). It also depends on private `pynxtools_xps` data structures (`data.sizes`, `average()`, `errors()`), so changes there break the adapter (xy l. 20).
11. **Edge cases of the spectrum data.** `axes == "."` (a NXdata placeholder) is not handled in fluo l. 112; `next(...)` raises `StopIteration` if all SPECS dimensions are `cycle` or `scan` (xy l. 52); `region` names such as `Mn-L3,2` or `O_K` give no element or edge (xy l. 28).
12. **Naming.** The file `oscars_xdi.py`, class `OscarsXdiParser` and vendor `"oscars"` differ from the docstring wording "OSCARS-prepared XDI-derived"; the intended spelling and source should be confirmed in the project docs.

## Out of scope in this folder

Not documented here: `parsers/base.py` (`_XASParser`), `hdf5_utils.py`, `datetime_utils.py`, `versioning.py`, the JSON configs, the reader entry point and ELN models, the `pynxtools-xps` SPECS XY parser, and the `NXxas` application definitions. Findings that depend on them are marked as inferred in the individual documents.
