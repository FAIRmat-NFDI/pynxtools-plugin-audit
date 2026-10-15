# J.A. Woollam VASE / CompleteEASE `.dat` ellipsometry parser (`pynxtools-ellips`)

## Source files reviewed

- `pynxtools_ellips/parsers/woollam.py` — `WoollamParser` and five module-level helpers (268 lines).
- Inherited: `_EllipsParser` (`pynxtools_ellips/parsers/base.py`). How `header_config` reaches `_parse(**kwargs)` and how `self.data` is consumed is inferred from `woollam.py` only.
- External: `pandas`, `numpy`, `pynxtools.dataconverter.helpers.extract_atom_types`.
- Project: [pynxtools-ellips (develop)](https://github.com/FAIRmat-NFDI/pynxtools-ellips/tree/develop).

**Line-number note:** References below refer to the file as supplied in the conversation on 15th October 2026. `woollam l.` = `woollam.py`.

## At a glance

| | |
|---|---|
| **Input format** | Tabular `.dat` export of a Woollam VASE/CompleteEASE ellipsometer, one row per (angle, wavelength), blocks repeated per angle of incidence |
| **Parser class** | `WoollamParser(_EllipsParser)` (woollam l. 36–138) |
| **Reader** | `pandas.read_csv(header=None, names=colnames, skiprows=skip, delimiter=sep)` (woollam l. 157–164) |
| **Layout source** | Not the file: `colnames`, `sep`, `skip`, `filename`, `Data.*`, `derived_parameter_type`, `plot_name` come from the ELN YAML passed as `header_config` (woollam l. 42–46, 70) |
| **Raw-data storage** | `whole_data` (a `DataFrame`, local to `_parse`) |
| **Output from parser** | `self.data`: `measured_data`, `measured_data_errors`, `<derived_parameter_type>`, `<spectrum_type>_spectrum`, `angle_of_incidence`, `angle_of_detection`, per-label link dicts and `<label>_long_name` (woollam l. 89–132); `atom_types` from `post_process` |
| **Extra state** | `data_labels`, `plot_name`, `spectrum_type`, `spectrum_unit` (woollam l. 54–57, 107–110, 118–120) |
| **Target definition** | NeXus ellipsometry definition (`NXellipsometry`; implied by the package) |
| **Project context** | [pynxtools-ellips](https://github.com/FAIRmat-NFDI/pynxtools-ellips). Only parser in this audit whose column layout is not self-describing. |

**Standard behaviour.** `matches_file` looks for `VASEmethod[` in the first five lines (woollam l. 59–67). `_parse` merges `DEFAULT_HEADER` with the ELN header, loads the table, finds the distinct angles, builds a label per (data type, angle), slices the table into 3D arrays `[angle, data type, point]` for values and errors, adds the derived-parameter array and the spectrum axis, and registers link-and-slice descriptors for every label (woollam l. 69–132). `post_process` derives `atom_types` from the chemical formula if the ELN has none (woollam l. 134–138).

## Formula / transformation

### Parser: separator escape

**Location:** woollam l. 76–79. The ELN string `"\\t"` is turned into a real tab with `.encode("utf-8").decode("unicode_escape")`. Default `{"sep": "\t", "skip": 0}` (woollam l. 33).

### Parser: angle blocks

**Location:** `_data_set_dims()` (woollam l. 187–195).

```python
energy = whole_data["type"].astype(str).values.tolist().count("E")      # rows of type "E"
unique_angles, counts = np.unique(
    whole_data["angle_of_incidence"].to_numpy()[0:energy].astype("int64"),
    return_counts=True)
```

The columns `type` and `angle_of_incidence` must be listed in `colnames`. The first `energy` rows are assumed to be the ellipsometric rows. Angles are cast to integers, sorted, and counted; `counts[0]` is later used as the number of points per angle.

### Parser: labels

**Location:** `_header_labels()` (woollam l. 167–184).

| `Data.data_type` | Types | Label example |
|---|---|---|
| `Psi/Delta` | `Psi`, `Delta` | `Psi_65deg` |
| `tan(Psi)/cos(Delta)` | `tan(Psi)`, `cos(Delta)` | `tan(Psi)_65deg` |
| anything else | Mueller matrix `m11 … m44` (16) | `m11_65deg` |

`labels = {type: [type_<angle>deg for each angle]}` with `int(angle)` (woollam l. 180–182). For angles `[55, 65, 75]` and Psi/Delta: `{"Psi": ["Psi_55deg", "Psi_65deg", "Psi_75deg"], "Delta": [...]}`.

### Parser: measured data and errors

**Location:** `_data_array()` (woollam l. 235–267).

$$
M[a, t, :] = \text{col}_t[\,b_a : b_{a+1}\,],\qquad b_k = k\cdot c_0,\ \ c_0 = \text{counts}[0]
$$

Shape `[n_angles, n_types, c_0]`. Errors use the column `err.<type>` (woollam l. 261). The block boundaries `b_k` come from a loop that steps by `counts[0]` over the **whole** table (woollam l. 241–245).

### Parser: derived parameter

**Location:** `_parameter_array()` (woollam l. 198–232). Shape `[n_angles, 1, c_0]`. The source column is the right-most column of `colnames` that is not NaN in the last row of the table; the slice for angle `a` is `block_idx[a + 6] : block_idx[a + 7]` (woollam l. 227–229). The magic offset 6 is not explained in the file.

### Parser: link and slice descriptors

**Location:** woollam l. 119–132. For `dindx` (data type) and `index` (angle):

```python
self.data[key] = {"link": "/entry/data_collection/measured_data",
                  "shape": np.index_exp[index, dindx, :]}
self.data[f"{key}_errors"] = {"link": "/entry/data_collection/measured_data_errors", ...}
self.data[f"{key}_long_name"] = f"{plot_name} (degree)"      # first label only
```

## Standard behaviour

1. **Detection.** `"VASEmethod["` in the first five lines read as UTF-8 (woollam l. 62–67).
2. **Header.** `header_config` is required (woollam l. 70–72); defaults are updated with it and `sep` unescaped (woollam l. 74–79).
3. **Load.** `_load_as_pandas_array()` requires `colnames`, `skip`, `sep` (woollam l. 149–152) and an existing file (woollam l. 154–155).
4. **Angles.** `_data_set_dims()` (see above).
5. **Labels.** `_header_labels()`.
6. **Arrays.** `measured_data` and `measured_data_errors` (woollam l. 86–90).
7. **Derived parameter.** Stored under the key given by `header["derived_parameter_type"]` (woollam l. 92–96).
8. **Spectrum axis.** `spectrum_type` (e.g. wavelength or energy column) must be in `colnames` or `ValueError` is raised (woollam l. 104–105); the first `counts[0]` values are stored as `<spectrum_type>_spectrum` (woollam l. 111–113). `Angstroms` becomes `angstrom` (woollam l. 108–110).
9. **Angles.** `angle_of_detection` and `angle_of_incidence` both hold `unique_angles` (woollam l. 115–116).
10. **Links.** One link dict per label and per `_errors` label (woollam l. 119–132).
11. **post_process.** If `/ENTRY[entry]/SAMPLE[sample]/atom_types` is absent but `chemical_formula` is present, `extract_atom_types(formula)` is stored as `atom_types` (woollam l. 134–138).

## Special behaviour

1. **ELN-driven layout.** `colnames`, `sep` and `skip` are user input (woollam l. 42–46, 149–164).
2. **Reference-style output.** Per-label values are not copied; they are `link` + `shape` dicts that point to the 3D arrays (woollam l. 123–130).
3. **Hard-coded target path.** `/entry/data_collection/measured_data` (woollam l. 124, 128) is a fixed path, not a template path with an entry name.
4. **Same angles for incidence and detection** (woollam l. 115–116).
5. **Mueller fallback.** Any unknown `data_type` (including typos) produces the 16 Mueller labels (woollam l. 174–178).
6. **Long name only on the first label** (woollam l. 131–132).

## Behaviour to investigate

1. **Off-by-one in the NaN search.** In `_parameter_array` the loop recomputes `temp` from the same column before incrementing `data_index` (woollam l. 217–223). After one NaN column the validated column is `-(k)` but the column used at woollam l. 227 is `-(k+1)`. Check with a real export (the comment at woollam l. 209–210 says "last but one column").
2. **Magic block offset.** `block_idx[index + 6]` (woollam l. 228) fails with `IndexError` for files with fewer than `n_angles + 6` blocks, and silently reads the wrong rows if the layout differs.
3. **Out-of-range last row.** `block_idx[-1] - 1` (woollam l. 212–214) exceeds the table length when `len(whole_data)` is not a multiple of `counts[0]`.
4. **Integer angles.** `astype("int64")` and `int(angle)` (woollam l. 192, 182) truncate `65.5` to `65`; angles 65.2 and 65.7 merge into one block and corrupt the block size.
5. **Uniform-block assumptions.** Equal number of points per angle (`counts[0]`), all `E` rows first and contiguous, angles in ascending order (woollam l. 189–193, 241–255). No check; `np.empty` arrays (woollam l. 238–239) stay uninitialised if a slice is skipped, and shorter slices raise a broadcast `ValueError`.
6. **`pandas` column count.** If the file has more columns than `colnames`, `read_csv` uses the extra leading columns as the index, silently shifting names (woollam l. 157–164).
7. **Required but undocumented columns.** `type`, `angle_of_incidence` (woollam l. 189–190) and `err.<type>` (woollam l. 261) are not mentioned in the docstring (woollam l. 37–47).
8. **Hard-coded `(degree)`.** `long_name` always ends with `(degree)` (woollam l. 132), wrong for `tan(Psi)/cos(Delta)` or Mueller data.
9. **Unit mapping.** Only `Angstroms` → `angstrom` (woollam l. 108–110); `spectrum_unit` is not validated.
10. **`header_config` keys.** `derived_parameter_type`, `Data.spectrum_type`, `Data.spectrum_unit`, `Data.data_type`, `plot_name` are accessed with `[]` (woollam l. 92, 98–101, 118, 170); a missing key raises `KeyError`.
11. **Duplicate checks.** `colnames/skip/sep` are checked twice for different keys (woollam l. 71–72 vs 149–152); `sep` unescape happens only if `sep` is in `header_config` (woollam l. 76).
12. **Detection.** `VASEmethod[` must be in the first five lines (woollam l. 64).
13. **`post_process`.** Only `atom_types`; `extract_atom_types` behaviour on malformed formulas is not visible here (woollam l. 138).
14. **Cast on type column.** `astype(str)` then count of `"E"` (woollam l. 189) counts exact matches only.

## Scanner findings

No scanner run was performed for `pynxtools-ellips`.
