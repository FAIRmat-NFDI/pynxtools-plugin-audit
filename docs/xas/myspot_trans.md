# BESSY II mySpot XAS HDF5 parser (`pynxtools-xas`)

## Source files reviewed

- `pynxtools_xas/parsers/myspot_trans.py` — `MySpotParser` and `_is_myspot_scan()` (85 lines).
- Inherited: `_XASParser`, `ParsedSpectrum`, `VendorType`; `parse_datetime`; `flatten_hdf5_group`, `sanitize_entry_name`.
- Inherited (companion mapping): `config_xas_trans.json` (shared; myspot l. 47).
- Project: [pynxtools-xas repository](https://github.com/FAIRmat-NFDI/pynxtools-xas).

**Line-number note:** References below refer to the file in the develop branch on 15th October 2026. `myspot l.` = `myspot_trans.py`.

## At a glance

| | |
|---|---|
| **Input format** | Bliss/SPEC-numbered HDF5 scans (`"9.1"`) from the BESSY II mySpot beamline, `NX_class="NXentry"` with `measurement/dcm_p_energy` |
| **Parser class** | `MySpotParser(_XASParser)` (myspot l. 44–84) |
| **Reader** | `h5py.File`; group flattened with `flatten_hdf5_group` (myspot l. 59–63) |
| **Fixed keys** | energy `measurement/dcm_p_energy`, intensity `measurement/normalised_roi_5` (myspot l. 30–31) |
| **Output from parser** | `self._data[<name>] = ParsedSpectrum(energy [eV], intensity, metadata)` (myspot l. 80–84) |
| **Config** | `config_xas_trans.json`, vendor `"myspot"` (myspot l. 47–49) |
| **Target definition** | `NXxas_trans` (shared config) |
| **Project context** | The only parser whose files carry **no** element, edge or sample identification; the config's attrs-then-`@eln` fallback supplies them (docstring myspot l. 10–13) |

**Standard behaviour.** `_is_myspot_scan` accepts `NXentry` groups with a 1D energy dataset longer than one point (myspot l. 34–41). `_parse` flattens each such group, converts the energy from keV to eV, takes `normalised_roi_5` as intensity, removes the uninformative SPEC title, converts the start time, and stores the spectrum (myspot l. 58–84). It does **not** call `map_metadata_fields`.

**Comparison with `EsrfTransParser` and `OscarsXdiParser`.** Those parsers translate flattened paths to short keys through `metadata_field_map`; here the raw flattened paths stay in the metadata and the config reads them directly.

## Formula / transformation

### Parser: energy to eV

**Location:** myspot l. 64–66.

$$
E_{\mathrm{eV}} = 1000\cdot E_{\mathrm{keV}}
$$

The dataset has no `units` attribute; the comment justifies keV with the Mo K-edge near 20 keV covered by this data.

### Parser: scan test

**Location:** myspot l. 34–41.

```python
isinstance(group, h5py.Group) and group.attrs.get("NX_class") == "NXentry"
and "measurement/dcm_p_energy" in group
and group[...].ndim == 1 and group[...].shape[0] > 1
```

## Standard behaviour

1. **Detect.** `any(_is_myspot_scan(g) for g in h5_file.values())`; any exception returns `False` (myspot l. 51–56).
2. **Iterate.** Skip groups that fail the scan test (myspot l. 60–62).
3. **Flatten.** `metadata = flatten_hdf5_group(group)` (myspot l. 63).
4. **Spectrum.** Pop `measurement/dcm_p_energy` (×1000) and `measurement/normalised_roi_5` (myspot l. 66–67).
5. **Drop title.** `metadata.pop("title", None)` so that the ELN title is reached by the config's fallback (myspot l. 69–72).
6. **Time.** A string `start_time` becomes `parse_datetime(…, tzinfo=Europe/Berlin)` (myspot l. 74–78, 28).
7. **Store.** `self._data[sanitize_entry_name(group_name)]` (myspot l. 80–84).

## Special behaviour

1. **ELN-dependent output.** Element, edge and sample must come from the ELN (myspot l. 10–13).
2. **Hard-coded ROI.** The intensity is `normalised_roi_5` in every file (myspot l. 31).
3. **Title removed on purpose.** SPEC writes `"Other seq_num -1"` on every scan (myspot l. 69–71).
4. **No key mapping.** `metadata_field_map` is not defined and `map_metadata_fields` is not called.

## Behaviour to investigate

1. **A `Group` as energy node breaks matching.** `group[_ENERGY_KEY].ndim` (myspot l. 39) raises `AttributeError` if the node is a group (Bliss sometimes stores `<name>/data`). Inside `matches_file` this is caught and the whole file is rejected; inside `_parse` it is not caught.
2. **`NX_class` comparison.** `== "NXentry"` (myspot l. 37) fails if h5py returns `bytes`; check with real files.
3. **Fixed ROI.** `normalised_roi_5` is hard-coded; a file using another ROI raises `KeyError` at myspot l. 67, after a successful match.
4. **Energy unit by assumption.** No attribute is read (myspot l. 64–66); the keV justification is only a comment.
5. **Other flattened keys unmapped.** Because no key map is applied, the shared config must refer to raw paths such as `measurement/...`; keep it in sync with `config_xas_trans.json`.
6. **Time zone.** `Europe/Berlin` is a fallback for offset-less strings (myspot l. 27–28, 76–78); `bytes` timestamps are not converted (myspot l. 75).
7. **Memory and cost.** The whole scan group is flattened though only two arrays are used.
8. **Name collisions** after sanitising (myspot l. 80).
9. **Implicit `NXentry` filter in `_is_myspot_scan`** skips non-NeXus scans silently.

## Scanner findings

No scanner run was performed for `pynxtools-xas`.
