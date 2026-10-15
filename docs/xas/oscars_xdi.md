# OSCARS XDI-derived transmission XAS HDF5 parser (`pynxtools-xas`)

## Source files reviewed

- `pynxtools_xas/parsers/oscars_xdi.py` — `OscarsXdiParser` (111 lines).
- Inherited: `_XASParser` (`map_metadata_fields`, `_data`), `ParsedSpectrum`, `VendorType`; `parse_datetime`; `flatten_hdf5_group`, `sanitize_entry_name`.
- Inherited (companion mapping): `config_xas_trans.json`.
- Project: [pynxtools-xas repository](https://github.com/FAIRmat-NFDI/pynxtools-xas).

**Line-number note:** References below refer to the file in the develop branch on 15th October 2026. `xdi l.` = `oscars_xdi.py`.

## At a glance

| | |
|---|---|
| **Input format** | HDF5 (`.h5`, `.hdf5`) with one top-level group per XAS entry, already shaped close to `NXxas_trans`; derived from XDI files (docstring xdi l. 6–13) |
| **Parser class** | `OscarsXdiParser(_XASParser)` (xdi l. 31–110) |
| **Reader** | `h5py.File`; subtree flattened with `flatten_hdf5_group` (xdi l. 66–70) |
| **Marker** | group contains `computed_mu` (xdi l. 59, 68) |
| **Output from parser** | `self._data[<name>] = ParsedSpectrum(energy, intensity, metadata)` (xdi l. 73–77) |
| **Key map** | `metadata_field_map` with 14 entries (xdi l. 38–53) |
| **Config** | `config_xas_trans.json`, vendor `"oscars"` (xdi l. 34–36) |
| **Target definition** | `NXxas_trans` |
| **Project context** | A pre-mapped intermediate format, not a raw beamline dump: "a flatten of each group's subtree" (xdi l. 10–12). Only parser with an edge-energy back-fill. |

**Standard behaviour.** Detection by the presence of `computed_mu` in a top-level group. `_parse` flattens every matching group, takes `energy` and `computed_mu` as the spectrum, fills missing edge energies from sibling entries, converts the start time with the APS time zone and applies the key map (xdi l. 65–85).

**Comparison with `EsrfTransParser`.** Same shape (flatten, pop, map); differences are the marker, the key map, the absence of any unit conversion, the sibling back-fill and the order of time parsing relative to mapping.

## Formula / transformation

### Parser: key map

**Location:** xdi l. 38–53.

| Output key | Source path |
|---|---|
| `start_time` | `scan/start_time` |
| `element_name` | `element/symbol` |
| `edge_name` | `edge/name` |
| `edge_energy` | `scan/edge_energy` |
| `sample_name` | `sample/name` |
| `source_name`, `source_type`, `source_probe` | `instrument/source/{name,type,probe}` |
| `i0_data`, `itrans_data` | `instrument/i0/data`, `instrument/itrans/data` |
| `normalized_intensity` | `intensity` |
| `process_program`, `process_version`, `process_notes` | `process/program`, `process/version`, `process/notes/data` |

### Parser: edge-energy back-fill

**Location:** `_fill_missing_edge_energies()` (xdi l. 87–110).

```text
pass 1: by_edge[(element, edge)] = first non-None scan/edge_energy   (setdefault)
pass 2: entry without scan/edge_energy -> by_edge.get((element, edge))
```

Entries without element or edge in pass 1 are skipped (xdi l. 100); in pass 2 the lookup `(None, None)` finds nothing.

## Standard behaviour

1. **Detect.** `any(isinstance(g, h5py.Group) and "computed_mu" in g ...)`; exceptions return `False` (xdi l. 55–63).
2. **Flatten.** `metadata = flatten_hdf5_group(group)` (xdi l. 70).
3. **Spectrum.** `energy = pop("energy")`, `intensity = pop("computed_mu")` (xdi l. 71–72).
4. **Store.** `self._data[sanitize_entry_name(group_name)]` (xdi l. 73–77).
5. **Back-fill.** `_fill_missing_edge_energies()` (xdi l. 78).
6. **Per spectrum.** If `scan/start_time` is a string, replace with `parse_datetime(..., tzinfo=America/Chicago)`; then `map_metadata_fields(metadata)` (xdi l. 79–85).

## Special behaviour

1. **No unit conversion.** Energy is taken as given (xdi l. 71); the ESRF and mySpot parsers multiply by 1000.
2. **Fixed APS time zone** for all entries (xdi l. 26–28, 83).
3. **Back-fill assumes equal edges share an energy.** Entries with the same element and edge transition get the first tabulated value (xdi l. 88–94).
4. **`normalized_intensity` stays a copy.** `intensity` is mapped but not popped (xdi l. 49, 71–72).
5. **Mapping happens per spectrum after parsing** (xdi l. 85), not inside the file loop.

## Behaviour to investigate

1. **Energy unit unstated.** Neither the code nor the docstring say whether `energy` is eV; if a file uses keV the result is silently wrong (xdi l. 71).
2. **Missing marker keys.** `energy` is popped without a default (xdi l. 71); `computed_mu` is guaranteed by the marker, `energy` is not, so a group lacking it raises `KeyError`.
3. **Fixed time zone.** "Every entry … is an APS scan" (xdi l. 26) is an assumption about the data source; naive timestamps from elsewhere would be tagged `America/Chicago`.
4. **Back-fill keys.** Uses `element/symbol` and `edge/name` (xdi l. 97–98) rather than the mapped names; formats with different paths would not be back-filled.
5. **First-wins rule.** `setdefault` keeps the first edge energy found (xdi l. 101); conflicting values for the same transition are not detected.
6. **Timestamp types.** Only `str` values are parsed (xdi l. 81); `bytes` or NumPy strings stay unparsed.
7. **Name collisions** after `sanitize_entry_name` (xdi l. 73).
8. **Naming.** The file is named `oscars_xdi.py`, the class `OscarsXdiParser`, the vendor `"oscars"`; the docstring says "OSCARS-prepared XDI-derived". Confirm the intended spelling and source in the project docs.

## Scanner findings

No scanner run was performed for `pynxtools-xas`.
