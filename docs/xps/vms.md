# VAMAS ISO parser (`vms`)

Source folder: `pynxtools_xps/parsers/vms/` (`parser.py`, `data_model.py`, `data_model_casa.py`, `metadata.py`, `comment_handler.py`). Line numbers refer to `parser.py` unless a file is named.

The axis comes from the abscissa fields of each VAMAS block. Binding-energy axes are reversed by label. A CasaXPS calibration found in block comments can shift the axis. A kinetic-to-binding conversion exists in the data model, but no caller was found.

## At a glance

| | |
|---|---|
| **Input format** | VAMAS files, ISO 14976 (`.vms`, `.npl`), in regular and irregular format. The documentation site additionally lists `.txt` for VAMAS (CasaXPS text exports). |
| **URL (source code)** | [vms](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/vms/) |
| **Documentation** | [VAMAS ISO standard (VMS)](https://fairmat-nfdi.github.io/pynxtools-xps/reference/vms.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/vms/metadata.py), [config_vms.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_vms.json) |

**Standard behaviour.** Reads VAMAS blocks and builds the energy axis by scan mode: REGULAR from `abscissa_start`, `abscissa_step` and `num`; IRREGULAR from the interleaved abscissa values in the data; MAPPING handled separately (empty stub). Data is stacked in file order from the first scan's axis into `(1, n_scans, n_energy)` (`y_cps`) and `(1, n_scans, 1, n_energy)` (raw counts). Header fields are mapped (`source_energy`→`excitation_energy`, `resolution`→`pass_energy`, `abscissa_label`→`energy_label`, `abscissa_start`→`start_energy`) with eV units.

**Special behaviour.**

- The default axis label is `"kinetic energy"`. Conversion to binding energy (`x = source_energy − x`, `abscissa_start` reset) is available, but no call site is visible in this folder.
- Binding axes are reversed with `np.flip` when the label is exactly `"binding energy"`.
- CasaXPS energy calibrations from the block's comments shift `x` after parsing (BE: `x − offset`; KE: `x + offset`), only for operation `"ADD"`; range calibration is a TODO.
- Axis and metadata come from the first scan (sorted by `scan_no`); cycle and channel dimensions have length 1.

## Formula / transformation

**Step 1: choose the axis builder by scan mode (l. 420-425)**

```
REGULAR   -> _add_regular_data(block)
IRREGULAR -> _add_irregular_data(block)
MAPPING   -> _add_mapping_data(block)       (empty body, see below)
```

**Step 2: regularly spaced axis (`_add_regular_data`, l. 431-439)**

```
num = int(num_ord_values / no_variables)                 (l. 433)
E_i = round(start + i · step, 2),   i = 0 … num−1        (l. 434)
if abscissa_label == "binding energy":  E = np.flip(E)   (l. 436-437)
```

`start` is `block.abscissa_start` and `step` is `block.abscissa_step` (l. 431-432). The axis is stored as `block.x` (l. 439).

**Step 3: intensities, regular mode (l. 447-459)**

```
y_var = data_array[var :: no_variables],   var = 0 … no_variables−1
names: "y", "y1", "y2", …
```

- The ordinate values are interleaved by variable, so every `no_variables`-th value belongs to one variable.
- `self.lines` is consumed by `num_ord_values` entries (l. 449).
- The intensities are not reversed here, although `x` was.
- The first `for var` loop (l. 441-445) only sets `name` and does nothing else.
- Example (my own numbers): `start = 280.0`, `step = 0.1`, `num = 4` gives `x = [280.0, 280.1, 280.2, 280.3]`. With a binding label it becomes `[280.3, 280.2, 280.1, 280.0]` while `y` stays in file order, so the value stored for 280.0 now sits at 280.3 (if the file is ordered by ascending abscissa).

**Step 4: irregular axis (`_add_irregular_data`, l. 465-473)**

```
E = block_data[:: no_variables + 1]                      (l. 467)
if abscissa_label == "binding energy":  E = np.flip(E)   (l. 468-469)
abscissa_start = min(E);  abscissa_step = _get_minimal_step(E)    (l. 472-473)
```

The abscissa is interleaved with the variables, one energy value for every `no_variables` ordinates. The loop that extracts the ordinates starts at l. 475 and was not inspected, so it is unknown whether `y` is flipped there.

**Step 5: kinetic to binding conversion (`data_model.py`, `convert_to_binding_energy_scale`, l. 144-153)**

```
abscissa_label = "binding energy"            (l. 150)
x = source_energy − x                         (l. 152)
abscissa_start = float(min(x))                (l. 153)
```

- The array order is unchanged, so an ascending KE axis becomes a descending BE axis and the data stay aligned.
- No work function is subtracted.
- A TODO at l. 145 says "check that components are also converted".
- The default label is `"kinetic energy"` (l. 112). No call to this method appears in any grep hit for this folder.

**Step 6: parse a CasaXPS calibration (`data_model_casa.py` l. 305-333)**

```
measured_energies = [float(raw_measured)]                  single value (l. 306)
                  = [float(e) for e in raw_measured.split(",")]   list, range_calibration = True (l. 309-310)
aligned_energy    = float(split_line[aligned_index + 2])    (l. 312)
operation         = split_line[8];  energy_type = _convert_energy_type(split_line[7])   (l. 315, 325)
if operation == "ADD":
    energy_offset = min(measured_energies) − aligned_energy   (l. 319)
    operation = "addition"                                    (l. 320)
```

For any other operation `energy_offset` stays `None` (l. 316).

**Step 7: apply the calibration (`apply_energy_shift`, `data_model_casa.py` l. 498-507; `parser.py` l. 589-600)**

```
if operation == "addition":
    BE:  return x − energy_offset      (l. 500-501)
    KE:  return x + energy_offset      (l. 503-504)
if range_calibration:  pass  # TODO    (l. 506-507)
```

`parser.py` calls `block.x = energy_calibration.apply_energy_shift(block.x)` for each calibration found in the block's own comments (l. 589-597), then calculates the background with the shifted `x` (l. 599-600).

Example (my own numbers): `measured = 285.4`, `aligned = 284.8` gives `offset = 0.6`. A BE axis is shifted by −0.6 eV, so a peak at 285.4 moves to 284.8.

**Step 8: output arrays (`_assemble_entry`, l. 126-150)**

```
scans sorted by scan_no (default 0)                                  (l. 126)
x = axis of the first sorted scan                                    (l. 128)
data: np.stack(y_cps per scan) -> (n_scans, n_energy) -> [np.newaxis]  = (1, n_scans, n_energy)       (l. 131-137)
raw:  np.stack(y per scan)     -> (n_scans, n_energy) -> [np.newaxis, :, np.newaxis, :] = (1, n_scans, 1, n_energy)   (l. 141-147)
metadata = _filter_metadata(first sorted scan)                       (l. 150)
```

Dimensions are `("cycle", "scan", "energy")` and `("cycle", "scan", "channel", "energy")`.

`y_cps` is calculated in `_build_list` (l. 672): `[np.round(y / block.dwell_time, 2) for y in block.y]`. This is the counts-per-second intensity, **rounded to 2 decimals**.

**Step 9: header metadata (`metadata.py`)**

```
source_energy  -> excitation_energy   (l. 62)
analyzer_mode  -> energy_scan_mode    (l. 63, converter l. 88)
resolution     -> pass_energy         (l. 64)
abscissa_label -> energy_label        (l. 66, converter _convert_energy_type l. 87)
abscissa_units -> energy_units        (l. 67)
abscissa_start -> start_energy        (l. 68)
```

Units are `"eV"` for excitation energy, sputter source energy, work function, pass energy and start energy (`metadata.py` l. 96-125).

## Special behaviour

1. **Three scan modes (l. 420-425).** `MAPPING` calls `_add_mapping_data`, which has an empty body (`pass`, l. 492), so mapping blocks get no axis or data.
2. **Kinetic is the default; conversion on request (`data_model.py` l. 112, 144-153).** The conversion changes the label, `x` and `abscissa_start` together.
3. **Binding axes are reversed by label (l. 436-437, 468-469).** The check is an exact string match on `"binding energy"`.
4. **CasaXPS calibration is applied per block (l. 589-597).** Calibrations come from the block's own comment lines and are applied in order. Only `"ADD"` is handled; range calibration is a TODO. `CasaProcess.process_smoothing` is also an empty stub (`data_model_casa.py` l. 367).
5. **Background offsets use a percentage (`data_model_casa.py` l. 138-139).** `start_offset / 100.0` and `end_offset / 100.0` scale the first and last `y` values.
6. **Axis and metadata from the first scan only (l. 126-128, 150).** Scans are sorted by `scan_no` first; later scans' axes and metadata are ignored.
7. **Single cycle, single channel (l. 131-147).** Both dimensions have length 1.
8. **Ion-spectroscopy names (l. 286-295; `metadata.py` l. 47-52).** `"FABMS/SIMS/SNMS energy spec"` appear in lists and `source_energy` is read from the next line (l. 295). What the lists do was not inspected.
9. **Kratos comments.** Kratos metadata is parsed from VAMAS comments by `comment_handler.py` (see [kratos.md](kratos.md)).
10. **Fallback date (l. 625-639).** If the date cannot be built, `0001-01-01 00:00:00` with a constructed time zone is used.

## Behaviour to investigate

- **Axis flipped but not the data (l. 436-437, 447-459):** for binding-energy blocks `x` is reversed while `y` stays in file order. In the irregular case (l. 467-469) the `y` extraction is not visible. Check with a known peak. The grep pattern did not include "flip", so a flip of `y` elsewhere would not have shown up.
- **`apply_energy_shift` can return `None` (`data_model_casa.py` l. 498-507):** if the operation isn't `"ADD"`, or the energy type is neither binding nor kinetic, no branch returns a value, so `block.x` becomes `None` (`parser.py` l. 597). For `ADD` with a range calibration the first branch returns early, so the range TODO is never reached and the range is treated as a simple shift by `min(measured)`.
- **KE sign convention (`data_model_casa.py` l. 503-504):** `x + offset` is correct only if `measured` and `aligned` are binding energies. If they are on the KE scale the sign would be wrong.
- **Work function ignored (`data_model.py` l. 152):** `source_energy − x` has no φ, although `work_function` is parsed (`parser.py` l. 324).
- **No visible caller for `convert_to_binding_energy_scale`:** find where it is called, or whether KE data are ever converted.
- **Rounding to 2 decimals (l. 434, 672):** a step below 0.01 eV, or 0.025 eV, gives repeated or inexact energy values; `y_cps` is rounded the same way. `_get_minimal_step` also rounds to 2 decimals (`numerics.py` l. 105), assuming it is the function imported here.
- **Exact label match (l. 436, 468):** other spellings are treated as kinetic. The scanner counts 59 exact string comparisons in this file.
- **`abscissa_start = min(E)` (l. 472; `data_model.py` l. 153):** for a binding axis this is the lowest value, not the first element, so it may not equal the start energy in the file.
- **`resolution` mapped to `pass_energy` in eV (`metadata.py` l. 64, 119):** in retarding-ratio mode this is a ratio.
- **Mapping blocks (l. 492):** confirm what happens for a file with `MAPPING` scan mode.
- **Copied docstring (l. 462):** says "regularly spaced" for the irregular case.

## Scanner findings

- **Medium:**
  - rounding to 2 decimals (`parser.py` l. 434, 672);
  - `np.flip` of the axis (l. 437, 469);
  - empty stubs `_add_mapping_data` (l. 492) and `process_smoothing` (`data_model_casa.py` l. 367);
  - time-zone handling and the `0001-01-01` sentinel date (l. 625-639);
  - `matches_file` swallows `Exception` (l. 83);
  - ambiguous unit `"C"` for `particle_charge` and `sputter_ion_charge` (`metadata.py` l. 98, 104);
  - unit with trailing whitespace `"degree "` (`metadata.py` l. 122);
  - scale factor `100.0` (`data_model_casa.py` l. 138-139).
- **Config:** 16 medium hits in `config_vms.json` are fallback chains (e.g. `['@attrs:energy_units', 'eV']`), a scanner false positive. One of them, `pass_energy/@units` (l. 136), has no literal fallback.
- **Low/info:** 59 exact string comparisons, 5 TODO markers, `int(float(...))` or `split('.')[0]` truncations (2).

## Not verified

- The `y` extraction in `_add_irregular_data` (after l. 475), and the full `_add_mapping_data` context.
- Where `abscissa_start`, `abscissa_step` and `source_energy` are read, and whether anything outside this folder flips `y`.
