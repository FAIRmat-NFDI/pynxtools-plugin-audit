# pynxtools-xps: parser audit

Status: **draft, based on static reading of the source** (grep/sed excerpts, an AST-based scanner and a manual review). Nothing here was confirmed by running the parsers on real files unless a section says so.

This folder documents how each parser of `pynxtools-xps` turns vendor data into the `NXxps` data model: where the energy axis comes from, which formulas and unit conversions are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

## Contents

| File | Parser | Source folder |
|---|---|---|
| [scienta.md](scienta.md) | Scienta Omicron (HDF5, Igor, TXT) | `pynxtools_xps/parsers/scienta/` |
| [specs_sle.md](specs_sle.md) | SPECS `.sle` | `pynxtools_xps/parsers/specs/sle/` |
| [specs_xml.md](specs_xml.md) | SPECS XML | `pynxtools_xps/parsers/specs/xml/` |
| [specs_xy.md](specs_xy.md) | SPECS XY export | `pynxtools_xps/parsers/specs/xy/` |
| [phi.md](phi.md) | PHI Electronics | `pynxtools_xps/parsers/phi/` |
| [vms.md](vms.md) | VAMAS ISO (incl. CasaXPS comments) | `pynxtools_xps/parsers/vms/` |
| [kratos.md](kratos.md) | Kratos (comment metadata inside VAMAS) | `pynxtools_xps/parsers/kratos/` |

## Parsers at a glance

