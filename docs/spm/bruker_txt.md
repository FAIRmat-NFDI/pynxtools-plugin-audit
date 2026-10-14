# Bruker NanoScope `.spm.txt` force-curve parser and formatter (`pynxtools-spm`)

## Source files reviewed

- `pynxtools_spm/parsers/bruker_txt.py` — `TxtBruker` parser (176 lines).
- `pynxtools_spm/nxformatters/bruker/bruker_txt_afm.py` — `BrukerTxtAFM` formatter and `NXScanControlPointForce` dataclass (377 lines).
- Inherited: `BrukerBase` (`nxformatters/bruker/bruker_base.py`), `_get_data_unit_and_others()`, `to_intended_t()`, `unit_short()` (`nxformatters/helpers.py`).
- Project docs: `reference/bruker.html` (section `.spm.txt`).

**Line-number note:** References below refer to the main branch on 13th October 2026. `parser l.` = `bruker_txt.py`, `formatter l.` = `bruker_txt_afm.py`.

## At a glance

| | |
|---|---|
| **Input format** | Bruker NanoScope ASCII export of a force ramp, `.spm.txt`; AFM force curve |
| **Parser class** | `TxtBruker(SPMBase)` (parser l. 11–176) |
| **Reader** | Plain Python line loop, `open(..., encoding="utf-8")`, no external library (parser l. 56) |
| **Raw-data storage** | `bruker_data_dict`; arrays accumulated column-wise as lists of strings (parser l. 53, 94–105) |
| **Output from parser** | Flat dict: `/<Section>/<idx>/<Key>` (+ `…/unit`), `/<Column>` (float `ndarray`), `/<Column>/unit` (parser l. 111–119, 121–131) |
| **Formatter class** | `BrukerTxtAFM(BrukerBase)` (formatter l. 71–377); default config `bruker_txt_afm` (formatter l. 106–109) |
| **Scan-control type** | `NXScanControlPointForce` dataclass replaces the base 2D scan control (formatter l. 44–68, 74–78, 98) |
| **Target definition** | `NXafm`, with `point_forceSCAN[point_force_scan]` instead of `meshSCAN[mesh_scan]` (formatter l. 195–201; docs) |
| **Tested versions** | NanoScope 9.x (Dimension Icon), ELN model `NanoScope` (docs) |
| **Project context** | See the [project repository](https://github.com/FAIRmat-NFDI/pynxtools-spm/). The only Bruker text parser and the only non-raster path. |

**Standard behaviour.** The parser strips the wrapping quotes of every line, builds numbered sections from `\*`/`\?` markers, converts `\Key: value` lines to metadata, takes the column header after `Force file list end` and converts the numeric rows to float arrays (parser l. 56–131). The formatter derives approach/retrace start, end and range from the ramp arrays, point counts from `Samps/line`, step sizes, the amplitude setpoint and the timestamp (formatter l. 115–175, 207–334).

**Comparison with other `pynxtools-spm` parsers.** Output is one-dimensional ramp arrays (`Defl_pN_Ex`, `Calc_Ramp_Rt_nm`, …), not images. Unit keys are `…/unit` here; the FLT parser writes `…/@unit`, the SPM parser `…/@unit` and `…/@units`.

## Formula / transformation

### Parser: unit from the column name

**Location:** `_extract_unit_from_column_name()` (parser l. 20–39).

```python
tokens = col_name.split("_")
for i, token in enumerate(tokens):
    if token in {"Ex", "Rt"}:
        if i + 1 < len(tokens): return tokens[i + 1]   # Calc_Ramp_Ex_nm -> 'nm'   (l. 34–35)
        if i > 0:               return tokens[i - 1]   # Time_s_Ex       -> 's'    (l. 36–38)
```

The unit is the token after the direction marker if present, otherwise the token before it. No unit validation.

### Parser: column values

`np.array([float(x) for x in array_data[ind]])` (parser l. 124–126). Direct string → float, no scaling.

### Parser: header value and unit

**Location:** `extract_data_unit()` (parser l. 133–176). Key: whitespace → `_`, `\` → `/`, `"` removed (l. 144–146); value: `"` removed (l. 148).

| Pattern | Example | Output | Lines |
|---|---|---|---|
| scaled | `V (0.00001164153 kHz/LSB) 172.0493 kHz` | `key = '172.0493'`, `key/unit = 'kHz'` | 152–157 |
| bracket | `S [AFMMode] Contact` | `key/AFMMode = 'Contact'` | 160–164 |
| value + unit (minus allowed) | `-5.0 nm` | `key = '-5.0'`, `key/unit = 'nm'` | 167–172 |
| other | anything else | `key = val` | 174–176 |

### Formatter: approach / retrace region

**Location:** `construct_scan_region_grp()` (formatter l. 207–266).

$$
s = r_0,\qquad e = r_{M-1},\qquad R = |e - s|
$$

where `r` is `/Calc_Ramp_Ex_nm` (approach, l. 237–248) or `/Calc_Ramp_Rt_nm` (retrace, l. 251–262). The first and last element keep the physical ramp direction (docstring l. 217–218). Unit: `/unit` key or `"nm"` (l. 239, 253), shortened with `unit_short()`.

### Formatter: step size

**Location:** `construct_point_force_scan_grp()` (formatter l. 272–334), l. 307–326.

$$
\Delta_{\text{approach}} = \frac{R_{\text{approach}}}{N_{\text{approach}}-1},\qquad
\Delta_{\text{retrace}} = \frac{R_{\text{retrace}}}{N_{\text{retrace}}-1}
$$

Only if the range is truthy and `N > 1` (l. 309, 319); errors `TypeError`/`ZeroDivisionError` are caught with a warning (l. 327–330).

### Formatter: point counts

**Location:** l. 283–305. `Samps/line` is split on whitespace: approach = first token; retrace = second token, or the first if there is only one (l. 294–300). `int(...)` of the token.

### Formatter: amplitude setpoint

**Location:** `_construct_cantilever_oscillator()` (formatter l. 144–175).

$$
A_{\text{setpoint}} = r_{\text{amp}}\cdot A_{\text{ref}}
$$

`r_amp` = raw `Amplitude_Ratio` (via `to_intended_t`, l. 159), `A_ref` = `reference_amplitude` (l. 153–156). Written with the unit of `A_ref` (l. 163–168).

### Formatter: timestamp

**Location:** `_set_start_end_time()` (formatter l. 115–138). Formats `%I:%M:%S %p %a %b %d %Y` and a double-space variant for days < 10 (l. 127), e.g. `03:44:35 PM Mon May 15 2023`; result `isoformat()`, naive.

## Standard behaviour

1. **Open and strip.** `open(..., encoding="utf-8")` (parser l. 56); `line.strip()` (l. 58) and `line.strip('"')` (l. 63).
2. **Sections.** Lines starting with `\*` or `\?` (l. 65–76): `Force file list end` sets `current_section = None` (l. 68–70); other names are snake-cased (l. 15–17) and numbered per name (`Name/idx`, l. 73–75).
3. **Column header.** First line without `:` after the end marker, while `array_header is None`, `current_section is None` and `last_line` contains `Force file list end` (l. 81–88).
4. **Numeric rows.** Lines without `:` once a header exists are split on whitespace (l. 92–93); the first row sets the column count (l. 94–95).
5. **Key/value.** Lines with `": "` are split at the first occurrence and sent to `extract_data_unit()` (l. 110–112); prefixed with `/<current_section>` if inside a section (l. 113–116).
6. **Arrays.** After the loop: names from `array_header.strip().split()` (l. 122); float arrays (l. 124–126) plus `/<name>/unit` if found (l. 127–129).
7. **Formatter.** Walk config → ELN → special fields (formatter l. 100–104). Special handlers: scan controller, `cantilever_oscillator`, `start_time` (l. 80–84).
8. **Scan controller.** `scan_region` and `point_forceSCAN[point_force_scan]` if present in the config (l. 188–201).
9. **Template writers.** `put_point_scan_data_field_in_template()` writes `scan_startN[scan_start_approach|retrace]` and `scan_endN[...]` (l. 340–367); `put_point_force_scan_field_in_template()` writes `scan_pointsN[scan_points_approach|retrace]` (l. 369–377).

## Special behaviour

1. **Extend and retract columns** end in `_Ex` / `_Rt`; the unit is part of the name (parser l. 20–39).
2. **Metadata before the first section marker** is stored without a section prefix (`current_section is None`, parser l. 113).
3. **Repeated sections** are disambiguated by the counter (parser l. 73–75).
4. **Column-count mismatch** logs an error and stops reading (`break`, parser l. 96–102); arrays collected so far are kept.
5. **Ramp keys are hard-coded** in the formatter: `/Calc_Ramp_Ex_nm` and `/Calc_Ramp_Rt_nm` (formatter l. 237, 251), not config-driven.
6. **Offsets** are taken as given from the config, no unit conversion (formatter l. 220–234).
7. **Point-force fields are written unconditionally.** If a ramp is missing, `None` start/end values and units are written (formatter l. 352–367); the same for points (l. 372–377).
8. **Scan control type** is replaced in `__init__` after `super().__init__()` (formatter l. 98); `z_points`, `z_offset` fields are unused here (l. 48, 53–54).
9. **Any `.txt` is routed here** when `experiment_technique: AFM` (docs).

## Behaviour to investigate

1. **Truncation on mismatch.** After `break` (parser l. 102), `array_names` (l. 122) can be longer than the filled columns; arrays are shorter than the ramp and only an error is logged. Check that the formatter fails or flags it.
2. **Encoding.** The file is opened as `utf-8` (parser l. 56); a NanoScope export with `µ`/`°` in a single-byte code page raises `UnicodeDecodeError`. The `.flt` and `.spm` parsers use `latin-1`.
3. **Whitespace splitting.** Data rows and column names use `.split()` (parser l. 93, 122) although the docs describe tab-separated columns; names or values with spaces would split.
4. **Unit from name.** `Defl_Ex` (no unit token) returns `Defl` as the unit (parser l. 36–38); a quantity name containing a standalone `Ex` or `Rt` token is misread; units are not validated.
5. **Unit key naming.** `…/unit` (parser l. 156, 171) vs `…/@unit` in FLT/SPM; configs cannot be shared across Bruker formats.
6. **Regex gaps.** The scaled pattern `[\d.]+` (parser l. 152) rejects negatives and exponents; `(\w+)` rejects `nm/V`; the bracket pattern `(\w+)$` (l. 160) rejects multi-word values such as `S [Z] "Height Sensor"`, which stay raw strings.
7. **Header detection** needs a `:`-free line directly after the end marker (parser l. 81–88); a column header containing `:` is read as a key/value line.
8. **Colon heuristic for data rows** (parser l. 92): any data line containing `:` is skipped as a row.
9. **Step size convention.** `R/(N-1)` here (formatter l. 310, 320) vs `R/N` in the FLT and SPM formatters. Document which is intended for a point-force curve.
10. **Point-count parsing.** `int(parts[0])` (formatter l. 296–300) raises `ValueError` outside the `try` block (l. 307–330) for non-integer text.
11. **Count vs array length.** `Samps/line` is never compared with `len(/Calc_Ramp_Ex_nm)` or `len(/Calc_Ramp_Rt_nm)`.
12. **Amplitude setpoint.** Silent if `reference_amplitude` or the ratio is `None` (formatter l. 161); no else branch.
13. **Timestamp locale.** `%p`, `%a`, `%b` in `strptime` (formatter l. 127) are locale-dependent; the FLT formatter avoids this with an explicit month table (`bruker_flt_afm.py` l. 48–63). A failed parse only logs a warning (l. 134–138).
14. **`None` writes** (see special behaviour 7): check how the template validator treats `scan_start*` / `scan_points*` with value `None`.
15. **Dispatch by extension.** Any `.txt` is treated as a force-curve export.

## Scanner findings

No scanner run was performed for `pynxtools-spm`.
