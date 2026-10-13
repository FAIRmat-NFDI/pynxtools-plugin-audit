# Scienta Omicron parsers

Source folder: `pynxtools_xps/parsers/scienta/` (`hdf5_parser.py`, `igor_parser.py`, `txt_parser.py`, `metadata.py`, `data_model.py`).

Three readers share no axis code. The axis comes from the file array (HDF5), the wave scaling (Igor) or the text columns (TXT). No reader converts between binding and kinetic energy; each takes the axis from its input format.

## At a glance

| | |
|---|---|
| **Input format** | Plain text (`.txt`), Igor Binary Wave (`.ibw`) and HDF5 (`.h5` / `.hdf5`). Versions are listed as "any" for all three formats. |
| **URL (source code)** | [scienta](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/scienta/) |
| **Documentation** | [Data from Scienta Omicron instruments](https://fairmat-nfdi.github.io/pynxtools-xps/reference/scienta.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/scienta/metadata.py), [config_scienta.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_scienta.json), [config_scienta_hdf5.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_scienta_hdf5.json) |

**Standard behaviour.** The parser is chosen by file extension. The output is a `ParsedSpectrum` whose data is an xarray with `(cycle, scan, energy)` dims. Header fields are mapped to parser-internal metadata keys in `metadata.py`.

**Special behaviour.**

- The `.txt` extension is shared with the CasaXPS text-export parsers (`vms_export/parser_export.py` l. 110, 581). The reader tells them apart by the first line of the file: Scienta requires exactly `[Info]` (`txt_parser.py` l. 55); the CasaXPS rows layout requires `Characteristic Energy eV` and `Acquisition Time s`; the CasaXPS columns layout requires a line starting with `Cycle` and containing `:` (`matches_file` of each layout in `vms_export/parser_export.py`). A given file can match only one.
- The Scienta `matches_file` accepts a file with `[Info]` on line 1 and a `Number of Regions=` line in the first 200 lines, even if the word "scienta" is never found (`txt_parser.py` l. 69-72, the final `return found_regions`). A `.txt` file from another vendor with the same layout would be parsed as Scienta data. Check whether such files exist and whether this should be stricter.
- Energy axis: IBW `E_i = sfB + sfA · i` (`igor_parser.py` l. 268-271); TXT and HDF5 read it from the file (HDF5 falls back to the channel index when `x_axis` is missing). Kinetic ↔ binding energy is only labelled, never converted (`igor_parser.py` l. 144-146, `metadata.py` l. 191-192).

## Formula / transformation

### HDF5 (`hdf5_parser.py`)

**Step 1: extra axes (l. 140-147)**

```
additional_axes = reversed list of datasets matching acquisition/spectrum/data/<name>_axis  (except x_axis)
data_axes       = additional_axes + ["energy"]                                        (l. 147)
```

The pattern at l. 140 matches every dataset under `data/` whose name ends in `_axis`, apart from `x_axis`. The order is reversed (l. 141-145).

**Step 2: energy axis (l. 150-164)**

```
energy_arr = np.asarray(x_axis)                    if x_axis exists                  (l. 158-159)
           = np.arange(intensity_arr.shape[-1])    if not and intensity is non-empty (l. 161-163)
           = np.array([])                          otherwise                          (l. 164)
```

The axis comes from `acquisition/spectrum/data/x_axis` (l. 151). The fallback is a pure index axis `0 … N−1` with no start or step.

**Step 3: shape and coordinates (l. 167-182)**

```
intensity_arr = intensity_arr[np.newaxis, np.newaxis, ...]            -> (1, 1, …)
n_physical    = intensity_arr.ndim − 2
physical_dims = data_axes[-n_physical:]  if n_physical <= len(data_axes)  else ["axis_0", "axis_1", …]
dims          = ("cycle", "scan") + physical_dims
coords        = {"energy": energy_arr}  only if "energy" in physical_dims
```

Energy is assumed to be the last axis of the intensity array. The additional axes get no coordinates (l. 179-182).

Example (my own numbers): data of shape `(n_a, n_e)` with one extra dataset `y_axis` gives `data_axes = ["y_axis", "energy"]` and dims `(cycle, scan, y_axis, energy)`.

### Igor (`igor_parser.py`)

**Step 4: axis values (l. 268-271, called at l. 147)**

```
E_i = sfA[dim] · i + sfB[dim],   i = 0 … nDim[dim] − 1
```

Example (my own numbers): `sfA = −0.5`, `sfB = 600`, `nDim = 5` gives `[600, 599.5, 599, 598.5, 598]`.

**Step 5: energy type from the dimension name (l. 143-151)**

```
if dim in ("kinetic_energy", "binding_energy", "analyser_energy"):
    spectrum["energy_scale"] = _context.map_value("energy_scale", dim)
    dim = "energy"
unit = file unit, or _context.get_default_unit(dim) if empty;  spectrum["units"][dim] = _context.map_unit(unit)
```

The binding/kinetic type is read from the name of the Igor dimension, and the dimension is renamed `"energy"`.

**Step 6: energy axis selection (l. 179-185)**

```
energy_axis = data["energy"]
if None and axis_labels:  energy_axis = data[axis_labels[0]]      (first axis label, whatever it is)
if still None:            energy_axis = np.array([])
```

A wave with no energy-named dimension uses the first axis, which could be an angle or a position, as the `"energy"` coordinate.

**Step 7: intensity and output (l. 187-207)**

```
intensity = first data label not containing "reduced", .squeeze()          (l. 187-194)
data      = intensity[np.newaxis, np.newaxis, :]   dims ("cycle", "scan", "energy")   (l. 203-207)
metadata["{axis}/@units"] = unit for each axis                              (l. 200-201)
```

The output is always one cycle and one scan.

### TXT (`txt_parser.py`)

**Step 8: axis and units (l. 190-221)**

```
[energy, intensity] = [float(s) for s in line.split(" ") if s != ""]     (l. 192)
energies.append(energy); intensities.append(intensity)                    (l. 193-194)
except ValueError: pass                                                    (l. 195-196)
energy_arr = np.array(energies);  dims ("cycle", "scan", "energy"), shape (1, 1, n_energy)   (l. 209-216)
metadata["energy/@units"] = "eV";  metadata["intensity/@units"] = "counts_per_second"        (l. 220-221)
```

Only lines in the data section (`in_data`, l. 190) are read.

### Header metadata (`metadata.py`)

**Step 9: range, type and units**

```
dimension_name  -> energy_units   via _extract_energy_units  (l. 149, 189)  "Binding Energy [eV]" -> "eV", default "eV" (l. 56-63)
dimension_scale -> energy_axis    via _separate_dimension_scale (l. 151, 190)  np.array([float(s) for s in scale.split(" ")])  (l. 66-81)
dimension_size  -> energy_size;   low_energy -> start_energy;  high_energy -> stop_energy;  energy_step -> step_size   (l. 150, 154-156)
energy_unit     -> energy_scale_2 (l. 153);  energy_scale (l. 191), energy_scale_2 (l. 192), energy_mode (l. 207): all via _convert_energy_type
```

- `_extract_energy_units` keeps only the unit, so the "Binding" or "Kinetic" word in `dimension_name` is discarded.
- The docstring example for the scale is `"600 599.5 599 598.5 5"` (`metadata.py` l. 73), a descending list.
- `_DEFAULT_UNITS` gives `"eV"` for `pass_energy`, `excitation_energy`, `energy_axis`, `center_energy`, `start_energy`, `stop_energy` and `step_size` (`metadata.py` l. 216-222).

## Special behaviour

1. **Three readers, no shared axis code.** File array (HDF5), wave scaling (Igor), text columns (TXT).
2. **Binding/kinetic is only read, never converted.** There is no `hν − KE` and no work function anywhere in the folder.
3. **Several sources for the type.** Igor uses the dimension name (`igor_parser.py` l. 144-146). Header fields use `energy_scale`, `energy_scale_2` and `energy_mode` (`metadata.py` l. 191-192, 207), and `data_model.py` l. 47 has the default `"kinetic"`.
4. **Cycle and scan are 1 for Igor and TXT** (`igor_parser.py` l. 203, `txt_parser.py` l. 212). HDF5 may add extra axes (`hdf5_parser.py` l. 147).
5. **Hard-coded units in TXT** (`txt_parser.py` l. 220-221). Igor takes units from the file, then from defaults (`igor_parser.py` l. 149-151).
6. **Silent data loss in TXT** (`txt_parser.py` l. 195-196). Unparseable lines are skipped without any message.
7. **Leftover debug output** (`igor_parser.py` l. 175: `print(entry_name)`).

## Behaviour to investigate

- **Wrong coordinate handling in Igor (`igor_parser.py` l. 181-183):** if no dimension is named as an energy, the first axis label is used as `"energy"`; an empty array is the last resort (l. 184-185).
- **Multi-dimensional Igor data (`igor_parser.py` l. 193, 205):** `.squeeze()` followed by `[np.newaxis, np.newaxis, :]` only fits 1D data. A 2D spectrum gives 4 dimensions against 3 dim names and would raise an error.
- **Index axis in HDF5 (`hdf5_parser.py` l. 161-163):** if `x_axis` is missing, the axis is in channels but may be labelled eV (`metadata.py` l. 218).
- **No coordinate in HDF5 for extra dimensions (`hdf5_parser.py` l. 174-175, 181):** if `n_physical > len(data_axes)`, the dims become `axis_0…` and no energy coordinate is set.
- **Default unit key mismatch (`igor_parser.py` l. 150, `metadata.py` l. 218):** the Igor reader looks up the default unit for `"energy"`, but `_DEFAULT_UNITS` has `"energy_axis"`. If an axis has no unit in the file, the default may not be found.
- **Data loss in TXT (`txt_parser.py` l. 192, 195-196):** `split(" ")` fails on tab-separated lines, `float()` fails on decimal commas, and lines with extra columns fail. All are skipped silently.
- **Two axes in TXT (`metadata.py` l. 151, 190; `txt_parser.py` l. 209):** the header scale (`energy_axis`) and the data-section axis are never compared. `_separate_dimension_scale` also fails on double or trailing spaces (`metadata.py` l. 81).
- **Header range vs actual axis (`metadata.py` l. 154-156):** `start_energy`, `stop_energy` and `step_size` come from the header and are not checked against the axis.
- **Type fields can disagree (`metadata.py` l. 191-192, 207; `data_model.py` l. 47):** `energy_scale`, `energy_scale_2` and `energy_mode` could differ. The default `energy_units = "kinetic"` is a type stored in a field named units.
- **`analyser_energy` (`igor_parser.py` l. 144):** check what `_convert_energy_type` makes of it, since it is neither binding nor kinetic.
- **Work function and conversion:** none in this folder, so any BE/KE conversion must happen downstream.
- **Direction:** no flip was found in the code inspected, so the axis keeps the file's direction.

## Scanner findings

- **High:** duplicate dict key `time_per_spectrum_channel` (`metadata.py` l. 188 and 194); the second entry (`float`) wins.
- **Medium:** hard-coded `"eV"` and `"counts_per_second"` (`txt_parser.py` l. 220-221); `matches_file` swallows `Exception` in `hdf5_parser.py` l. 56, `igor_parser.py` l. 311 and 382 (classes `ScientaIgorParserOld` and `ScientaIgorParserPEAK`), and `txt_parser.py` l. 73.
- **Low/info:** silent `except KeyError` (`hdf5_parser.py` l. 136), `except ValueError` (`metadata.py` l. 96, 105; `txt_parser.py` l. 195), zero-filled array default (`data_model.py` l. 41), 20 hits for keys spelled differently (e.g. case or underscore variants), 4 exact string comparisons, 1 `print`.

## Not verified

- The bodies of `get_default_unit`, `map_unit`, `map_value` and `_convert_energy_type`.
- How `axes_labels_with_units` is built, and how the HDF5 reader sets units and `energy_scale`.
- `_filter_metadata` exclusions, and whether `energy_axis` from the header ends up in the output metadata.
