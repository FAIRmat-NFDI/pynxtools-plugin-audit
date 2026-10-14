# Nanonis SXM parser and formatters (`pynxtools-spm`)

## Source files reviewed

- `pynxtools_spm/parsers/nanonis_sxm.py` — `SxmGenericNanonis` parser.
- `pynxtools_spm/nxformatters/nanonis/nanonis_sxm_stm.py` — `NanonisSxmSTM` formatter.
- `pynxtools_spm/nxformatters/nanonis/nanonis_sxm_afm.py` — `NanonisSxmAFM` formatter.
- The parser imports `pynxtools_spm.parsers.nanonispy` and shared parser helpers; the formatter imports `NanonisBase`, formatter helpers, and default configuration.

**Line-number note:** References below refer to the main branch on 13th October 2026.

## At a glance

| | |
|---|---|
| **Input format** | Nanonis `.sxm` scanning-probe microscopy image/scan file |
| **Parser class** | `SxmGenericNanonis(SPMBase)` (`nanonis_sxm.py`, approximately l.42) |
| **Parser entry point** | `parse()` calls `__get_nested_metadata_dict_and_signal()` (l.166) |
| **Raw-data reader** | `nap.read.Scan(file_name)` from `pynxtools_spm.parsers.nanonispy` (l.82) |
| **Parser output** | Flat dictionary with slash-separated metadata paths and signal paths; scan-channel information is aligned with `/DATA/INFO` metadata (l.156-159) |
| **STM formatter** | `NanonisSxmSTM(NanonisBase)` (`nanonis_sxm_stm.py`, l.65) |
| **AFM formatter** | `NanonisSxmAFM(NanonisSxmSTM, NanonisBase)` (`nanonis_sxm_afm.py`, l.53); reuses most STM formatting methods |
| **Formatted output** | Configuration-driven NeXus template, with scan-control, scan-region, scan-pattern, channel `NXdata`, and time fields |
| **Important dependency** | The exact binary signal decoding is delegated to `nanonispy`; base-class behaviour and parts of NXdata construction are inherited from `NanonisBase` / `SPMBase`. |# Nanonis SXM parser review (`pynxtools-spm`)

## Scope and files reviewed

This review is based on:

- `parsers/nanonis_sxm.py` — `SxmGenericNanonis`
- `nxformatters/nanonis/nanonis_sxm_stm.py` — `NanonisSxmSTM`
- `nxformatters/nanonis/nanonis_sxm_afm.py` — `NanonisSxmAFM`

## Overview

The SXM parser reads the Nanonis file through `nanonispy`, normalizes header metadata and channel information, and combines them with the image signal arrays. The STM formatter then maps the parsed content into the configured NeXus structure, including scan geometry, channel `NXdata` groups, axes, and timestamps. The AFM formatter reuses most of the STM formatting logic with an AFM-specific configuration and an `NXdata` override.

## Component responsibilities

### `SxmGenericNanonis` — raw parsing and metadata normalization

- Reads the file using `nap.read.Scan(file_name)` and obtains header metadata and signal arrays.
- Splits the raw header into key/value tokens and builds a metadata dictionary.
- Converts concatenated metadata keys to nested paths, then flattens metadata and signals into slash-separated paths.
- Extracts units written in parentheses into `@unit` fields, except for units listed in `UNIT_TO_SKIP`.
- Reads `/DATA/INFO` and aligns its channel rows with the channel names taken from the third tab-separated column.
- Merges aligned channel metadata and signal paths into the returned dictionary; signal paths are merged last.

### `NanonisSxmSTM` — NeXus formatting

- Reads formatter configuration and maps configured metadata into the NeXus template.
- Builds scan-control, scan-pattern, and scan-region groups from scan speed, fast-axis, range, point-count, offset, and angle metadata.
- Creates channel groups from `/DATA/INFO`, including signal values, axis arrays, units, calibration, and offset attributes.
- Orders image axes as `[Y, X]` for `NXdata` and adds pixel-centre coordinate arrays where needed.
- Constructs start and end timestamps from recording date/time and acquisition duration.
- Delegates bias-sweep construction to the `NanonisDatSTS` formatter through wrapper methods attached dynamically to `NanonisSxmSTM`.

### `NanonisSxmAFM` — AFM formatting

- Uses the AFM-specific default configuration.
- Reuses STM methods for scan pattern, scan region, image data, channel groups, and scan controllers.
- Overrides `NXdata` formatting to set X/Y axis metadata and pixel-centre coordinates.

## Step-by-step data flow

1. **Read:** `nanonispy` supplies the header metadata and signal arrays.
2. **Normalize:** header entries become nested and then slash-separated paths; parenthesized units are extracted as labels.
3. **Align channels:** `/DATA/INFO` rows are mapped to channel names and metadata.
4. **Merge:** channel metadata and signal arrays are combined into one dictionary.
5. **Format:** the STM formatter builds scan geometry and `NXdata`; AFM reuses most of that logic.

## Transformation formulas and conventions

