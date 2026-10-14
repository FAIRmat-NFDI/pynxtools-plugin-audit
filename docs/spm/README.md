# pynxtools-spm: parser audit

Status: **draft, based on static reading of the source** (manual review of the parsers and formatters, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-spm`. Nothing here was confirmed by running the parsers on real files unless a section says so.

This folder documents how each parser of `pynxtools-spm` turns vendor data into the `NXstm` and `NXafm` data models: which library reads the file, where the scan geometry and the axes come from, which formulas and unit conversions are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

Unlike `pynxtools-xps`, a `pynxtools-spm` format is handled in two steps, so each document covers both:

1. **Parser** (`pynxtools_spm/parsers/`): reads the file into a flat dictionary of slash-separated paths.
2. **Formatter** (`pynxtools_spm/nxformatters/`): maps that dictionary to the NeXus template with a JSON config and derives the scan region, step sizes, axes and timestamps.

## Contents

| File | Format | Parser | Formatter |
|---|---|---|---|
| [nanonis_dat.md](nanonis_dat.md) | Nanonis `.dat` (STS) | `nanonis_dat_generic.py` | `nanonis/nanonis_dat_sts.py` |
| [nanonis_sxm.md](nanonis_sxm.md) | Nanonis `.sxm` (STM and AFM images) | `nanonis_sxm.py` | `nanonis/nanonis_sxm_stm.py`, `nanonis/nanonis_sxm_afm.py` |
| [omicron_sm4.md](omicron_sm4.md) | Omicron / RHK `.sm4` | `omicron_sm4.py`, `rhk_sm4_metadata.py` | `omicron/omicron_sm4_stm.py` |
| [bruker_flt.md](bruker_flt.md) | Bruker SPMLab `.flt` | `bruker_flt.py` | `bruker/bruker_flt_afm.py` |
| [bruker_spm.md](bruker_spm.md) | Bruker NanoScope `.spm` | `bruker_spm.py` | `bruker/bruker_spm_afm.py` |
| [bruker_txt.md](bruker_txt.md) | Bruker NanoScope force-curve export `.spm.txt` | `bruker_txt.py` | `bruker/bruker_txt_afm.py` |

## Parsers at a glance

Source code: [pynxtools-spm on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-spm/) (links point to the `main` branch). Documentation: [pynxtools-spm docs](https://fairmat-nfdi.github.io/pynxtools-spm/). The reader selects the parser from the file extension and the ELN vendor/model. Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code | Documentation |
|---|---|---|---|---|
| Nanonis `.dat` | STS, bias spectroscopy / `NXstm` | own text parser | [parsers](https://github.com/FAIRmat-NFDI/pynxtools-spm/tree/main/src/pynxtools_spm/parsers/), [nxformatters](https://github.com/FAIRmat-NFDI/pynxtools-spm/tree/main/src/pynxtools_spm/nxformatters/) | [docs](https://fairmat-nfdi.github.io/pynxtools-spm/) |
| Nanonis `.sxm` | STM and AFM images / `NXstm`, `NXafm` | `nanonispy` (bundled) | same folders | [docs](https://fairmat-nfdi.github.io/pynxtools-spm/) |
| Omicron `.sm4` | STM images / `NXstm` | own binary header reader + `gwyddionpy` for the images | [omicron_sm4.py](https://github.com/FAIRmat-NFDI/pynxtools-spm/blob/main/src/pynxtools_spm/parsers/omicron_sm4.py), [rhk_sm4_metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-spm/blob/main/src/pynxtools_spm/parsers/rhk_sm4_metadata.py) | [reference](https://fairmat-nfdi.github.io/pynxtools-spm/reference/omicron.html), [scan region](https://fairmat-nfdi.github.io/pynxtools-spm/explanation/scan-region/omicron-sm4.html) |
| Bruker `.flt` | AFM images (one channel per file) / `NXafm` | own INI header reader + `gwyddionpy` | [bruker_flt.py](https://github.com/FAIRmat-NFDI/pynxtools-spm/blob/main/src/pynxtools_spm/parsers/bruker_flt.py) | [reference](https://fairmat-nfdi.github.io/pynxtools-spm/reference/bruker.html), [scan region](https://fairmat-nfdi.github.io/pynxtools-spm/explanation/scan-region/bruker-flt.html) |
| Bruker `.spm` | AFM images (many channels, both directions) / `NXafm` | own ASCII header reader + `gwyddionpy` | [bruker_spm.py](https://github.com/FAIRmat-NFDI/pynxtools-spm/blob/main/src/pynxtools_spm/parsers/bruker_spm.py) | [reference](https://fairmat-nfdi.github.io/pynxtools-spm/reference/bruker.html), [scan region](https://fairmat-nfdi.github.io/pynxtools-spm/explanation/scan-region/bruker-spm.html) |
| Bruker `.spm.txt` | AFM force curves / `NXafm` with `point_forceSCAN` | own text parser | [bruker_txt.py](https://github.com/FAIRmat-NFDI/pynxtools-spm/blob/main/src/pynxtools_spm/parsers/bruker_txt.py) | [reference](https://fairmat-nfdi.github.io/pynxtools-spm/reference/bruker.html) |

Note: any `.txt` input with `experiment_technique: AFM` is routed to the Bruker TXT parser; see [bruker_txt.md](bruker_txt.md). General structure of a reader: [reader structure](https://fairmat-nfdi.github.io/pynxtools-spm/explanation/reader-structure.html).

## Context

- Plugin: `pynxtools-spm` (public). Application definitions: `NXstm`, `NXafm`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** Each parser and its formatter were read in full from the `main` branch of 13th October 2026. The Nanonis and Bruker documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*. [omicron_sm4.md](omicron_sm4.md) is organised by parser and formatter workflow instead and ends with a *Validation status* section.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin, so every "Scanner findings" section says so.
3. **Conventions.** Line numbers (`l. N`) refer to the source version that was inspected and will drift with later commits. The Bruker documents write `parser l.` and `formatter l.`; the Omicron document writes `file.py:N`; the Nanonis documents name the file in each reference. Statements marked *(docs)* come from the project documentation, not from reading code.
4. **Inherited code.** Base classes and helpers are reviewed only where a document says so. Not read in full: `SPMBase`, `NanonisBase`, `OmicronBase`, `BrukerBase` (including `rearrange_data_according_to_axes`), the base-formatter methods `derive_scan_2d_start_end()`, `_pixel_centres()` and `put_scan_2d_region_field_in_template()`, `nxformatters/helpers.py` (partly), `rhk_sm4_metadata.py` (partly), `nanonispy`, and the default JSON configs.

## Summary of how the parsers build the scan geometry

| Format | Offset meaning | Range / step size | Axis values | Fast / slow axis | Orientation and rotation |
|---|---|---|---|---|---|
| Nanonis `.dat` (STS) | not spatial | ΔV = (V_end − V_start) / N (`nanonis_dat_sts.py` l. 119–137) | bias values from the data column | not applicable | not applicable |
| Nanonis `.sxm` | read with range and angle, passed to `derive_scan_2d_start_end()` (not read) | Δx = R / N | `_pixel_centres()` (not read), axes `[Y, X]` | from scan metadata; `both` direction gives forward and backward groups | angle read, application not verified |
| Omicron `.sm4` | frame **centre** | r = abs(scale)·N; fallback step Δ = r / N | pixel centres, ascending, computed in the parser | fast `x` unsigned; slow `+y` or `−y` from the sign of `RHK_Yscale` (zero gives `−y`) | `RHK_Angle` not applied in the coordinates |
| Bruker `.flt` | frame **centre** (contradicts Gwyddion's corner reading) | Δ = R / N, skipped if N < 2 | pixel centres, ascending, from the image shape | fast `+x` / `−x` from `ScanDirection`; slow `y` unsigned | `Rotation` exported, not applied |
| Bruker `.spm` | frame **centre** | R_y = R_x / aspect ratio; Δ = R / N | pixel centres, ascending, rebuilt from the image shape if counts differ | fast `x` unsigned; slow `+y` / `−y` from `\Frame direction` | `\Rotate Ang.` exported, not applied |
| Bruker `.spm.txt` | x/y offsets as given | R = abs(last − first) of the ramp array; Δ = R / (N − 1) | ramp arrays | not applicable (force ramp) | not applicable |

## Summary of calibration and unit handling

| Format | Signal calibration | Unit labels | Unit conversion of values |
|---|---|---|---|
| Nanonis `.dat` | none; current multiplied by `flip_number` (default 1) | from `(unit)` in column headers | none |
| Nanonis `.sxm` | calibration and offset stored as channel attributes, not applied | from `(unit)` in header, shortened with pint | none |
| Omicron `.sm4` | done by `gwyddionpy` (`RHK_Zscale`, `RHK_Zoffset`), parser exports `channel.data` unchanged | keys ending in `unit(s)` rewritten to `…/@unit` | none |
| Bruker `.flt` | `gwyddionpy` values used as returned | trailing token of a header value; `data/@unit` from `si_unit_z` | none |
| Bruker `.spm` | parser multiplies the image by 1 / m(u_sens) (×1000 if the Z scale is in mV) | trailing token of a header value | scale factor above; formatter converts geometry strings with pint |
| Bruker `.spm.txt` | none | column-name token, header trailing token | none; amplitude setpoint = ratio × reference amplitude |

## Cross-cutting observations

These points appear in more than one parser. Each is a candidate for a single check or fix.

1. **Step-size convention is not uniform.** R / N for Nanonis `.sxm`, Omicron, Bruker `.flt` and `.spm` (pixel pitch, consistent with pixel-centre axes); (V_end − V_start) / N for the Nanonis STS bias sweep; R / (N − 1) for Bruker force curves. For endpoint-inclusive sweeps `N − 1` intervals is the usual count, so the STS bias step is worth checking first (`nanonis_dat_sts.py` l. 119–137).
2. **Frame offset is read as the centre** in Bruker `.flt`/`.spm` and Omicron, supported by tests and the vendor manual (docs). Gwyddion's SPMLab module reads the `.flt` offset as a corner. For Nanonis `.sxm` the convention sits in `derive_scan_2d_start_end()`, which was not read.
3. **Unit-key spelling differs between parsers.** `…/@unit` (Nanonis, Bruker `.flt`, Omicron, Bruker `.spm`), `…/@units` for scaled values in Bruker `.spm` (`bruker_spm.py` l. 271), and `…/unit` in Bruker `.spm.txt`. The formatters write `…/@units` to the template. A config written for one parser cannot be reused for another.
4. **Unit parsing regexes have gaps.** Bruker `.spm` and `.spm.txt` do not split negative values with a unit in the scaled pattern, exponents, or units containing `/` such as `nm/V`; the `.spm` formatter recovers geometry values with pint, other header values stay strings. Omicron's `(units|unit)$` rewrite over-matches any key ending in "unit" (`omicron_sm4.py:12,56`). Bruker `.flt` takes any trailing token as unit (`2 nd order` gives unit `nd`).
5. **Fragile matching of data to metadata.**
   - Bruker `.spm`: the *k*-th image section is paired with the *k*-th gwyddionpy channel (`bruker_spm.py` l. 140–142).
   - Omicron: images matched by lower-cased `Page ID`; identical IDs overwrite each other (`omicron_sm4.py:46-49`).
   - Nanonis `.sxm`: channel metadata alignment depends on fixed `/DATA/INFO` column positions.
   - Bruker `.flt`: the channel name is taken from the first key ending in `/data`.
6. **Silent overwrites and duplicates.** Bruker `.spm` duplicate channel and direction; Bruker `.flt` duplicate header keys and lines before the first section; Nanonis `.sxm` signal paths merged last and able to replace metadata on an exact path collision; Bruker `.spm` exposes a one-direction channel as both `forward` and `backward`.
7. **Silent fallbacks and swallowed errors.**
   - Bruker `.spm` scale factor falls back to `1.0` if pint fails (`bruker_spm.py` l. 247–248).
   - Bruker `.spm` aspect ratio without `:` falls back to 1:1 without a message.
   - Bruker `.spm.txt` stops reading at a column-count mismatch and keeps truncated arrays (`bruker_txt.py` l. 96–102).
   - Omicron end-time errors (`ValueError`, `TypeError`) are ignored (`omicron_sm4_stm.py:493-494`).
   - Bruker `.flt` step size is skipped without a message for N < 2.
1. **Possible bug: Omicron end time.** `datetime.timedelta(float(data))` takes days as its first positional argument (`omicron_sm4_stm.py:490`). If the raw duration is in seconds, the end time is wrong.
2. **Step size and axes can disagree.** Bruker `.flt` and `.spm` compute the step size from header point counts but rebuild the axes from the image shape afterwards; `.spm` warns about the mismatch, `.flt` does not.
3. **Rotation is exported but not applied** in Bruker `.flt` and `.spm`, and the Omicron coordinates ignore `RHK_Angle`. A rotated frame would make `x` and `y` the wrong names for the fast and slow axis.
4. **Direction handling differs.** Omicron: Forward/Backward names the pass, the fast axis stays unsigned. Bruker `.flt`: `ScanDirection` signs the fast axis. Bruker `.spm`: `\Frame direction` signs the slow axis. Nanonis: direction `both` creates forward and backward groups, other labels are treated as forward. The slow axis of a `.flt` file is not stored at all.
5. **Calibration is delegated to libraries.** `gwyddionpy` (Omicron, `.flt`, `.spm`) and `nanonispy` (`.sxm`) decide the physical values and, in part, the row order. Confirm there is no double calibration through the configs, and that orientation is flipped in exactly one place (`BrukerBase.rearrange_data_according_to_axes`, `OmicronBase`).
6. **Axis units.** Nanonis `.sxm` uses `scan_control.x_range_unit` for all step-size axes; Omicron reads X and Y units separately but emits ranges and fallback pitches through the start-unit fields; Bruker `.spm` converts the range to the X offset unit (`bruker_spm_afm.py` l. 188), which fails if no offset is configured.
7. **Mutable or shared state.**
    - `gbl_scan_ranges` is module-level state in the Nanonis `.sxm` formatter.
    - The Nanonis STM formatter delegates bias sweeps to `NanonisDatSTS` through methods attached at runtime.
    - Omicron formatter keeps `_scan_list`, `_scan_tag_raw_data`, `_scan_tag_to_data_group` as class attributes and swaps `self.raw_data` temporarily without `finally`.
    - The Bruker `.spm` formatter calls `popitem()` on config entries, which consumes them; the `.flt` formatter avoids this on purpose.
8. **Timestamps are handled four ways.** Bruker `.flt` uses an explicit month table (locale independent, naive); Bruker `.spm.txt` uses `strptime` with `%p %a %b` (locale dependent, naive); Nanonis and Omicron add the local timezone with `add_local_timezone()` to a naive timestamp. A failed parse mostly only logs a warning.
9. **Hard-coded names in formatters.** Omicron scan controllers are only found for page labels starting with `topography`, `current`, `backward` or `forward` (`omicron_sm4_stm.py:379-382`); Bruker `.spm.txt` reads `/Calc_Ramp_Ex_nm` and `/Calc_Ramp_Rt_nm` by name and writes `None` start/end/points fields if a ramp is missing (`bruker_txt_afm.py` l. 237, 251, 352–377).
10. **Metadata-only pages.** Omicron non-image pages (spectra) export metadata only, and an image without a matching channel still exports coordinates although the warning says only metadata is read. Whether such pages reach the NeXus file depends on the config and base formatter.
11. **Derived conductance.** The Nanonis STS formatter computes dI/dV with second-order finite differences on the actual voltage grid (`cal_dy_by_dx`, `Diff(axis=0, grid=V, acc=2)`), applied to the sign-adjusted current. The same helper is shared with Nanonis `.sxm`. Its numerical behaviour for non-monotonic or repeated voltages was not tested.
12. **Dormant code.** `_construct_nxscan_controllers()` in `NanonisDatSTS` is a stub (`pass`); the TXT scan-control dataclass has unused `z_points` and `z_offset` fields.

## Out of scope in this folder

Not documented here: `parsers/base_parser.py` and shared parser helpers, `nxformatters/helpers.py`, the base formatter classes (`NanonisBase`, `OmicronBase`, `BrukerBase`), the default JSON configs in `configs/`, the vendored `nanonispy` package, the reader entry point and the ELN models. Findings that depend on them are marked "not read" in the individual documents.
