# pynxtools-raman: parser audit

Status: **draft, based on static reading of the source** (manual review of the two parsers, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-raman`. Nothing here was confirmed by running the parsers on real files unless a section says so.

This folder documents how each parser of `pynxtools-raman` turns Raman data into the `NXraman` application definition: which file is accepted, which library reads it, where the x-axis comes from, which formulas and unit conversions are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

Both parsers derive from the same base class `_RamanParser` (`pynxtools_raman/parsers/base.py`, **not supplied**). A parser fills `self.data` (arrays), `self.attrs` and `self.unused_attrs` (flat key/value dictionaries) and may implement `post_process()`. A JSON config named in the parser (`config_file_*.json`, **not supplied**) maps those keys to the NeXus template. The two parsers differ in what they read:

1. **WITec** (`witec.py`): an instrument export in nm; the Raman shift must be computed using the laser wavelength from the ELN.
2. **ROD** (`rod.py`): a database record (CIF) that already contains Raman shift; most of the code is key discovery and clean-up.

## Contents

| File | Format | Parser |
|---|---|---|
| [witec.md](witec.md) | WITec Alpha ASCII export `.txt` (`[Header]` / `[Data]`) | `witec.py` |
| [rod.md](rod.md) | Raman Open Database `.rod` (CIF) | `rod.py` |

## Parsers at a glance

Source code: [pynxtools-raman on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-raman) (links point to the `develop` branch; the inspected version is the one of 15th October 2026). Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| WITec Alpha `.txt` | Raman spectra / `NXraman` | plain Python line loop, no library | [witec.py](https://github.com/FAIRmat-NFDI/pynxtools-raman/blob/develop/src/pynxtools_raman/parsers/witec.py) |
| ROD `.rod` (CIF) | Raman Open Database records / `NXraman`, plus `NXcite` entries | `gemmi.cif` plus a text scan of the same file | [rod.py](https://github.com/FAIRmat-NFDI/pynxtools-raman/blob/develop/src/pynxtools_raman/parsers/rod.py) |

The reader class is `RamanReader` with `supported_nxdls = ["NXraman"]` (`src/pynxtools_raman/reader.py` l. 39), registered as the `raman` entry point. The two parser files sit next to `base.py` and `versioning.py` in `src/pynxtools_raman/parsers/` (develop, commit `9a30f9b` of 13th October 2026; the audited line numbers come from the 15th October copy supplied in the conversation). `versioning.py` was not read.

## Context

- Plugin: `pynxtools-raman` (public). Application definition: `NXraman`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** Each parser was read in full from the `develop` branch of 15th October 2026. Both documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin, so every "Scanner findings" section says so.
3. **Conventions.** Line numbers (`witec l.`, `rod l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited code.** Not read: `_RamanParser` (dispatch through `matches_file`, `unused_attrs` handling and the order in which `_parse()` and `post_process()` run are inferred from the two parsers), the two JSON configs, and the reader entry point.

## Summary of how the parsers build the x-axis and the metadata

| Format | Detection | X-axis | Laser / resolution handling | Unit handling |
|---|---|---|---|---|
| WITec `.txt` | `[Header]` and `[Data]` in the first 50 lines (witec l. 46–54) | measured wavelength in nm, converted to Raman shift: Δν̃ = 10⁷/λ_laser − 10⁷/λ_meas, stored under `data/x_values_raman` (witec l. 115–142) | laser wavelength is required from the ELN dict (witec l. 132) | both wavelengths assumed to be nm; `XAxisUnit` is collected but not compared |
| ROD `.rod` | a `data_` line in the first 50 lines (rod l. 69–79) | Raman shift read directly, `_raman_spectrum.raman_shift` (rod l. 232–236) | spectral resolution cm⁻¹ → nm: Δλ = Δν̃·λ_L²/10⁷ (rod l. 321–347) | cell parameters and dates are normalised; the grating value is inverted without unit (rod l. 356) |

## Cross-cutting observations

These points appear in both parsers or in the shared base-class contract. Each is a candidate for a single check or fix.

1. **Required inputs crash with an unhelpful exception.** WITec raises `IndexError` if the ELN has no laser wavelength (witec l. 132). ROD's `post_process` calls `float(None)` before its own `None` guard (rod l. 322–329), so records without laser wavelength or resolution fail the whole conversion.
2. **Units are assumed, not read.** WITec ignores `XAxisUnit` (witec l. 106); ROD writes a grating value without a unit (rod l. 356). A different export unit gives a wrong x-axis or a wrongly scaled field without a warning.
3. **Detection windows are fixed.** Both parsers look at the first 50 lines only (witec l. 51, rod l. 69–79). If the marker lies later, the file is silently rejected.
4. **Text handling is not robust.** WITec opens the file without `encoding` (witec l. 57) and splits data lines on commas, so a decimal comma or a non-UTF-8 `µ` fails; ROD assumes UTF-8 (rod l. 73, 85) and its raw-text scan is not CIF-aware: a `_` line inside a `;` text field, a `loop_` with trailing blanks or CRLF is misclassified (rod l. 101–111, 210).
5. **Fixed-position assumptions.** WITec skips exactly two mini-header lines (witec l. 78); ROD checks only `a` and `alpha` before reading `b`, `c`, `beta`, `gamma` (rod l. 263–280).
6. **Missing-value handling.** ROD never treats CIF `?` and `.` as missing, so `float("?")` raises `ValueError` (rod l. 268–285, 322–327, 356). WITec raises `IndexError` on an empty data section (witec l. 97).
7. **Always-true guards and dead code.** `x is not None or ""` (rod l. 259, 263, 276), `rod_lines is None` (rod l. 106), tz checks (rod l. 303–304), a wrong copy-pasted docstring (rod l. 163, "Prodigy export settings").
8. **Ordering with the base class.** WITec's `post_process` relies on the ELN dictionary being loaded before it runs, and both parsers rely on `_RamanParser` for dispatch; neither is checked here (witec behaviour 11).
9. **First match wins.** With several `…/beam_incident/wavelength` keys, dictionary order decides (witec l. 132). Duplicate CIF keys collapse silently (rod l. 139–143).
10. **Small gaps in the output.** The WITec unit alias list has one entry (witec l. 30–32); ROD reads `_journal_paper_doi` only to trigger the citation block and always appends a full stop to the citation title (rod l. 394–412); `__init__` takes `*args, **kwargs` and does not forward them (rod l. 63–64).

## Out of scope in this folder

Not documented here: `parsers/base.py` (`_RamanParser`), the JSON configs (`config_file_witec.json`, `config_file_rod.json`), the reader entry point and the ELN models, the `gemmi` library, and the `NXraman` application definition itself. Findings that depend on them are marked as inferred in the individual documents.
