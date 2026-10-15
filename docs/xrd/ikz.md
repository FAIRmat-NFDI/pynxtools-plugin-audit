# Rigaku RASX and Bruker BRML XRD readers `ikz.py` (`readers-xrd`)

## Source files reviewed

- `fairmat_readers_xrd/…/ikz.py` — `try_scalar()`, `parse_rasx_metadata()`, `RASXfile`, `BRMLfile` (553 lines). The exact package path was not stated.
- Inherited: `fairmat_readers_xrd.utils.to_pint_quantity`.
- External: `numpy`, `xmltodict`, standard `zipfile`, `xml.etree.ElementTree`.
- Origin: code adapted from `IKZ/xray/io.py` by Dr. Carsten Richter (header, ikz l. 1–5); BRML parts and the `mounted_optics_info` block were added later (ikz l. 395, 412, 417–424).
- Project: [readers-xrd](https://github.com/FAIRmat-NFDI/readers-xrd/tree/main) and [pynxtools-xrd](https://github.com/FAIRmat-NFDI/pynxtools-xrd).

**Line-number note:** References below refer to the file in the development branch on 15th October 2026. `ikz l.` = `ikz.py`.

## At a glance

|                             |                                                                                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Input formats**           | Rigaku `.rasx` (ZIP of `Profile*.txt`, `Image*`, `MesurementConditions*.xml`) and Bruker `.brml` (ZIP of `Experiment0/DataContainer.xml` and `RawData*.xml`) |
| **Classes**                 | `RASXfile` (ikz l. 136–326), `BRMLfile` (ikz l. 328–552)                                                                                                     |
| **Reader**                  | `zipfile.ZipFile`, `np.loadtxt`, `ElementTree` (RASX), `xmltodict` (BRML)                                                                                    |
| **Raw-data storage (RASX)** | `.data` list of N×3 arrays, `.images` list of detector frames, `.meta` list of metadata dicts, `.positions`, `.units` (ikz l. 195–209)                       |
| **Raw-data storage (BRML)** | `.data` and `.motors` (`defaultdict(list)`), `.mounted_optics_info` (ikz l. 343–344, 418–424)                                                                |
| **Output**                  | `get_scan_data()`, `get_scan_info()`, `get_source_info()` return dicts of `pint` quantities from `to_pint_quantity` (ikz l. 229–317, 426–552)                |
| **Target definition**       | `NXxrd_pan` (implied by the package)                                                                                                                         |
| **Project context**         | The only file in the audit with two format readers sharing one method set; the two sets of keys differ (see below)                                           |

**Standard behaviour.** `RASXfile` iterates all `Profile*.txt` members and their metadata XML, loads the 2θ/intensity/third column, parses a rich metadata tree, then also loads detector images and collapses axis positions into scalars when constant. `BRMLfile` parses the data container, loops over the raw-data XML files, slices each `Datum` matrix by `DataView` descriptors, reconstructs scan-axis values by `linspace` and collects drive positions. Both expose the same three accessor methods.

**Comparison of RASX and BRML accessors.**

| | RASX | BRML |
|---|---|---|
| 2θ key | `2Theta` (ikz l. 252) | `2Theta` (ikz l. 452, 459) |
| sample axes | `Omega, Chi, Phi, X, Y` (ikz l. 259) | `Theta, Chi, Phi` (ikz l. 467) |
| source keys | `TargetName, Voltage, Current, WavelengthKalpha1/2, WavelengthKbeta` (ikz l. 299–316) | `TubeMaterial, Voltage, Current, WaveLengthAlpha1/2/Beta/Ratio` (ikz l. 520–550) |
| `get_scan_info` | whole `ScanInformation` dict (ikz l. 281) | only `ScanName` (ikz l. 494–496) |

## Formula / transformation

### Helper: scalar conversion

**Location:** `try_scalar()` (ikz l. 25–34). `int(val)` → `float(val)` → raw value. `"3"` → `3`, `"3.5"` → `3.5`, `None` → `None`.

### RASX: file names

**Location:** ikz l. 140, 150–151, 164, 174–175. Profiles are members with `Profile` in the name; the metadata name is `Profile…` with `Profile` replaced by `MesurementConditions` and the extension changed to `.xml`. The spelling `Mesurement` matches the archive naming (verify on a real file). Images are members containing `Image`.

### RASX: profile loading

**Location:** ikz l. 153–156. `f.seek(3)` skips three non-ASCII bytes, `np.loadtxt(f)` gives N×3 (2θ, intensity, a third column that is dropped at ikz l. 250).

### RASX: images

**Location:** ikz l. 180–190. Detector shape from the detector name: `HyPix3000(H)` → (385, 775); `HyPix3000(V)` → (775, 385); otherwise `(-1,)`; `np.fromstring(..., dtype=np.uint32)` then `resize`.

### RASX: positions

**Location:** ikz l. 198–209. For each metadata set and each axis, `Position` is appended; if every entry is equal the list collapses to the scalar, otherwise to an array.

### RASX: start time

**Location:** `get_starttime()` (ikz l. 319–325). `strptime("%Y-%m-%dT%H:%M:%SZ")` then `time.mktime`, which treats the struct as **local time**.

### BRML: scan-axis values

**Location:** ikz l. 387–403.

$$
s = \text{Start}+\text{Ref},\quad e = \text{Stop}+\text{Ref},\quad
n_{int} = \operatorname{round}\!\left(\frac{|e-s|}{\text{Increment}}\right)
$$

`nsteps == 1` (RSM-type, per the comment at ikz l. 397): `linspace(s, e, n_int)`. `nsteps > 1` (1D scans): `linspace(s, e, nsteps)`. Example: `s=10`, `e=20`, increment 0.5 → `n_int = 20`; `linspace(10, 20, 20)` has spacing 0.526, not 0.5. The unit is `axis["Unit"]["@Base"].lower()` (ikz l. 389, 402).

### BRML: data views

**Location:** ikz l. 363–375. For each `RawDataView`, `Start` and `Length` slice the transposed `Datum` matrix; `FixedRawDataView` is keyed by `@LogicName`, `RecordedRawDataView` by `Recording/@LogicName`.

## Standard behaviour

### RASX (`RASXfile.__init__`, ikz l. 137–209)

1. Open the ZIP, list profiles, load each profile and its metadata (ikz l. 138–161).
2. Load images and their metadata; image metadata is appended to the **same** `meta` list (ikz l. 163–190).
3. Build `positions` and `units` from all metadata (ikz l. 198–209).

### RASX metadata (`parse_rasx_metadata`, ikz l. 37–133)

| Block | Content | Lines |
|---|---|---|
| groups | `GeneralInformation`, `ScanInformation`, `SampleInformation`, `RSMInformation` as tag → `try_scalar(text)` | 43–52 |
| `HardwareConfig` | optics categories (Name → SelectedUnit), `Monochromator` list, `Detector`, `distances` (namedtuples), `xraygenerator` | 54–80 |
| `RASHeader` | key/value pairs, `MEAS_COND_AXIS_NAME-<n>` collected as axis titles | 82–91 |
| `Axes` | ordered `Axis` namedtuples with `Description` from the header | 93–131 |

### RASX accessors

- `get_scan_data()` (ikz l. 229–272): per scan `intensity` and `2Theta` as quantities, 2θ unit from `units[scan_axis]` or `deg`; axes `Omega, Chi, Phi, X, Y` as lists of quantities or `None`.
- `get_RSM()` (ikz l. 211–227): stacks all profiles, returns `Intensity`, the scan motor and the other axes broadcast to the intensity shape.
- `get_scan_info()` (ikz l. 274–281), `get_source_info()` (ikz l. 283–317), `get_starttime()` (ikz l. 319–325).

### BRML (`BRMLfile.__init__`, ikz l. 329–424)

1. Open `Experiment{exp_nbr}/DataContainer.xml` and list the raw-data references (ikz l. 332–341).
2. For every reference parse the XML, read `MeasurementPoints`, build the data matrix, slice the data views, record `ScanName`, `TimePerStep`, `TimePerStepEffective`, `ScanMode` (ikz l. 345–382).
3. Build axis values from `ScanAxes` (ikz l. 384–403) and collect `Drives` as motors (ikz l. 405–415).
4. After the loop read the mounted optics of the **last** frame, `[]` on `KeyError`/`TypeError` (ikz l. 418–424).

### BRML accessors

- `get_scan_data()` (ikz l. 426–484): exactly one key with `counter` in its name is the intensity (ikz l. 440–447); `2Theta` from the scan-axis dicts; `Theta`, `Chi`, `Phi` from motors.
- `get_scan_info()` (ikz l. 486–498), `get_source_info()` (ikz l. 500–552).

## Special behaviour

1. **List normalisation.** `xmltodict` returns a dict for a single child and a list for several; the code wraps in lists at ikz l. 340–341, 364–365, 385–386, 406–407 — but not at ikz l. 419–421.
2. **Mixed value types per key.** BRML `self.data[name]` holds arrays for views and dicts for scan axes (ikz l. 372, 375, 403).
3. **Image metadata is appended to `meta`** (ikz l. 179), so `meta[0]` is the first profile but indices past the profiles refer to images.
4. **Constant axes collapse** to a single position in RASX (ikz l. 206–207), so axis lists can be shorter than the scan list.
5. **Progress output** is `print`/`sys.stdout`, not the logger (ikz l. 146–148, 171–172, 346–350). The `logger` argument of the accessors is unused (ikz l. 229, 426).
6. **`Theta` replaces `Omega`** in BRML (comment at ikz l. 466).

## Behaviour to investigate

1. **Time zone bug.** `time.mktime` interprets the UTC timestamp as local time (ikz l. 321–323). On a UTC+2 machine `2023-05-15T14:03:00Z` yields the epoch of 12:03 UTC. `calendar.timegm` would fix it.
2. **BRML `get_source_info` crashes for a single optic.** `mounted_optics_info` may be a dict (single `InfoData`); iterating it gives strings and `component['@xsi:type']` raises `TypeError` (ikz l. 513–514).
3. **Ratio gets a length unit.** `WaveLengthRatio` falls back to `'angstrom'` like the wavelengths (ikz l. 537–550).
4. **`nint` off by one?** For `nsteps == 1` the axis has `n_int` points with the endpoint included (ikz l. 394, 398), so spacing differs from `Increment`. Compare with the detector channel count. `Increment == 0` raises `ZeroDivisionError` (ikz l. 394).
5. **Silent unknown-attribute warning.** `Description` is added before the check, so a single unknown attribute does not trigger the warning (`len(attrib) < len(axis.attrib)`, ikz l. 123–130). Only two or more do. Also uses `print`.
6. **`axtitle[i]`** raises `KeyError` if the header has no title for axis `i` (ikz l. 123).
7. **No existence checks** for `HWConfigurations` (ikz l. 55–58), `optics['Detector']` (ikz l. 61) and `RASHeader` entries; any missing element gives `AttributeError`/`KeyError`.
8. **`Distance(**attrib)`** fails for unexpected attributes, unlike `Axis`, which filters them (ikz l. 73–76 vs 126).
9. **`get_RSM` with missing axes.** `self.positions` is a `defaultdict(list)`; a missing axis returns `[]`, `np.ndim([]) == 1`, and `[][:, None]` raises `TypeError` (ikz l. 198, 220–224). It also inserts the key.
10. **`get_RSM` assumptions.** Equal-length scans for `np.array(self.data)` and a squeeze that changes shape for a single scan (ikz l. 212–213). Output key `Intensity` differs from `intensity` in `get_scan_data` (ikz l. 214, 251).
11. **`np.fromstring` with binary data** is deprecated and may fail on current NumPy; use `np.frombuffer` (ikz l. 188). `resize` zero-pads or truncates silently if the size is wrong (ikz l. 189).
12. **Profile ordering.** Members are taken in ZIP order, matched by substring (`'Profile' in name`), not sorted numerically (ikz l. 140).
13. **BRML dead variable.** `scan_two_theta_value` is normalised (ikz l. 455–458) but the original `Value` is passed on (ikz l. 461).
14. **BRML no counter.** `counter_key[0]` raises `IndexError` with zero counters (ikz l. 444–447); only `>1` is handled.
15. **BRML single `DataRoute` assumed** (ikz l. 354); `nsteps == 0` leaves `rawdata` undefined (ikz l. 357–362).
16. **Name collisions** between view names and axis names would mix arrays and dicts under one key (ikz l. 372, 375, 403).
17. **`mounted_optics_info`** is read from the last `data` variable (ikz l. 419), not the first frame.
18. **Scalar-position edge case.** If all `Position` values are `None`, the scalar is `None` and `to_pint_quantity` receives an object array (ikz l. 206–207, 264–270).
19. **Docstrings out of date.** `get_source_info` says items are `[value, unit]` lists (ikz l. 285–288, 502–505) but returns `pint` quantities.
20. **Encoding and upstream licence.** XML is parsed with `encoding='utf-8'` by default (ikz l. 329). The upstream repository's licence should be checked against this file's use.

## Scanner findings

No scanner run was performed for `readers-xrd`.