| Transformation | Formula / implementation | What the helpers confirm |
|---|---|---|
| Scan step size | `Δxᵢ = Rᵢ / Nᵢ` | The SXM formatter uses range divided by point count. Verify whether the file's convention instead requires `Rᵢ / (Nᵢ − 1)` and whether this agrees with the pixel-centre coordinates. |
| Scan-region start/end | Calls `derive_scan_2d_start_end()` after reading offset, range, and angle | The implementation is not included in either parser or nexus transformer. |
| Pixel-centre coordinates | Calls `_pixel_centres()` | The implementation is not included in either parser or nexus transformer. |
| Image values and array shape | `to_intended_t(data)`; then the SXM formatter rearranges the array for `NXdata` | `to_intended_t` returns existing NumPy arrays unchanged. Lists are converted to NumPy arrays (normally `float64`); numeric strings are parsed as integers/floats; bracketed JSON-like strings are parsed; semicolon-separated values are split only if every part can be converted. It is type/structure normalization, not a calibration formula. `NXdata` axes are `[Y, X]`, with Y at index `0` and X at index `1`. |
| Calibration and offset | Stored as channel attributes in the shown SXM method | No operation applying `signal = raw × calibration + offset` is shown. |
| Unit labels | Parser extracts parenthesized unit text; formatter helper verifies units with Pint and can shorten symbols (for example, `nanometer` → `nm`) | These operations label/standardize unit metadata; they do not convert the underlying numeric values between units. |
| Numerical derivative helper | `Diff(axis=0, grid=x_val, acc=2)(y_val)` in `cal_dy_by_dx(y_val, x_val)` | This computes a numerical derivative using `findiff` with second-order accuracy and `x_val` as the grid. |
| End timestamp | `t_end = t_record + Δt_acquisition` | The SXM formatter adds acquisition duration to the recording timestamp. `add_local_timezone()` can attach the system or specified timezone to a timezone-naive ISO timestamp. |

### Transformation notes

- `get_nested_dict_from_concatenated_key()` turns keys containing `_` or `>` into nested dictionaries; `nested_path_to_slash_separated_path()` then emits slash-separated paths. This changes metadata structure, not signal values.
- `to_intended_t()` has a few notable special cases: common `on`/`off` spellings become the strings `true`/`false`; listed infinity/NaN spellings become `None`; and a list containing non-numeric strings may be left unconverted. Numeric list conversion defaults to `float64` unless an explicit supported dtype/callable is provided.

## Standard behaviour

- Reads Nanonis `.sxm` data through `nanonispy` rather than decoding the binary signal payload directly in the parser.
- Normalizes metadata into slash-separated paths and extracts available unit labels.
- Uses `/DATA/INFO` to associate channel names with channel metadata.
- Builds STM/AFM scan geometry and channel data in the configured NeXus template.
- Uses X/Y pixel-centre coordinates and an `[Y, X]` axis order for image `NXdata`.
- Builds an end timestamp by adding acquisition duration to the recording timestamp.

## Special behaviour

- Channel metadata alignment depends on fixed `/DATA/INFO` column positions, with the channel name read from the third tab-separated field.
- A channel direction of `both` produces forward and backward groups; other direction labels are treated as forward by the supplied logic.
- The STM formatter dynamically attaches bias-sweep wrapper methods and delegates that formatting to `NanonisDatSTS`.
- `gbl_scan_ranges` is module-level state used while constructing scan geometry.
- The AFM formatter inherits/reuses most STM formatting methods rather than implementing a separate full pipeline.

## Behaviour to investigate

1. **Step size and pixel centres:** verify `R/N` against the instrument's point-count convention and check consistency with `_pixel_centres()`.
2. **Scan geometry:** inspect `derive_scan_2d_start_end()` for offsets, angles, negative directions, and start/end conventions.
3. **Axis units:** the supplied code uses `self.scan_control.x_range_unit` for all step-size axes; confirm this is correct for every axis.
4. **Calibration and offset:** establish whether these values are metadata only or should be applied to signal values.
5. **Header and channel parsing:** test unusual header delimiters, duplicate keys, malformed unit parentheses, short/reordered `/DATA/INFO` rows, and duplicate channel names.
6. **Paths and directions:** check unexpected direction labels and missing forward/backward signal paths. Signal entries are merged last and could overwrite metadata on an exact path collision.
7. **Shared state and delegation:** test multiple files or formatter instances for `gbl_scan_ranges` leakage and review the runtime class monkey-patching used for bias sweeps.
8. **Timestamps:** test malformed or missing date/time fields, missing or zero acquisition duration, and timezone expectations.
9. **External behaviour:** verify assumptions in the base classes, helper functions, `nanonispy`, and default STM/AFM configurations.

## Comparison checklist for other parsers

- Input decoding and error handling
- Metadata normalization and unit extraction
- Channel discovery and metadata alignment
- Scan geometry, offsets, angles, and step-size formulas
- Pixel-centre and endpoint conventions
- Direction handling and axis ordering
- Calibration, offset, and numerical unit conversion
- State shared between files or formatter instances
- Timestamp parsing and acquisition-duration handling
## Scanner findings

No scanner run was perform for `pynxtools-spm`.