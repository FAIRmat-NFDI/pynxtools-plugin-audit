# ESRF BM transmission EXAFS HDF5 parser (`pynxtools-xas`)

## Source files reviewed

- `pynxtools_xas/parsers/esrf_trans.py` — `EsrfTransParser` (85 lines).
- Inherited, **not supplied**: `_XASParser` (including `map_metadata_fields` and `_data`), `ParsedSpectrum`, `VendorType`; `parse_datetime`; `flatten_hdf5_group`, `sanitize_entry_name`. Their roles are inferred from usage (e.g. `flatten_hdf5_group(group)` returns a dict keyed by relative path, as `metadata.pop("instrument/Emono/value")` at trans l. 72 implies).
- Companion mapping, **not supplied**: `config_xas_trans.json` (shared with other transmission parsers).
- Project: [pynxtools-xas repository](https://github.com/FAIRmat-NFDI/pynxtools-xas).

**Line-number note:** References below refer to the file in the develop branch on 15th October 2026. `trans l.` = `esrf_trans.py`.

## At a glance

| | |
|---|---|
| **Input format** | ESRF BM beamline raw scan HDF5 (`.h5`, `.hdf5`); one top-level group per scan named by scan number (`"10.1"`), hundreds of channels each |
| **Parser class** | `EsrfTransParser(_XASParser)` (trans l. 33–84) |
| **Reader** | `h5py.File`; the whole group subtree is flattened by `flatten_hdf5_group` (trans l. 61–68) |
| **Output from parser** | `self._data[<sanitized name>] = ParsedSpectrum(energy [eV], intensity, metadata)` (trans l. 80–84) |
| **Key map** | `metadata_field_map` (trans l. 40–48) |
| **Config** | `config_xas_trans.json`, vendor `"esrf"` (trans l. 36–38) |
| **Target definition** | `NXxas_trans` (docstring trans l. 11) |
| **Project context** | Fixed-layout parser: scan identification via `instrument/ExafsElement`; all other channels stay available as metadata |

**Standard behaviour.** A top-level group is a scan if it contains `instrument/ExafsElement` (trans l. 50–58, 63–67). The parser flattens the group, pops the energy and the transmission signal out of the metadata, converts the start time, lets the base class apply the key map, and stores the spectrum.

**Comparison with `EsrfFluoParser`.** No layout detection: names are fixed, so a different export fails with `KeyError` instead of being skipped.

## Formula / transformation

### Parser: energy to eV

**Location:** trans l. 69–72.

$$
E_{\mathrm{eV}} = 1000\cdot E_{\mathrm{keV}}
$$

`instrument/Emono/value` is read as an array and always multiplied by 1000. The comment states that the dataset has HDF5 attribute `units = "keV"`; the attribute itself is not read.

### Parser: key map

| Output key | Source path | Line |
|---|---|---|
| `element_name` | `instrument/ExafsElement/Element` | 41 |
| `edge_name` | `instrument/ExafsElement/Edge` | 42 |
| `edge_energy` | `instrument/ExafsElement/EdgeEnergy` (eV per comment trans l. 71) | 43 |
| `sample_name` | `sample/name` | 44 |
| `i0_data` | `instrument/I0/data` | 45 |
| `itrans_data` | `instrument/I1/data` | 46 |
| `iref_data` | `instrument/I2/data` | 47 |

The energy (`instrument/Emono/value`) and the intensity (`instrument/mu_trans/data`) are popped before mapping (trans l. 72–73).

## Standard behaviour

1. **Detect.** Any top-level `h5py.Group` containing `"instrument/ExafsElement"` (trans l. 53–56); any exception returns `False` (trans l. 57–58).
2. **Iterate.** Skip non-groups and groups without the marker (trans l. 62–67).
3. **Flatten.** `metadata = flatten_hdf5_group(group)` (trans l. 68).
4. **Spectrum.** `energy = asarray(pop("instrument/Emono/value")) * 1000`; `intensity = asarray(pop("instrument/mu_trans/data"))` (trans l. 72–73).
5. **Time.** If `start_time` is a string, replace it by `parse_datetime(start_time, tzinfo=Europe/Paris)` (trans l. 74–78).
6. **Map.** `self.map_metadata_fields(metadata)` (trans l. 79).
7. **Store.** `self._data[sanitize_entry_name(group_name)]` (trans l. 80–84).

## Special behaviour

1. **All channels are kept in memory** as metadata; unused ones are ignored by the config (trans l. 8–13).
2. **Intensity is a precomputed channel** named `mu_trans`; I0, I1, I2 are carried alongside for the config (trans l. 45–47, 73).
3. **Time-zone fallback only.** Timestamps carry an offset (trans l. 27–29).
4. **Same config as other transmission parsers**, with `NXxas_trans` structure.

## Behaviour to investigate

1. **Unconditional ×1000.** The `units` attribute is documented (trans l. 69) but never checked; an export in eV is scaled wrongly without warning.
2. **No existence check for the fixed keys.** `matches_file` tests only `ExafsElement`, while `_parse` pops `instrument/Emono/value` and `instrument/mu_trans/data` (trans l. 72–73); a scan without them raises `KeyError` and aborts the whole file.
3. **Channel naming assumption.** `I1` is mapped to `itrans` and `I2` to `iref` (trans l. 46–47); confirm against the ESRF channel definitions.
4. **Memory.** Flattening reads every array of every scan before use (trans l. 68).
5. **`mu_trans` semantics.** The name suggests a computed absorption coefficient; whether it is `ln(I0/I1)` or another quantity is not stated in the file.
6. **Mixed time handling.** The string check `isinstance(start_time, str)` (trans l. 75) misses a `bytes` or NumPy string value.
7. **Name collisions** after `sanitize_entry_name` (trans l. 80).
8. **Broad `except Exception`** in `matches_file` hides unreadable-file causes (trans l. 57).

## Scanner findings

No scanner run was performed for `pynxtools-xas`.
