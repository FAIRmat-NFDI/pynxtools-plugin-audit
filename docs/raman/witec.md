# WITec Alpha `.txt` Raman export parser (`pynxtools-raman`)

## Source files reviewed

- `pynxtools_raman/parsers/witec.py` — `WitecParser` (143 lines).
- Inherited: `_RamanParser` (`pynxtools_raman/parsers/base.py`). Dispatch, `unused_attrs` handling and the order in which `_parse()` and `post_process()` are called are inferred from `witec.py` only.
- Inherited (companion mapping): `config_file_witec.json` (named at witec l. 43).
- Project: [pynxtools-raman repository](https://github.com/FAIRmat-NFDI/pynxtools-raman).

**Line-number note:** References below refer to the file in the development branch on 15th October 2026. `witec l.` = `witec.py`.

## At a glance

| | |
|---|---|
| **Input format** | WITec Alpha ASCII export `.txt` with a `[Header]` section (`key=value`) and a `[Data]` section (two comma-separated float columns) |
| **Parser class** | `WitecParser(_RamanParser)` (witec l. 35–142) |
| **Reader** | Plain Python line loop over `readlines()`, no external library (witec l. 57–58, 68–92) |
| **Raw-data storage** | local `header_dict` (str→str) and `data` (list of `[x, y]` rows) (witec l. 60–61) |
| **Output from parser** | `self.data = {"data/x_values": [float…], "data/y_values": [float…]}` (witec l. 97); `self.attrs` and `self.unused_attrs`: both copies of `header_dict` (witec l. 106–107); after `post_process`, `self.data["data/x_values_raman"]` (witec l. 142) |
| **Config** | `config_file_witec.json` (witec l. 43); `unused_attrs_group_name = "unused_witec_keys"` (witec l. 44) |
| **Target definition** | NeXus Raman application definition (implied by the package) |
| **Project context** | [pynxtools-raman](https://github.com/FAIRmat-NFDI/pynxtools-raman). Only parser that needs ELN input (laser wavelength) in order to compute its x-axis. |

**Standard behaviour.** `matches_file` looks for `[Header]` and `[Data]` in the first 50 lines (witec l. 46–54). `_parse` walks the file once, switching section on those two markers, collects header `key=value` pairs and, in the data section, every comma-containing line after a two-line mini header (witec l. 56–97). `post_process` converts the measured wavelengths (nm) into a Raman shift in cm⁻¹ using the laser wavelength found in the ELN data (witec l. 109–142).

**Comparison with `RodParser`.** `WitecParser` produces an instrument spectrum in nm and needs a derived x-axis; `RodParser` already receives Raman shift from the database and only post-processes metadata.

## Formula / transformation

### Parser: wavelength to Raman shift

**Location:** `transform_nm_to_wavenumber()` (witec l. 115–120), called at witec l. 137–139.

$$
\Delta\tilde\nu = -\left(\frac{10^7}{\lambda_{\text{meas}}} - \frac{10^7}{\lambda_{\text{laser}}}\right)
= \frac{10^7}{\lambda_{\text{laser}}} - \frac{10^7}{\lambda_{\text{meas}}}
$$

Wavelengths in nm, result in cm⁻¹, Stokes shifts positive. Example: `λ_laser = 532`, `λ_meas = 580` → 1555.6 cm⁻¹. The result is `ndarray.tolist()` (witec l. 120) and stored under `data/x_values_raman` (witec l. 142). No unit check is made on `data/x_values` (the header key `XAxisUnit` is collected but not read here).

### Parser: start of numeric data

**Location:** witec l. 77–78, 88–92.

```python
data_mini_header_length = line_count + 2        # on '[Data]'
...
if line_count > data_mini_header_length: ...    # parse float pair
```

The first two lines after `[Data]` are skipped; parsing starts on the third (line number `N + 3` if `[Data]` is line `N`).

### Parser: unit alias

**Location:** `_WITEC_ALIASES` (witec l. 30–32) and witec l. 99–102. `DataUnit == "CCD cts"` is replaced by `"counts"`. The comment (witec l. 27–29) states that only observed values should be added.

## Standard behaviour

1. **Detection.** First 50 lines read as UTF-8 and joined; both section markers must be present (witec l. 49–54). `OSError` returns `False`.
2. **Load.** `open(file)` and `readlines()` (witec l. 57–58). Each line is stripped (witec l. 71) and counted (witec l. 69).
3. **Sections.** `startswith("[Header]")` → `current_section = "header"`; `startswith("[Data]")` → `"data"` (witec l. 74–80).
4. **Header.** In the header section, lines containing `=` are split once and stored stripped (witec l. 83–85).
5. **Data.** In the data section, lines containing `,` and past the mini header are split on `,`; the first two fields become floats (witec l. 88–92).
6. **Transpose.** `[[x1,y1],[x2,y2],…]` → `[[x1,x2,…],[y1,y2,…]]` via `zip(*data)` (witec l. 95).
7. **Store.** `self.data` gets the two lists (witec l. 97).
8. **Aliases.** Values normalised (witec l. 100–102).
9. **Attributes.** `self.attrs = dict(header_dict)`; `self.unused_attrs = dict(header_dict)` (witec l. 106–107). The comment (witec l. 104–105) notes the header fields (`XAxisUnit`, `DataUnit`, `PositionX`, …) are scalar metadata.
10. **post_process.** Look up the laser wavelength in the ELN dict (witec l. 122–135), convert (witec l. 137–139), store (witec l. 142).

### Laser wavelength lookup

**Location:** `get_incident_wavelength_from_NXraman()` (witec l. 122–133). All ELN keys containing `/beam_incident/wavelength` are collected (witec l. 126), then filtered to those that **end** with that string (witec l. 128–130), and the **first** is used (witec l. 132). This excludes sibling keys such as `…/wavelength/@units`.

## Special behaviour

1. **Column count fixed at two.** Extra columns in `[Data]` are ignored (witec l. 92).
2. **Values are Python lists**, not NumPy arrays, in both `data/x_values` and `data/x_values_raman` (witec l. 95–97, 120).
3. **Duplicate header keys** overwrite earlier ones (witec l. 85).
4. **`attrs` and `unused_attrs` are separate dicts** with identical content (witec l. 106–107); the base class presumably removes consumed keys from `unused_attrs` only.
5. **Matching reads UTF-8, parsing reads the locale default** (witec l. 50 vs 57).

## Behaviour to investigate

1. **Missing laser wavelength.** `filtered_list[0]` raises `IndexError` if no matching ELN key exists (witec l. 132); a `None` value would fail later in NumPy arithmetic (witec l. 117). A short error message would help users.
2. **Unit assumptions.** The laser wavelength and `x_values` are both assumed to be in nm. `XAxisUnit` from the header is never compared (witec l. 106); an export in a different unit gives a wrong x-axis without warning.
3. **Detection window.** If `[Data]` starts after line 50, `matches_file` returns `False` (witec l. 51).
4. **Mini-header length.** The fixed offset of 2 (witec l. 78) assumes the WITec header block never changes. A third non-numeric line containing `,` would raise `ValueError` in `float()` (witec l. 92).
5. **Locale and decimal separator.** A decimal comma would collide with the column separator (witec l. 88, 91).
6. **Empty data.** If no data lines are found, `transposed[0]` raises `IndexError` (witec l. 97).
7. **Encoding.** `open(file)` without `encoding=` (witec l. 57) depends on the platform default; a header with `µ` or `°` can fail on a non-UTF-8 locale.
8. **Header section ends implicitly.** There is no handling for other sections; any further `[Section]` line before `[Data]` is treated as part of the header (witec l. 83).
9. **Alias list is tiny.** One entry (witec l. 30–32); other CCD or detector unit strings pass through unchanged and may not be valid unit strings downstream.
10. **First match wins.** With several `…/beam_incident/wavelength` keys (e.g. several entries), dict order decides (witec l. 132).
11. **Ordering with the base class.** `post_process` must run after the ELN dict is loaded; this relies on `_RamanParser` (not supplied).

## Scanner findings

No scanner run was performed for `pynxtools-raman`.
