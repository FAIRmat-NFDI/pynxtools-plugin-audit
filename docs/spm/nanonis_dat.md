# Nanonis STS `.dat` parser (`pynxtools-spm`)

Source files reviewed:

- `pynxtools_spm/parsers/nanonis_dat_generic.py` — the nanonis_dat parser defining `DatGenericNanonis`.
- `pynxtools_spm/nxformatters/nanonis/nanonis_dat_sts.py` — the STS formatter, `NanonisDatSTS`.

**Line-number note:** References below refer to the main branch on 13th October 2026.

## At a glance

| | |
|---|---|
| **Input format** | Nanonis `.dat`, STS/bias spectroscopy |
| **Parser class** | `DatGenericNanonis(SPMBase)` (nanonis_dat parser, l. 55–76) |
| **Formatter class** | `NanonisDatSTS(NanonisBase)` (`nanonis_dat_sts.py`, l. 50–54) |
| **Raw-data storage** | Nested dictionary `bias_spect_dict` (nanonis_dat parser, l. 68–75) |
| **Output from parser** | Flattened dictionary with slash-separated paths (nanonis_dat parser, l. 271–277) |
| **Formatted output** | NeXus template; the formatter describes STS data for `NXstm` (`nanonis_dat_sts.py`, l. 1–4, 86–89) |
| **Project context** | `pynxtools-spm` supports multiple SPM vendors/formats; this document focuses on the Nanonis STS `.dat` path. See the [project repository](https://github.com/FAIRmat-NFDI/pynxtools-spm/). |

**Standard behaviour.** The nanonis_dat parser reads a Nanonis `.dat` file, separates metadata from numeric matrix rows, extracts units from headers, splits the matrix into per-column arrays, stores the results in a nested dictionary, and flattens nested paths in `parse()` (nanonis_dat parser, l. 206–269 and 271–277). The STS formatter maps configured fields into a NeXus template, constructs bias-sweep metadata, applies a current sign factor where current and voltage are detected, and can create a differential-conductance group (`nanonis_dat_sts.py`, l. 86–89, 100–142, 183–204, 308–340).

**Comparison with other `pynxtools-spm` parsers.** This path is a spectroscopy parser: its distinctive outputs include a bias sweep and derived `dI/dV`. The project also handles image/channel-oriented formats such as `.sxm`, `.sm4`, and `.flt`; those formats have different file layouts and may represent spatial images or individual channels rather than a bias-sweep matrix.

## Formula / transformation

### Generic parser: matrix layout, not a physical transformation

**Step 1: identify numeric rows** (nanonis_dat parser, l. 159–184)

```python
wd_list = line_to_analyse.split()
# each token is tested with float(word)
return True, int_list  # only if every token is numeric
```

A row is accepted only if every whitespace-separated token converts to `float`. This detects numeric rows; it does not identify which column is voltage or current.

**Step 2: flatten accumulated values into a matrix** (nanonis_dat parser, l. 213–238)

```python
column_keys = column_string.split("\t")
np_2d_array = one_d_np_array.reshape(-1, len(column_keys))
```

If the header has `M` columns, the accumulated flat array is reshaped into `M` columns. This is a layout transformation, not a change in measured values.

**Step 3: store each column by name** (nanonis_dat parser, l. 220–238)

Headers containing parentheses are parsed into a key and unit by `check_metadata_and_unit()` (l. 186–204). Values are stored as `np_2d_array[:, ind]`; extra bracket metadata such as `filt` is preserved (l. 221–234). Headers without parentheses are stored as lists without a unit (l. 236–238).


### STS formatter: bias step-size calculation

**Location:** `nanonis_dat_sts.py`, `_construct_linear_sweep_grp()`, l. 119–137.

```python
self.bias_sweep.scan_size_bias = (
    self.bias_sweep.scan_end_bias - self.bias_sweep.scan_start_bias
) / self.bias_sweep.scan_points_bias
```

Formula:

\[
\Delta V_{\mathrm{bias}} =
\frac{V_{\mathrm{end}}-V_{\mathrm{start}}}{N}
\]

where `scan_start_bias` and `scan_end_bias` are the sweep endpoints and `scan_points_bias` is the point count (l. 122–129). The result is written as `step_size_bias` with units at l. 132–137.

**Detail to investigate:** the code divides by the number of points, `N`, rather than `N - 1`. If both endpoints are included in `N` evenly spaced samples, there are normally `N - 1` intervals. Confirm the instrument convention and the intended meaning of `scan_points_bias` before changing this.

### STS formatter: current sign transformation

**Location:** `nanonis_dat_sts.py`, `_nxdata_grp_from_conf_description()`, l. 308–338; multiplication at l. 332.

```python
flip_number = self.TmpConceptsVal.flip_number or 1
...
self.template[current_field] = flip_number * value
```

Formula:

\[
I_{\mathrm{formatted}} = f_{\mathrm{flip}} I_{\mathrm{raw}}
\]

The formatter tries to obtain `flip_number` from an ELN key ending in `flip_sign` (l. 312–320), and defaults to `1` when the expression at l. 323 evaluates to a falsy value. A factor of `-1` reverses the current sign; `+1` leaves it unchanged.


### STS formatter: differential conductance

**Location:** `nanonis_dat_sts.py`, `_construct_di_dv_grp()`, l. 207–242.

```python
di_by_dv = cal_dy_by_dx(
    iv_dict["current_fld"], iv_dict["voltage_fld"]
)
```

The intended derived quantity is differential conductance:

\[
\frac{dI}{dV}
\]

`cal_dy_by_dx` is imported from `pynxtools_spm.nxformatters.helpers` (l. 40–44 ). It is calculated numerically using a second-order-accurate finite-difference method, implemented as Diff(axis=0, grid=V, acc=2) (helpers.py, lines 489–492) and the actual voltage values are used as the differentiation grid.

The formatter checks that the derivative, current, and voltage arrays have matching shapes (l. 213–218), then writes `dI_by_dV` to the template (l. 219–240). It constructs the derived group only if the formatter detects both current and voltage (l. 276–308, 329–338).

Because the current is multiplied by `flip_number` at l. 332 before `_construct_di_dv_grp()` is called at l. 338, the derivative in this execution path is based on the sign-adjusted current.

## Standard behaviour

1. **Initialization and extraction.** `DatGenericNanonis.__init__()` initializes `bias_spect_dict`, stores the filename, and calls `extract_and_store_from_dat_file()` (nanonis_dat parser, l. 68–75).
2. **Metadata hierarchy.** `retrieve_key_recursively()` splits paths using `>` and tab separators and builds nested dictionaries (nanonis_dat parser, l. 113–157; separators set at l. 209).
3. **Units and column metadata.** `check_metadata_and_unit()` separates a header into name, unit, and optional bracket metadata (nanonis_dat parser, l. 186–204). Matrix headers are processed by the nested `dismantle_matrix_into_dict_key_value_list()` function (l. 213–238).
4. **Numeric block detection.** `check_matrix_data_block_has_started()` accepts a line only when every whitespace-separated token parses as a float (nanonis_dat parser, l. 159–184).
5. **Nested dictionary to flattened paths.** `parse()` calls `nested_path_to_slash_separated_path()` and returns the flattened dictionary (nanonis_dat parser, l. 271–277).
6. **Configuration-driven NeXus formatting.** `get_nxformatted_template()` walks the config, formats ELN values, and handles special fields (formatter, l. 86–89).
7. **Bias sweep.** `_construct_bias_sweep_grp()` constructs `scan_region` and `linear_sweep` groups (formatter, l. 183–204).
8. **Derived conductance.** If current and voltage are both found and the data are valid, the formatter creates `dI_by_dV` (formatter, l. 207–242 and 276–340).

## Special behaviour

1. **Header-to-matrix association relies on the preceding line.** When a numeric block starts, the parser uses `last_line` as the matrix header (nanonis_dat parser, l. 248–258). The file format must place the relevant column header immediately before the numeric rows.
2. **The parser accumulates the matrix as one flat array.** All numeric rows are appended with `np.append` (nanonis_dat parser, l. 248–252), then reshaped based on the number of tab-separated header fields (l. 216–217).
3. **Header units are optional in the implementation.** Columns with `(...)` get a parsed unit; columns without parentheses are stored as lists without a unit (nanonis_dat parser, l. 221–238).
4. **Bracket labels are retained as metadata.** For a header like `Current (A) [filt]`, the code stores a field like `Current [filt]`, unit `A`, and metadata `filt` (nanonis_dat parser, l. 199–204 and 221–228).
5. **Current sign correction belongs to the formatter, not the raw parser.** It is applied by multiplying the current field by `flip_number` (formatter, l. 312–332).
6. **The derivative helper is external to the reviewed files.** `cal_dy_by_dx()` is imported (formatter, l. 40–44) and called at l. 210.
7. **The formatter is config-driven and inherits behaviour.** It invokes `walk_though_config_nested_dict()` and parent methods (formatter, l. 86–89 and 253–260).
8. **`_construct_nxscan_controllers()` is a stub.** It contains only `pass` (formatter, l. 91–98), so this method adds no controller content itself in this class.
9. **The parser is one path in a multi-format project.** `pynxtools-spm` also supports `.sxm`, `.sm4`, and `.flt`; do not assume this `.dat` matrix logic applies to image/channel parsers.

## Behaviour to investigate


1. **Matrix parsing and data loss:** Check accumulator resets, malformed rows, and block boundaries.
2. **Header and data-shape consistency:** Verify column counts and array reshaping.
3. **Unit and metadata parsing:** Test missing units, unusual headers, and Boolean mapping.
4. **Bias-step formula:** Verify whether the denominator should be `N` or `N − 1`.
5. **Current sign correction:** Check zero, missing, duplicate, or invalid sign values.
6. **Derived dI/dV output:** Test numerical differentiation with invalid or problematic voltage/current data and check for silent failures.

## Scanner findings

No scanner run was perform for `pynxtools-spm`.

