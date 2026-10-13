# SPECS XY parser

Source folder: `pynxtools_xps/parsers/specs/xy/` (`parser.py`, `metadata.py`). Line numbers refer to `parser.py` unless a file is named.

This parser has **no energy formula**. The axis is read from the file and passed through unchanged.

## At a glance

| | |
|---|---|
| **Input format** | SpecsLabProdigy export format (`.xy`), including all export settings. |
| **URL (source code)** | [specs/xy](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/specs/xy/) |
| **Documentation** | [Data from SPECS instruments](https://fairmat-nfdi.github.io/pynxtools-xps/reference/specs.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/specs/xy/metadata.py), [config_specs_xy.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_specs_xy.json) |

**Standard behaviour.** Reads the energy axis directly from the first data column of the file (no computation). Scans are grouped by `loop_no` (cycle) and sorted by `scan_no`; intensities (2nd column) are stacked to `(n_cycles, n_scans, n_energy)` with dims `(cycle, scan, x_axis_name)`. Header fields are mapped to SPECS file keys (`ex_energy`→`excitation_energy`, `binding_energy`→`start_energy`, `eff._workfunction`→`work_function`, `scan_mode`, `energy_axis`→`x_units` for binding/kinetic type) with float conversion and eV units. Step size is measured from the axis if the spacing is uniform.

**Special behaviour.**

- No BE/KE conversion: the axis stays in the file's scale, with no flip. `excitation_energy` and `work_function` are parsed but not used in any calculation.
- One axis (from the first scan) for all cycles and scans. Metadata is taken from the first scan only.
- Other data columns are stored as `external_{name}` arrays `(n_cycles, n_scans, n_energy)`. The coordinate name is the first column's name, not necessarily `"energy"`.

## Formula / transformation

**Step 1: group and order scans (l. 255-258)**

```
cycles = scans grouped by loop_no;   within each cycle: sorted by scan_no
```

A missing `loop_no` or `scan_no` defaults to 0 (`s.get("loop_no", 0)`, `s.get("scan_no", 0)`). Cycles are processed in sorted key order (l. 256).

**Step 2: axis names from the first scan only (l. 261-264)**

```
x_axis_name = name of 1st data column   (default "energy")
y_axis_name = name of 2nd data column   (default "intensity")
```

Taken from `cycles_dict[cycle_keys[0]][0]["data"]`, the first scan of the first cycle. The names are whatever the file's column labels are, not fixed to `"energy"`.

**Step 3: energy axis (l. 266)**

```
energy_axis = np.array(first column of the first scan)
```

Not computed (no `linspace`, `arange`, start or step). One axis is used for all cycles and scans; later scans' axes are not compared with it.

**Step 4: intensity stacking (l. 268-275)**

```
per cycle:   np.stack([scan[y_axis_name] for each scan], axis=0)  ->  (n_scans, n_energy)
all cycles:  np.stack(cycle_arrays, axis=0)                       ->  (n_cycles, n_scans, n_energy)
```

No sum, mean, reshape or transpose, so every scan is kept. `np.stack` requires equal lengths, otherwise it raises `ValueError`.

**Step 5: output array (l. 280-284)**

```
dims   = ("cycle", "scan", x_axis_name)
coords = {x_axis_name: energy_axis}
```

The docstrings (l. 92, 124, 227) say `("cycle", "scan", "energy")`, but the code uses `x_axis_name`.

**Step 6: raw line parsing (l. 781-788)**

```
values = [float(v) for v in line.strip().split()]
data_channels[label].append(v)     for each (label, v) in zip(labels, values)
```

Each data line is split on whitespace and converted to floats. If `in_remote_channel` is true, column 0 (`i == 0`) is skipped. `data_channels` is a dict of lists, one list per column label.

**Step 7: step size (l. 790-793)**

```
if energy_axis and check_uniform_step_width(energy_axis):
    scan_settings["step_size"] = _get_minimal_step(energy_axis)
```

`energy_axis = data_channels.get("energy")` looks up the literal key `"energy"` (l. 790). The step is measured from the data and stored as metadata only; the axis is not rebuilt from it.

**Step 8: header metadata (`metadata.py`)**

```
energy_axis       -> x_units                   (l. 71), converted by _convert_energy_type (l. 101): binding / kinetic
ex_energy         -> excitation_energy         (l. 75)
binding_energy    -> start_energy              (l. 83)
eff._workfunction -> work_function             (l. 84)
scan_mode         -> _convert_energy_scan_mode (l. 90)
```

Float conversion for `excitation_energy`, `kinetic_energy`, `work_function` and `pass_energy` (l. 93-99). Units are `"eV"` for `work_function`, `excitation_energy` and `pass_energy` (l. 111-113).

## Special behaviour

1. **No binding/kinetic conversion.** The axis stays in the scale of the file. `excitation_energy` and `work_function` are parsed into metadata but are not used in any calculation.
2. **No flip or reorder.** The axis direction is whatever the file contains.
3. **Metadata from the first scan only (l. 286-296).** Every key not in `self._metadata_exclude_keys` is copied from `primary_scans[0]`. `analysis_method` also gets a `_long_name` entry via `_get_measurement_method_long`.
4. **External channels (l. 298-300, 694-700).** Other data columns are stored as `external_{channel_name}` arrays with shape `(n_cycles, n_scans, n_energy)`. `_normalize_ext_channel_label` splits a label into a name and optional unit, e.g. `('excitation_energy_monochromator', 'eV')`; `"energy"` gives `('energy', None)`.
5. **Step size is optional (l. 792-793).** Set only if the axis exists and has uniform spacing.
6. **Scan record layout (l. 794-799).** Each scan returns an `OrderedDict` with `data` (the channel lists), `channel_units` and `scan_settings`.
7. **Export options with defaults (l. 215, 247, 301).** `x_units` defaults to `""`, `separate_channel_data` and `external_channel_data` to `False`, read from `self.export_settings`.

## Behaviour to investigate

- **Axis name vs `"energy"` (l. 263 vs 790):** dims and coords use the first column's name, but the step size looks up the literal key `"energy"`. If the first column has another name (e.g. `kinetic_energy`), `step_size` is never set.
- **Docstring mismatch (l. 92, 124, 227 vs 282):** the docs say the dim is `"energy"`, the code uses `x_axis_name`.
- **Intensity is the second column (l. 264):** whatever its name, so a different column order silently uses the wrong column.
- **Ragged data fails (l. 269-275):** `np.stack` needs the same number of points in every scan and the same scan count in every cycle, otherwise `ValueError`. A scan missing `y_axis_name` raises `KeyError`.
- **Axis taken from scan 0 only (l. 266):** later scans may have a different axis with no warning.
- **Silent truncation by `zip` (l. 784):** if a data line has more or fewer values than labels, extra values or labels are dropped.
- **Metadata from the first scan only (l. 286-296):** differences in later scans are ignored.
- **Work function and `start_energy` (`metadata.py` l. 83-84):** the work function is parsed but unused, and `start_energy` is set from a field called `binding_energy` regardless of the axis type.
- **Time zone (`metadata.py` l. 55, 63):** UTC is assumed or attached when parsing dates; check the local-time fallback at l. 63.

## Scanner findings

- **Medium:** UTC time zone assumed (`metadata.py` l. 55, 63); `matches_file` swallows `Exception` (`parser.py` l. 72); export-option defaults (`parser.py` l. 215, 247, 301).
- **Low/info:** silent `except ValueError` (`metadata.py` l. 61) and `except UnicodeDecodeError` (`parser.py` l. 346); 11 exact string comparisons; 5 `.get(..., default)` fallbacks.

## Not verified

- Bodies of `check_uniform_step_width`, `_get_minimal_step` and `_convert_energy_type`. Note that `_get_minimal_step` lives in `numerics.py` and rounds to 2 decimals (`numerics.py` l. 105).
- Where axis units and `_metadata_exclude_keys` are set, and how `in_remote_channel` and `normalized_labels_and_units` are built.
