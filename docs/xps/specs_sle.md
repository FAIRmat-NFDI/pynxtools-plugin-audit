# SPECS SLE parser

Source folder: `pynxtools_xps/parsers/specs/sle/` (`parser.py`, `metadata.py`). Line numbers refer to `parser.py` unless a file is named.

FAT stands for **Fixed Analyzer Transmission**, a scan mode of the electron energy analyser (the same as "constant analyser energy", CAE).

The raw axis is relative (`i · step_size`). In FAT mode, per-channel shifts are applied and the channels are resampled onto a common grid. The parser does not convert between binding and kinetic energy for the main axis.

## At a glance

| | |
|---|---|
| **Input format** | SpecsLabProdigy files from SPECS GmbH (`.sle`). The same plugin also reads SpecsLab 2 `.xml` and the `.xy` export (see [specs_xml.md](specs_xml.md) and [specs_xy.md](specs_xy.md)). |
| **URL (source code)** | [specs/sle](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/specs/sle/) |
| **Documentation** | [Data from SPECS instruments](https://fairmat-nfdi.github.io/pynxtools-xps/reference/specs.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/specs/sle/metadata.py), [config_specs_sle.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_specs_sle.json) |

**Standard behaviour.** Maps SPECS metadata to SPECS file keys (`Ebin`, `Ekin`, `Epass`, `Eexc`, `wf`) with eV units. Energy axis from start, step and number of points (BE: `start − i·step`; KE: `start + i·step`; `parser.py` l. 1077-1090; in my reading this branch is reached only when no axis is stored, see Step 8 below). Data is reshaped to `(n_energy, n_channels)` and stored as `(cycle, scan, energy)` or `(cycle, scan, channel, energy)`. Transmission-function KE axis: `KE = excitation_energy − BE`, with a flat transmission function of ones if absent.

**Special behaviour.**

- FAT mode only: each channel is shifted by `detector_shift·E_pass`, then linearly interpolated onto the common overlap grid (the output step can differ from `step_size`). Channels are summed (`np.sum`).
- The raw axis is relative (`i·step_size`). The BE axis is flipped with `np.flip`. `ValueError` if `step_size` or the energy axis information is missing.

## Formula / transformation

**Step 1: raw scan axis (`_get_one_scan`, `parser.py` l. 387-394)**

```
E_i = i · step_size,   i = 0 … N−1,   N = data.shape[0]
```

- `step_size` is read from `spectrum["step_size"]`. If it is `None`, the code raises `ValueError` (l. 388-393).
- The axis is relative: it starts at 0 and has no start energy.
- `data` comes from `_separate_channels`, which reshapes the flat array to `(n_energy, n_channels)` (`reshape(size // n_channels, n_channels)`, l. 646).

**Step 2: per-channel shifts, once per spectrum (l. 324-335)**

```
detector_shifts = [item["shift"] for key, item in detector_calib.items() if key.startswith("detector")]   (l. 326-330)
detector_calib["shifts"] = np.array(detector_shifts) · pass_energy                                         (l. 331-333)
```

- Each detector channel has a calibrated shift stored as a fraction of the pass energy. Multiplying by `pass_energy` (from `pass_energy_or_retardation_ratio`, l. 325) gives eV.
- If the pass energy or the calibration is missing, `except KeyError: pass` (l. 334-335) skips this silently and `shifts` is never set.
- `_apply_channel_shifts` reads the result at l. 429. If it is missing, axis and data come back unchanged (l. 430-431).

**Step 3: shifted axis per channel (l. 434-436)**

```
E_i,c = i · step_size + shift_c
```

`shifts[i]` is paired with channel `i` by list position. This assumes the detector key order matches the channel order.

**Step 4: common overlap grid (l. 438-440)**

```
xmin = max_c( min_i E_i,c )
xmax = min_c( max_i E_i,c )
E_calib,j = xmin + j · (xmax − xmin)/(num_values − 1),   j = 0 … num_values−1
```

Only the energy range covered by all channels is kept. `linspace` includes its endpoint, so the new step is `(xmax − xmin)/(num_values − 1)`. It equals `step_size` only if there are no shifts and `num_values == N`.

**Step 5: linear resampling (l. 442-444)**

```
I_c(E_calib) = interp1d(E_i,c, data[:, c], kind="linear")
```

Each channel is interpolated onto the common grid. Because of the overlap cut, nothing is extrapolated. The result is transposed (`.T`) back to `(n_energy, n_channels)`.

**Step 6: binding-energy orientation (l. 446-447)**

```
if energy/@type == "binding":  E_calib = np.flip(E_calib)
```

Only the axis is reversed. `data_interpolated` is not flipped.

**Step 7: merged signal (l. 405)**

```
merged_i = Σ_c data[i, c]      (np.sum, axis=1)
```

This is a sum, not a mean.

**Step 8: stored energy axis (l. 349-356, 358-363, 1062-1063)**

```
data["energy"] = energy of scan 0     (l. 352-353)
   = i · step_size                    non-FAT mode, or FAT without shifts
   = E_calib (overlap grid)           FAT mode with shifts
```

- Only the first scan's axis is stored. The other scans are checked only by `_check_scan_length(node_id, scan["energy"], abscissa_info)` (l. 354-356), which looks like a length check.
- `spectrum["abscissa_info"]` (l. 347) is used only for that check. It does not build the axis.
- If no scan produces an axis, the code raises `ValueError` (l. 358-363).
- `_get_energy_data` returns an existing stored axis as it is (l. 1062-1063).
- The start-energy formulas at l. 1077-1090 (BE: `BE_start − i·step`, KE: `KE_start + i·step`) are reached only when no stored axis exists. In this flow that case raises at l. 358-363 first, so that branch looks unreachable here unless the function is called from elsewhere.
- **Consequence:** nothing in the code inspected adds `binding_energy` or `kinetic_energy` (the start energy) to the stored axis.

**Step 9: transmission-function kinetic-energy axis (`_compute_tf_energy_axis`, l. 467-493)**

```
BE type:   KE = excitation_energy − energy      (l. 482-483)
otherwise: KE = energy                           (l. 485)
```

- The result is truncated to `n = min(len(KE), len(rel_intensity))` (l. 489-490) and stored as `transmission_function/kinetic_energy` (l. 493).
- It is skipped for `fixed_energy` mode (l. 475-476).
- If there is no transmission function, `np.ones(len(energy))` is used (l. 365-366).
- If `energy` is still the relative axis from Step 8, this subtraction gives wrong values, because it needs the absolute BE.

**Worked example (my own numbers, not from a file)**

- `step_size = 0.1`, `N = 5`, `E_pass = 20`, detector shifts `[0.0, 0.01]`.
- Shifts after Step 2: `[0.0, 0.2]` eV.
- Channel 0 axis `[0, 0.1, 0.2, 0.3, 0.4]`, channel 1 axis `[0.2, 0.3, 0.4, 0.5, 0.6]`.
- `xmin = 0.2`, `xmax = 0.4`: the common grid covers 0.2-0.4 eV only. Three of the five points of each channel survive.

## Special behaviour

1. **Shift correction only in FAT mode (l. 396-397).** The check is `spectrum["energy_scan_mode"] == "fixed_analyzer_transmission"`. In any other mode the raw relative axis and the unshifted channel data are used.
2. **Missing calibration is silent (l. 334-335, 429-431).** In FAT mode the channels are then left uncorrected, with no warning logged.
3. **One axis for all scans (l. 349-356).** The first scan sets `data["energy"]`; later scans are only length-checked.
4. **Output shapes (l. 197-198, 213-240).**
   - Channel-averaged signal: `(n_scans, n_energy)` becomes `(1, n_scans, n_energy)`, dims `("cycle", "scan", "energy")`.
   - Raw per-channel data: `(n_scans, n_energy, n_channels)` is transposed with `transpose(0, 2, 1)` (l. 236) to dims `("cycle", "scan", "channel", "energy")`.
   - Cycle is always length 1.
5. **Units (l. 315-316; `metadata.py` l. 128-142).** `energy/@units = "eV"` and `intensity/@units = "counts_per_second"` are hard-coded. `metadata.py` maps `work_function`, `excitation_energy`, `pass_energy`, `start_energy` and the transmission-function kinetic energy to `"eV"`.
6. **Work function (`metadata.py` l. 50).** `"wf"` is mapped to `work_function`, but nothing in the inspected code uses it in a conversion. The BE→KE relation at l. 483 is `hν − BE` with no φ.
7. **Possible `step_size` fallback (l. 892-897).** The comment "Last resort: derive from energy range and n_values" and the code (`start = binding_energy or kinetic_energy`, `end = end_energy`) suggest that `step_size` is derived from metadata when it is not stored. This matches `_get_one_scan` needing `step_size` (l. 388-393). The code was not read in full, so this is likely but not confirmed.
8. **Options read from kwargs (l. 139-140).** `remove_align` defaults to `True` and `sum_channels` to `False`. The code was not checked against the user documentation.

## Behaviour to investigate

- **Missing start energy (l. 352-353, 394):** the stored axis is relative. Confirm where, if anywhere, `binding_energy` or `kinetic_energy` is added, for example in the NeXus writer. This also affects the transmission-function axis (l. 483).
- **Flip on the axis only (l. 446-447):** for binding-energy scans the axis is reversed while the interpolated data is not, so spectra could be mirrored. Check whether the data is reversed elsewhere.
- **Silent skip of shifts (l. 334-335):** FAT-mode channels end up uncorrected without any message.
- **Channel-order assumption (l. 326-330, 435):** shifts are matched to channels by detector key order.
- **Step changes with shifts (l. 440):** the output step differs from `step_size` unless there are no shifts and `num_values == N`.
- **Axis from scan 0 only (l. 352-353):** later scans are not compared with it apart from the length check.
- **Work function unused (l. 483):** `KE = hν − BE` ignores φ.
- **Fabricated transmission function (l. 365-366):** `np.ones` stands in when no transmission function exists. Check that downstream code does not treat it as measured data.

## Scanner findings

- **High:** duplicate dict key `DeviceExcitationEnergy` (`metadata.py` l. 87 and 94); the second wins.
- **Medium:**
  - hard-coded units (`parser.py` l. 315-316);
  - `np.ones` constant array (l. 366);
  - `np.flip` on the axis (l. 447);
  - `matches_file` and other `except Exception` that swallow errors (l. 90, 149, 694);
  - option defaults read from kwargs (l. 139-140);
  - unit strings with trailing whitespace `"counts_per_second "` and `"degree "` (`metadata.py` l. 135-136);
  - `"micrometer"` unit not in the scanner's list (`metadata.py` l. 123), probably a scanner heuristic and benign.
- **Low/info:** silent `except IndexError`/`KeyError`/`sqlite3.OperationalError` (l. 281, 334, 541, 591, 1012), `.get('ValuesPerCurve', 1)` (l. 572) and `.get('NumValues', 1)` (l. 887) fallbacks, `interp1d` data-changing operation (l. 443), `min(len(a), len(b))` truncation (l. 489), `or 'entry'` fallback (l. 203), 15 hits for keys spelled differently.

## Not verified

- The NeXus writer and any code outside the excerpts inspected.
- Whether `np.flip` of only the axis is compensated elsewhere.
