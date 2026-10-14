# Bruker SPMLab `.flt` parser and formatter (`pynxtools-spm`)

## Source files reviewed

- `pynxtools_spm/parsers/bruker_flt.py` — `FltBruker` parser (207 lines).
- `pynxtools_spm/nxformatters/bruker/bruker_flt_afm.py` — `BrukerFltAFM` formatter (432 lines).
- Inherited and not read: `BrukerBase` (`nxformatters/bruker/bruker_base.py`), `derive_scan_2d_start_end()`, `_pixel_centres()`, `put_scan_2d_region_field_in_template()` (base formatter) and `_get_data_unit_and_others()` (`nxformatters/helpers.py`).
- Project docs: `reference/bruker.html`, `explanation/scan-region/bruker-flt.html`.

**Line-number note:** References below refer to the main branch on 13th October 2026. `parser l.` = `bruker_flt.py`, `formatter l.` = `bruker_flt_afm.py`.

## At a glance

|                        |                                                                                                                                                       |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input format**       | Bruker SPMLab `.flt` / `.FLT` (INI-style text header + binary float raster); AFM                                                                      |
| **Parser class**       | `FltBruker(SPMBase)` (parser l. 62–198)                                                                                                               |
| **Raster reader**      | `gwyddionpy.load()` (Gwyddion `spmlabf` importer) (parser l. 187)                                                                                     |
| **Header reader**      | Own parser `_get_raw_header_dict()` (parser l. 102–144); keeps keys gwyddionpy drops, grouped by section (parser l. 104–108)                          |
| **Raw-data storage**   | Nested dict per channel: `name`, `data`, `x_real`, `y_real`, `meta`, `header` (parser l. 146–166, 190–194)                                            |
| **Output from parser** | Flattened dict with slash-separated paths, e.g. `/Height/data`, `/Height/meta/SetPoint`, `/Height/header/Data Parameters/OffsetX` (parser l. 196–198) |
| **Formatter class**    | `BrukerFltAFM(BrukerBase)` (formatter l. 66–432); default config `bruker_flt_afm` (formatter l. 106–112)                                              |
| **Target definition**  | `NXafm` (docs)                                                                                                                                        |
| **Tested versions**    | SPMLab `1.00` (`[Data Version]` section) (docs)                                                                                                       |
| **Project context**    | See the [project repository](https://github.com/FAIRmat-NFDI/pynxtools-spm/). The same gwyddionpy package reads NanoScope `.spm`.                     |

**Standard behaviour.** The parser loads the file with gwyddionpy, reads the ASCII header separately and builds one dict per channel (parser l. 187–198). The formatter resolves the `/CHANNEL/` placeholder in the config (formatter l. 126–156), lets the config walker write mapped fields, and adds the derived scan region, mesh-scan step sizes, fast-axis sign and `NXdata` axes (formatter l. 96–100, 202–355, 361–432).

**Comparison with other `pynxtools-spm` parsers.** One `.flt` holds one channel in one scan direction; the `.spm` format holds many channels and both directions. Unlike `BrukerSpmAFM`, this formatter does not build the scan region from a config-driven group of raw keys but from plain scalars mapped by the config (formatter l. 69–75).

## Formula / transformation

### Parser: header value and unit split

**Location:** `_split_value_and_unit()` (parser l. 72–100); regexes at l. 36, 40, 48.

```python
VALUE_WITH_UNIT    = rf"^(?P<value>{NUMBER})\s+(?P<unit>\S+)$"                  # 'SetPoint=0.030000 V'
GAIN_WITH_CONSTANT = rf"^(?P<value>{NUMBER})\s*\((?P<constant>{NUMBER})\)$"     # 'GainP=0.8 (1000.0)'
```

- A trailing non-numeric token becomes the unit; the value stays a **string** (l. 100).
- A unit starting with `(` or a numeric token is not a unit (l. 96–97).
- A unit whose lower-case form is in `UNIT_TO_SKIP` is stored as `""` (l. 98–99).
- A PID gain keeps only the leading number; the constant is dropped (l. 85–87, comment l. 42–47).

No unit conversion happens in the parser.

### Parser: channel values

`_get_channel_dict()` (l. 146–166): `data` ← `channel.data`, `data/@unit` ← `si_unit_z`, `x_real`/`y_real` ← `xreal`/`yreal` with `si_unit_xy` (l. 149–155). All from gwyddionpy, unscaled.

### Formatter: scan region

**Location:** `construct_scan_region_grp()` (formatter l. 257–294).

Offsets and ranges are read from the config (`_read_xy_fields()`, l. 227–255), stored in `scan_control` (l. 286–291), then `derive_scan_2d_start_end()` and `put_scan_2d_region_field_in_template()` are called (l. 293–294).

$$
x_{\text{start}} = o_x - \frac{R_x}{2},\qquad x_{\text{end}} = o_x + \frac{R_x}{2}
$$

(same for `y`; formula stated in the docstring, l. 272–274; the arithmetic is in the base class, not read). `OffsetX/Y` is the **centre** of the frame; Gwyddion reads it as a corner (l. 274–276).

### Formatter: mesh-scan step size

**Location:** `construct_scan_pattern_grp()`, l. 341–351.

```python
# The step is the pixel pitch, so the axis values are pixel centres.
self.template[step_key] = scan_range / int(n_points)
```

$$
\Delta_a = \frac{R_a}{N_a},\quad a\in\{x,y\}
$$

Skipped without a message if `scan_range is None`, `N` is falsy or `N < 2` (l. 344–345). The unit is the range unit, written to `/@units` (l. 349–351).

### Formatter: fast-axis sign

**Location:** l. 319–335. `ScanDirection` (`…/meta/ScanDirection`, lower-cased): `forward` → `+x`, `backward` → `-x`, anything else → `x` with a warning. Slow axis is always unsigned `y` (l. 335), because SPMLab stores no slow direction (l. 316–318).

### Formatter: NXdata axes

**Location:** `_nxdata_grp_from_conf_description()` (formatter l. 361–432).

Only when the config has no `0`/`1` axis entries (l. 390), the signal is 2D (l. 398) and `x_start`/`y_start` are known (l. 402–407). `y_points, x_points = signal.shape` (l. 413–415); axes `Y` and `X` are `_pixel_centres("y")`/`("x")` (l. 416–419). Both axes ascend; row 0 is the bottom row (l. 409–412). `@axes = [Y, X]` (l. 430).

### Formatter: timestamp

**Location:** `_set_start_end_time()` (l. 162–196), regex `SPMLAB_TIMESTAMP` (l. 43–46), month table (l. 50–63). `'Jun.17.2026 08:03:43'` → `datetime(...)` → `isoformat()`, naive (no timezone). Month matching is explicit, not locale-dependent (l. 48–49).

## Standard behaviour

1. **Load.** `gwyddionpy.load(self.file_path)` (parser l. 187); `/source_format` stored (l. 190).
2. **Header.** `_get_raw_header_dict()` reads the first `HEADER_CHUNK_SIZE = 8192` bytes (l. 111), finds `DataOffset` (l. 112), re-reads up to the offset if the header is longer (l. 119–122), decodes `latin-1` (l. 126) and splits sections (l. 130–134) and `key=value` at the first `=` (l. 138). Missing `DataOffset` → warning, `{}` (l. 113–118).
3. **Per channel.** `_get_channel_dict()` (l. 146–166), the same `header_dict` object attached as `header` (l. 194).
4. **Meta units.** Every gwyddionpy `meta` value passes `_split_value_and_unit()`; `…/@unit` only if a unit was found (l. 159–164).
5. **Flatten.** `phs.nested_path_to_slash_separated_path()` (l. 197).
6. **Config.** `_get_conf_dict()` loads the user config or `bruker_flt_afm` (formatter l. 106–112) and replaces `/CHANNEL/` by `/<channel>/` (l. 126–156). The channel name is the key ending in `/data` that holds an `ndarray` (l. 121–123).
7. **Template.** `get_nxformatted_template()`: walk config → ELN → special fields (l. 96–100). Special handlers: `SPM_SCAN_CONTROL[spm_scan_control]` → `_construct_nxscan_controllers`, `start_time` → `_set_start_end_time` (l. 77–80).
8. **Scan controller.** `_construct_nxscan_controllers()` builds `scan_region` and `meshSCAN[mesh_scan]` if the config has them (l. 202–225).
9. **Axes.** `_nxdata_grp_from_conf_description()` calls the base implementation then attaches axes (l. 377–430).

## Special behaviour

1. **One channel per file.** The channel name (`DataName`, e.g. `Height`) is the key prefix and names the `NXdata` group (docs).
2. **Header read twice on purpose.** gwyddionpy drops some keys and merges the two `Leveling` keys; the own reader keeps them per section (parser l. 104–108).
3. **PID gains lose their loop constant** (parser l. 85–87).
4. **Header values stay strings**; gwyddionpy `meta` values go through the same splitter (parser l. 159–164).
5. **Unit `""`** is written for units in `UNIT_TO_SKIP` (parser l. 98–99), so `…/@unit` can be an empty string.
6. **The same `header_dict` object** is attached to every channel (parser l. 194); harmless for one channel.
7. **Rotation is not applied.** Comment l. 312–314: `Rotation` is 0 in every file seen so far; a rotated frame would make `x`/`y` wrong names for fast/slow.
8. **Slow axis unsigned** (formatter l. 316–318, 335).
9. **Config values are read without mutation** (`next(iter(...))`, l. 232–244), because the walker recurses into the same dicts afterwards.
10. **Axes from the config win.** If the config has `0` or `1` axis entries, no derived axes are added (l. 389–391).
11. **Placeholder fallback.** No channel data → warning and the unresolved `/CHANNEL/` paths stay in the config (l. 136–143).
12. **Row flip and NXdata construction** are in `BrukerBase` (not read).

## Behaviour to investigate

1. **Lines before the first `[section]`** are written into a throw-away dict (`section_dict` starts `{}`, parser l. 125, 141) and lost without a warning.
2. **Duplicate keys within a section** overwrite silently (parser l. 141).
3. **`DataOffset` beyond the first chunk.** `DATA_OFFSET` is searched only in the first 8192 bytes (parser l. 111–112); a longer header with `DataOffset` further down is treated as missing (l. 113–118).
4. **Empty `/@unit`.** `UNIT_TO_SKIP` gives `""` (parser l. 99) rather than no key; check how the formatter treats it.
5. **Value/unit regex edge cases.** `VALUE_WITH_UNIT` takes any `\S+` after a number as unit (parser l. 40); `2 nd order` would give value `2`, unit `nd`.
6. **Step size from header counts, axes from image shape.** The step size uses the header `N` (formatter l. 342–348), but axes are rebuilt from the signal shape afterwards (l. 413–419) and `scan_control.x_points/y_points` are overwritten (l. 414–415). If they differ, step size and axes disagree; the SPM formatter warns in this case, this one does not.
7. **Silent skip of step size** for `N < 2` or missing range (formatter l. 344–345).
8. **Numeric type of `scan_range`.** Parser values are strings (parser l. 100, 141); `scan_range / int(n_points)` (formatter l. 348) needs a number. Confirm that `_get_data_unit_and_others()` converts it.
9. **Slow-axis direction.** Never known; docs list it as an open question. The ascending axes follow the "row 0 = bottom" assumption (formatter l. 409–412), tested by cross-correlation only.
10. **Rotation not applied** (formatter l. 312–314); check that a non-zero `Rotation` is at least flagged.
11. **Unknown `ScanDirection`.** Falls back to unsigned `x` with a warning (l. 327–333); a missing key is silent (direction `""`).
12. **Channel detection** relies on the first `…/data` key with an `ndarray` (formatter l. 121–123) and `key.split("/")[1]`; a channel name containing `/` breaks it.
13. **Timestamp.** Naive, no timezone (formatter l. 188–196); unparsed date only logs a warning (l. 171–177).
14. **Calibration of `channel.data`.** Confirm gwyddionpy returns the values in `si_unit_z` for all channel types (parser l. 150–151).
15. **Cross-parser consistency.** Step size `R/N` matches the SPM formatter but not the TXT formatter (`R/(N-1)`).
16. **Inherited code.** Review `BrukerBase`, `derive_scan_2d_start_end()`, `_pixel_centres()` and `_get_data_unit_and_others()` (not read).

## Scanner findings

No scanner run was performed for `pynxtools-spm`.