Source code: [pynxtools-xps on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-xps) (links point to the `main` branch). Documentation: [pynxtools-xps docs](https://fairmat-nfdi.github.io/pynxtools-xps/). The reader selects the parser by file extension. Each parser file has an "At a glance" section with the standard and special behaviour.

| Parser | Input format | Source code | Documentation | Metadata map |
|---|---|---|---|---|
| Scienta Omicron | `.txt`, `.ibw`, `.h5` / `.hdf5` | [scienta](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/scienta/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/scienta.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/scienta/metadata.py) |
| SPECS SLE | `.sle` | [specs/sle](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/specs/sle/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/specs.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/specs/sle/metadata.py) |
| SPECS XML | `.xml` | [specs/xml](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/specs/xml/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/specs.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/specs/xml/metadata.py) |
| SPECS XY | `.xy` | [specs/xy](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/specs/xy/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/specs.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/specs/xy/metadata.py) |
| PHI Electronics | `.spe`, `.pro` | [phi](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/phi/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/phi.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/phi/metadata.py) |
| VAMAS ISO | `.vms`, `.npl` | [vms](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/vms/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/vms.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/vms/metadata.py) |
| Kratos | `.vms` (VAMAS comments) | [kratos](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/kratos/) | [reference](https://fairmat-nfdi.github.io/pynxtools-xps/reference/kratos.html) | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/kratos/metadata.py) |

Note: the `.txt` extension is shared between the Scienta Omicron parser and the CasaXPS text-export parsers (`vms_export/parser_export.py`); see [scienta.md](scienta.md).

## Context

- Plugin: `pynxtools-xps` (public). Application definition: `NXxps`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** For each parser the energy-axis code and the metadata mapping were read with `grep -n` and `sed -n` excerpts. Each document has the same sections: *Formula / transformation*, *Special behaviour*, *Behaviour to investigate*, *Not verified*.
2. **Static scanner** (`audit_scan.py`). An AST scanner that flags patterns worth a second look: hard-coded units, magic numbers, silent fallbacks, axis flips, swallowed exceptions, stubs, duplicate dictionary keys. It also scans the JSON configs. Its output (`audit_xps.csv`) contains 722 findings: 2 high, 74 medium, 358 low, 288 info. **A finding is a pointer, not proof of a bug.** Each parser document has a "Scanner findings" section with the medium/high items and the rule counts for the rest.
3. **Conventions.** Line numbers (`l. N`) always come with their file name and refer to the source version that was inspected. They will drift with later commits. Numerical examples marked "my own numbers" are illustrations, not values from any real file.

## Summary of how the parsers build the energy axis

| Parser | Axis source | BE ↔ KE conversion | Work function used | Axis reversed | Output dims |
|---|---|---|---|---|---|
| Scienta | HDF5 `x_axis` dataset (or index fallback); Igor wave scaling `sfA·i + sfB`; TXT data columns | none; type is read from the file | no | none seen | HDF5: `(cycle, scan, [extra axes], energy)`; Igor/TXT: `(cycle, scan, energy)` with cycle = scan = 1 |
| SPECS SLE | `i · step_size` (relative), per-channel shifts and common grid in FAT mode | none for the axis; `KE = hν − BE` only for the transmission-function axis | no | `np.flip` of the axis for binding type (data not flipped) | `(cycle, scan, energy)`, `(cycle, scan, channel, energy)` |
| SPECS XML | computed: `BE_upper = hν − KE + KE_base + 1`, descending `linspace` | always builds binding energy | no | built descending | `(n_cycles, n_scans, N)`, `(n_cycles, n_scans, mcd_num, N)` |
| SPECS XY | first data column of the file, unchanged | none | no | none | `(cycle, scan, <first column name>)` |
| PHI | `start`, `stop`, `step` parsed from the region definition | none; `"binding"` is hard-coded | no | `np.flip` of the axis only | `(1, n_scans, n_energy)` |
| VAMAS | `start + i·step` (regular) or interleaved abscissa (irregular) | optional `convert_to_binding_energy_scale` (no caller seen); CasaXPS shift for `ADD` | no | `np.flip` of the axis for label `"binding energy"` | `(1, n_scans, n_energy)`, raw `(1, n_scans, 1, n_energy)` |
| Kratos | none; metadata only (via VAMAS comments) | none | no | none | none |

## Cross-cutting observations

These points appear in more than one parser. Each is a candidate for a single check or fix.

1. **No parser converts between kinetic and binding energy in the main data path, and none applies the work function.** `hν − KE` appears only in the SPECS XML axis, in the SLE transmission-function axis, and in the unused VAMAS conversion method. None of them subtracts φ. Binding/kinetic is mostly read from the file or hard-coded.
2. **Axis reversed without reversing the data.** SLE (`parser.py` l. 446-447), PHI (`parser.py` l. 320) and VAMAS (`parser.py` l. 436-437, 468-469) reverse the energy axis. In none of them is the intensity array reversed in the code that was inspected. Whether this is correct depends on how each file orders its data. Check with a known peak (for example Au 4f7/2 at 84.0 eV). The scanner also flags the flips in `numerics.py` l. 152 (`interpolate_arrays`) and `models/backgrounds.py` l. 233-234, 262 (Shirley).
3. **Binding energy hard-coded or assumed.** PHI (`parser.py` l. 317) and SPECS XML always produce binding energy. A kinetic-energy file would be labelled as binding.
4. **Hard-coded units.** `energy/@units = "eV"` and `intensity/@units = "counts_per_second"` are written directly in SLE (`parser.py` l. 315-316) and Scienta TXT (`txt_parser.py` l. 220-221); PHI hard-codes `"eV"` and `"s"` (`parser.py` l. 315, 318).
5. **Silent data loss and silent fallbacks.** Examples: unparseable TXT lines skipped (`txt_parser.py` l. 195-196), SLE shifts skipped on `KeyError` (`parser.py` l. 334-335), Kratos lines that do not split cleanly (`parser.py` l. 97-98). Every `matches_file` method (Scienta, SLE, XML, XY, PHI, VAMAS, VAMAS export) swallows `Exception`, so a broken file is reported as "not this format".
6. **Step-size helper rounds to 2 decimals.** `numerics.py` l. 105 (`_get_minimal_step`) uses `round(..., 2)`. Assuming the XY and VAMAS parsers import this function, it feeds `step_size` in the XY parser and `abscissa_step` for irregular VAMAS data. A true step below 0.005 eV would become 0. VAMAS also rounds the regular axis to 2 decimals (`parser.py` l. 434) and `y_cps` to 2 decimals (`parser.py` l. 672).
7. **Sum instead of mean.** SLE and XML sum the channels (`np.sum`, `counts_sum`). The result is in counts, not an average per channel. Check the NeXus `data` description and units.
8. **Axis and metadata taken from the first scan only.** SLE, XY and VAMAS use the first scan's axis (and, for XY and VAMAS, its metadata) for the whole set. Later scans are only length-checked (SLE) or not compared at all.
9. **Energy-type fields that can disagree.** Scienta stores the type in several places (`energy_scale`, `energy_scale_2`, `energy_mode`, Igor dimension name, a default in `data_model.py` l. 47). VAMAS and SPECS XY derive it from a label.
10. **Dormant or stub code.** Kratos `_parse` is empty; VAMAS `_add_mapping_data` (`parser.py` l. 492) and `CasaProcess.process_smoothing` (`data_model_casa.py` l. 367) have empty bodies; VAMAS `apply_energy_shift` can return `None`.
11. **Time zones.** UTC is assumed in `mapping.py` l. 114, 160 and in SPECS XY `metadata.py` l. 55, 63. VAMAS uses `0001-01-01` as a fallback date (`parser.py` l. 639).
12. **Unit strings with trailing spaces.** `"counts_per_second "` and `"degree "` in SLE `metadata.py` l. 135-136, and `"degree "` in VAMAS `metadata.py` l. 122. VAMAS maps `particle_charge` and `sputter_ion_charge` to `"C"` (`metadata.py` l. 98, 104), which is ambiguous (coulomb or Celsius).
13. **Duplicate dict keys.** The only two high-severity scanner findings: `time_per_spectrum_channel` (Scienta `metadata.py` l. 188 and 194) and `DeviceExcitationEnergy` (SLE `metadata.py` l. 87 and 94). The later entry silently wins.
14. **Config.** `config/template.json` does not parse as JSON (scanner, l. 290). The `U01` hits in `config_vms.json` and `config_specs_sle.json` are fallback chains such as `['@attrs:energy_units', 'eV']`, so they are scanner false positives for unit strings rather than invalid units.

## Out of scope in this folder

The scanner also covers code that has no document here: `parsers/vms_export/` (VAMAS export text parsers and result parser), `parsers/specs/slh/`, `models/` (backgrounds, lineshapes), `peak_finding.py`, `reader.py` and `parsers/base.py`. Their findings are in `audit_xps.csv`.
