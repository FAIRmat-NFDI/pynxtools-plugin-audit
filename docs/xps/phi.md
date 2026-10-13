# PHI Electronics parser

Source folder: `pynxtools_xps/parsers/phi/` (`parser.py`, `metadata.py`, `data_model.py`). Line numbers refer to `parser.py` unless a file is named.

The axis is built from the start, stop and step values in the region definition string. The energy type and units are hard-coded to binding energy and eV.

## At a glance

| | |
|---|---|
| **Input format** | PHI Electronics `.spe` (single spectra) and `.pro` (sputter profile / external parameter scan) files from PHI Electronics VersaProbe 4 instruments. |
| **URL (source code)** | [phi](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/phi/) |
| **Documentation** | [Data from PHI instruments](https://fairmat-nfdi.github.io/pynxtools-xps/reference/phi.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/phi/metadata.py), [config_phi.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_phi.json) |

**Standard behaviour.** Reads PHI region definition strings by position (`spectrum_type`, `n_values`, `step`, `start`, `stop`, dwell time in s, pass energy in eV) and builds the energy axis from start/stop/step (not read directly). The energy type is set to `"binding"` and units to eV. All scans of a region are stacked in file order into `(1, n_scans, n_energy)`, dims `(cycle, scan, energy)`. Header fields are mapped to parser-internal metadata keys (these are not NeXus names; the NeXus fields are set in the config_*.json files) (`analyser_work_fcn`→`analyzer_work_function`, `energy_recal`→`energy_recalibration`, `analyser_mode`→`energy_scan_mode`, `neutralizer_energy`→`flood_gun_energy`, `energy_reference`→peak + energy in eV).

**Special behaviour.**

- Energy type `"binding"`, energy units `"eV"` and dwell-time unit `"s"` are hard-coded (`parser.py` l. 315-318), not read from the file.
- The step is negated before use (l. 311) and the axis is reversed with `np.flip` (l. 320). `n_values` is read but not passed to the axis function.
- Scans are stacked as is, with no sum, mean or flip of intensities; the cycle dimension is always length 1.
- Header lines are matched in order against the first remaining line only (l. 295-305). `energy_reference` and `energy_recalibration` are stored as metadata but not applied to the axis. `"energy"` and `"data"` are excluded from metadata (l. 55).

## Formula / transformation

**Step 1: parse the region definition string (l. 308-318)**

```
def_split     = region_definition.split(" ")
spectrum_type = def_split[2]
n_values      = int(def_split[4])
step          = −float(def_split[5])
start         = float(def_split[6])
stop          = float(def_split[7])
dwell_time    = float(def_split[-3])     (units "s", hard-coded)
pass_energy   = float(def_split[-2])
energy_type   = "binding";  energy_units = "eV"     (hard-coded)
```

- All values are read by position in a space-separated string. The middle fields are counted from the start (indices 2-7), the last two from the end (indices −3 and −2).
- The step from the file is multiplied by −1 (l. 311).
- The energy type is `"binding"` for every region in the lines inspected (l. 317). This overrides the data-model default `"kinetic"` (`data_model.py` l. 356).

**Step 2: energy axis (l. 320)**

```
energy = np.flip( safe_arange_with_edges(stop, start, step) )
```

- `safe_arange_with_edges` is imported from `pynxtools_xps/numerics` (l. 30). Its body was not inspected, so it is unknown whether it includes both end points or how it handles floating-point rounding.
- The arguments are passed as `(stop, start, step)` with a negated step, then the result is reversed. The final direction depends on the sign convention in the file and on the function's signature; it cannot be stated from the code seen.
- No `hν − KE` and no work function is applied. The axis comes only from the file's start, stop and step.
- `n_values` (l. 310) is read but not passed to the axis function, so the axis length comes from `start`, `stop` and `step`.
- `region.validate_types()` runs afterwards (l. 322); its body was not inspected.

**Step 3: stack the scans (`_assemble_entry`, l. 129-134)**

```
energy_array = np.array(spectrum_dict["energy"])                              (l. 129)
scan_arrays  = np.array([np.array(v) for v in spectrum_dict["data"].values()]) (l. 131)   -> (n_scans, n_energy)
data         = scan_arrays[np.newaxis, ...]                                    (l. 134)   -> (1, n_scans, n_energy)
```

- Every scan in `spectrum_dict["data"]` becomes one row, in the dict's insertion order.
- No sum, mean, reshape, transpose or flip of the intensity data.
- `np.array` over a list of arrays requires every scan to have the same length.
- Example (my own numbers): 3 scans of 101 points give shape `(1, 3, 101)`.

**Step 4: output array (l. 133-137)**

```
dims   = ("cycle", "scan", "energy")
coords = {"energy": energy_array}
```

The comment at l. 132 states that there is a single cycle, so the first dimension is always length 1.

**Step 5: entry name and metadata (l. 114-123, 139-140)**

```
entry_name = _construct_entry_name([group_name, spectrum_type]) or "entry"
metadata   = self._filter_metadata(spectrum_dict)
```

The metadata filter excludes the keys `"energy"` and `"data"` (l. 55).

**Step 6: header metadata (`metadata.py`)**

```
analyser_work_fcn  -> analyzer_work_function        (l. 141)
energy_recal       -> energy_recalibration          (l. 148, converted by _convert_bool l. 217)
analyser_mode      -> energy_scan_mode              (l. 161, converted by _convert_energy_scan_mode l. 230)
neutralizer_energy -> flood_gun_energy              (l. 192)
energy_reference   -> _convert_energy_referencing   (l. 215)
```

- `_convert_energy_referencing` (`metadata.py` l. 71-74) splits `"<peak> <energy>"` on a space and returns `{"peak": ..., "energy": float, "energy_units": "eV"}`. A second converter at l. 85-90 splits `"<label> <energy> <mono>"` the same way.
- Data-model defaults: `analyzer_work_function = 0.0` eV (`data_model.py` l. 47-48), `energy_recalibration = False` (l. 63).

## Special behaviour

1. **Binding energy and eV are hard-coded (l. 317-318).** Nothing in the lines inspected checks the file for the energy type.
2. **Dwell time unit is hard-coded to seconds (l. 315).**
3. **Metadata lines are matched in order (l. 295-305).** For each region the code checks only the first remaining line `spectral_defs[0]` against each `file_key`. On a match it sets the attribute from `split(" ", 1)[1]` and removes that line. If a key is absent from the file, the lines after it no longer match, because the loop only looks at the first line.
4. **`full_region` is reset to `False` for every region (l. 300).**
5. **Energy reference and recalibration are metadata only.** `energy_reference` and `energy_recalibration` (`data_model.py` l. 45, 63) are stored, but nothing inspected shows either shifting the axis.
6. **Single cycle (l. 132-134).** The output always has a cycle dimension of length 1.
7. **Many instrument fields are only parsed.** Sputter, neutralizer, flood-gun, SXI and GCIB energies (`data_model.py` l. 85-332) are stored with eV units and are not used in any axis calculation.

## Behaviour to investigate

- **Hard-coded `"binding"` (l. 317):** kinetic-energy PHI files would be labelled as binding energy.
- **Negated step and argument order (l. 311, 320):** print `start`, `stop`, `step` and the final axis for a real file. Check the direction and that the first and last values match `start` and `stop`.
- **Flip on the axis only (l. 320 and 131-134):** the intensities are used in file order. Confirm that the file's data order matches the flipped axis, using a known peak.
- **`n_values` unused (l. 310):** check `len(energy) == n_values`. The axis function's end-point handling or rounding could give a different count, which would fail at `np.stack` or on the coordinate assignment.
- **Position-based parsing (l. 309-318):** a change in the definition string layout gives silently wrong values or an error. Pass energy (`def_split[-2]`) and dwell time (`def_split[-3]`) depend on the token count.
- **Order-dependent metadata matching (l. 295-305):** a missing key shifts which lines get matched. Check files with optional fields absent.
- **Energy reference and recalibration not applied:** confirm the axis in the file is already referenced.
- **Work function unused:** `analyzer_work_function` is parsed (`metadata.py` l. 141) but not used in any conversion.
- **Energy reference string split (`metadata.py` l. 73):** `value.split(" ")` raises `ValueError` if there are more or fewer than two parts, for example a peak name containing a space.
- **Ragged scans (l. 131):** scans of unequal length give an object array in some NumPy versions or a `ValueError` in newer ones.

## Scanner findings

- **Medium:** `np.flip` on the axis (l. 320); `matches_file` swallows `Exception` (l. 79).
- **Low/info:** `or 'entry'` fallback (l. 115); zero-filled array default (`data_model.py` l. 351); 2 reductions; 7 hits for keys spelled differently.

## Not verified

- The bodies of `safe_arange_with_edges` and `validate_types`.
- How `region_definition` and `spectrum_dict["data"]` are produced, and the signature the `(stop, start, step)` call maps to.
- The file format specification for the region definition fields.
