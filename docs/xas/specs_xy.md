# SpecsLab Prodigy XY export parser for XAS (`pynxtools-xas`)

## Source files reviewed

- `pynxtools_xas/parsers/specs_xy.py` — `SpecsXYParser` and helpers `_sanitize_entry_name()`, `_element_and_edge()`, `_to_xas_spectrum()` (103 lines).
- Imported: `pynxtools_xps.parsers.specs.xy.parser.SPECSXYParser` (does the actual file parsing) and `pynxtools_xps.parsers.base.ParsedSpectrum` (xarray-based, with `.data`, `.metadata`, `.average()`, `.errors()`); `_XASParser`, `ParsedSpectrum`, `VendorType`, `parse_datetime` from `pynxtools_xas`.
- Imported (companion mapping): `config_specs_xy.json` (xy l. 89).
- Project: [pynxtools-xas repository](https://github.com/FAIRmat-NFDI/pynxtools-xas).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `xy l.` = `specs_xy.py`.

## At a glance

| | |
|---|---|
| **Input format** | SPECS SpecsLab Prodigy XY export (`.xy`) holding electron-yield NEXAFS scans |
| **Parser class** | `SpecsXYParser(_XASParser)` (xy l. 86–102) |
| **Reader** | Delegated to `pynxtools_xps`' `SPECSXYParser`; this file only adapts the result (xy l. 94, 96–102) |
| **Raw-data storage** | none local; the XPS parser's `data` dict of xarray-based spectra |
| **Output from parser** | `self._data[<sanitized region>] = ParsedSpectrum(energy, intensity, intensity_errors, metadata)` (xy l. 76–83, 99–102) |
| **Config** | `config_specs_xy.json`, vendor `"specs"`, extension `.xy` (xy l. 89–91) |
| **Target definition** | `NXxas` (per package) |
| **Project context** | The only XAS parser that wraps another plugin's parser; the only one carrying `intensity_errors` |

**Standard behaviour.** `matches_file` forwards to the XPS parser. `_parse` runs the XPS parser, then converts each spectrum: it finds the energy dimension, infers element and edge from the region name, sets the title, makes the timestamp explicit, flattens the mirror-current channel, and averages repeated scans with error estimates (xy l. 50–83, 96–102).

**Comparison with HDF5-based XAS parsers.** No HDF5 handling, no `flatten_hdf5_group`; all format knowledge lives in `pynxtools_xps`, so a change there changes this parser.

## Formula / transformation

### Parser: element and edge from the region name

**Location:** `_ELEMENT_EDGE_RE` (xy l. 28) and `_element_and_edge()` (xy l. 42–47).

```text
^([A-Z][a-z]?)-([A-Za-z0-9]+?)(?:_\d+)?$
"O-K_134"  -> element "O",  edge "K"
"Fe-L3"    -> element "Fe", edge "L3"
"Fe-L"     -> element "Fe", edge "L"  -> canonicalised to "L2,3"
```

`_EDGE_CANONICALIZATION = {"L": "L2,3", "M": "M4,5"}` (xy l. 35). Non-matching region names give `(None, None)` (xy l. 44–45).

### Parser: repeats, mean and error

**Location:** xy l. 51, 76–83.

$$
n_{\text{repeats}} = n_{\text{cycle}}\cdot n_{\text{scan}},\qquad
I = \texttt{spectrum.average()},\qquad
\sigma = \begin{cases}\texttt{spectrum.errors()} & n_{\text{repeats}} > 1\\ \text{None} & \text{otherwise}\end{cases}
$$

Dimensions `cycle` and `scan` default to size 1 when absent. The meaning of `average()` and `errors()` is defined in `pynxtools_xps` and was not available for this review.

### Parser: mirror current

**Location:** xy l. 69–74. `external_i_mirror` is reshaped to 1D and stored as `i0_mirror` (the original key remains).

## Standard behaviour

1. **Detect.** `_XPSSpecsXYParser().matches_file(file)` (xy l. 93–94).
2. **Parse.** `xps_parser.parse(file, **kwargs)` (xy l. 97–98).
3. **Name.** Each entry name goes through `_sanitize_entry_name` (`[^0-9A-Za-z_]` → `_`, strip, fallback `"entry"`) (xy l. 38–39, 99–100).
4. **Energy axis.** First dimension of the data that is not `cycle` or `scan` (xy l. 52); its coordinate values are the energy (xy l. 77).
5. **Metadata.** Copy of the XPS metadata; add `element_name`, `edge_name` when found (xy l. 54–60); `title = region_name or group_name` (xy l. 61).
6. **Timestamp.** A string `time_stamp` goes through `parse_datetime` with no explicit time zone (xy l. 63–67).
7. **Intensity and errors** as above (xy l. 78–81).

## Special behaviour

1. **Wraps a sibling plugin.** The XPS parser does format parsing; this file adapts shapes (xy l. 6–13).
2. **UTC made explicit.** The export header says "Time Zone Format: UTC"; the timestamp itself has no offset (xy l. 63–64).
3. **Canonicalisation of split edges.** `L` → `L2,3`, `M` → `M4,5` (xy l. 30–35).
4. **Local copy of the sanitiser.** Other parsers import `sanitize_entry_name` from `hdf5_utils`; this file defines its own (xy l. 38–39).

## Behaviour to investigate

1. **Matching is not XAS-specific.** `matches_file` is true for every SPECS Prodigy `.xy`, including XPS files (xy l. 93–94). Dispatch must rely on vendor, extension and an explicit technique setting, which are outside this file.
2. **Canonicalisation comment vs code.** The comment says a region spanning more than 30 eV covers both split components (xy l. 31–34), but the code maps `L` and `M` unconditionally and does not look at the energy range (xy l. 47).
3. **Edge strings.** Only a bare `L` or `M` is mapped; `L3`, `K1` and similar pass through (xy l. 47). Compare with `EsrfFluoParser`, which yields `"L"` or `"M"` (fluo l. 62).
4. **Energy axis meaning.** The coordinate is used as given (xy l. 77); whether it is photon energy, kinetic energy or binding energy is not checked here.
5. **`StopIteration`.** `next(d for d in dims if d not in (...))` raises if all dimensions are `cycle` or `scan` (xy l. 52).
6. **Time zone.** `parse_datetime(time_stamp)` is called without `tzinfo` (xy l. 67), so the "UTC" result depends on that function's default.
7. **Duplicate keys.** `external_i_mirror` and `i0_mirror` both remain in the metadata (xy l. 72–74).
8. **Name collisions.** The dict comprehension overwrites entries whose sanitised names coincide (xy l. 99–102).
9. **Private import alias.** The XPS `ParsedSpectrum` is imported under a private alias (xy l. 20); changes in `pynxtools_xps` data structures (`data.sizes`, `average()`, `errors()`) break this adapter.
10. **Region regex.** Names such as `"Mn-L3,2"` or `"O_K"` do not match and yield no element or edge, so the ELN must provide them (xy l. 28).

## Scanner findings

No scanner run was performed for `pynxtools-xas`.
