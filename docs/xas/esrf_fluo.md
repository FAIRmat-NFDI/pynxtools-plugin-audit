# ESRF fluorescence-yield XAS HDF5 parser (`pynxtools-xas`)

## Source files reviewed

- `pynxtools_xas/parsers/esrf_fluo.py` — `EsrfFluoParser` and eight module-level helpers (289 lines).
- Inherited, **not supplied**: `_XASParser`, `ParsedSpectrum`, `VendorType` (`pynxtools_xas/parsers/base.py`); `parse_datetime` (`datetime_utils.py`); `sanitize_entry_name` (`hdf5_utils.py`). Their behaviour below is inferred from how `esrf_fluo.py` and its sibling parsers use them.
- Companion mapping, **not supplied**: `config_xas_fluo.json` (named at fluo l. 191).
- External: `h5py`, `numpy`.
- Project: [pynxtools-xas repository](https://github.com/FAIRmat-NFDI/pynxtools-xas).

**Line-number note:** References below refer to the file in the develop branch on 15th October 2026. `fluo l.` = `esrf_fluo.py`.

## At a glance

|                        |                                                                                                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Input format**       | ESRF Bliss/SPEC HDF5 (`.h5`, `.hdf5`) with one `NX_class="NXentry"` group per scan; fluorescence-yield XAS from ID21 (µXANES)                                                              |
| **Parser class**       | `EsrfFluoParser(_XASParser)` (fluo l. 188–288)                                                                                                                                             |
| **Reader**             | `h5py.File(file, "r")`, top-level groups iterated (fluo l. 208–209)                                                                                                                        |
| **Layouts recognised** | (1) *plotselect* group with `@signal`/`@axes` (fluo l. 98–117); (2) *avg* convention `instrument/avg_energy` + `instrument/avg_<element>_<line>` (fluo l. 82–151)                          |
| **Raw-data storage**   | none kept; arrays go straight into `ParsedSpectrum`                                                                                                                                        |
| **Output from parser** | `self._data[<sanitized entry name>] = ParsedSpectrum(energy [eV], intensity, metadata)`; metadata keys `element_name`, `edge_name`, `title`, `sample_name`, `start_time` (fluo l. 220–254) |
| **Config**             | `config_xas_fluo.json`; vendor `"esrf"` (fluo l. 191–193)                                                                                                                                  |
| **Target definition**  | `NXxas` (fluorescence yield; docstring fluo l. 23–26)                                                                                                                                      |
| **Project context**    | The only `pynxtools-xas` parser that *infers* element and edge from channel names and shares them between entries                                                                          |

**Standard behaviour.** `matches_file` is true if any top-level `NXentry` group yields a scan through `_extract_scan` (fluo l. 195–205). `_parse` repeats that extraction for each entry, reads title, sample name and start time, stores one `ParsedSpectrum` per entry, then fills missing element/edge from sibling entries (fluo l. 207–256, 258–288). The plotselect declaration is preferred over the avg convention because it is the file's own statement of what was plotted (fluo l. 12–16, 171–175).

**Comparison with other `pynxtools-xas` parsers.** `EsrfTransParser` and `OscarsXdiParser` use a fixed key map and `flatten_hdf5_group`; this parser looks up datasets by name patterns and never flattens the group.

## Formula / transformation

### Parser: energy axis to eV

**Location:** `_to_ev()` (fluo l. 72–79).

$$
E_{\mathrm{eV}} = \begin{cases} 1000\,E & \max|E| < 100 \\ E & \text{otherwise}\end{cases}
$$

Heuristic: ID21 records keV (edges at about 2–20 keV), so a maximum below 100 means keV. The rule is applied to both layouts (fluo l. 117, 185).

### Parser: emission line to absorption edge

**Location:** `_emission_line_to_edge()` (fluo l. 56–62). Only the shell letter is kept: `line[0].upper()`.

```text
avg_P_Ka1  -> element "P",  line "Ka1" -> edge "K"
avg_Fe_La1 -> element "Fe", line "La1" -> edge "L"
```

### Parser: element and edge from names

**Location:** regexes at fluo l. 46–50 and `_infer_element_edge()` (fluo l. 154–160).

| Pattern | Example | Result |
|---|---|---|
| `^avg_(?P<element>[A-Z][a-z]?)_(?P<line>[A-Z][a-z]?\d*)$` | `avg_P_Ka1` | P, K |
| `^(?P<element>[A-Z][a-z]?)(?P<line>K\|L\d?\|M)a?\d*_corr_norm\d*$` | `PKa_corr_norm0` | P, K |
| neither (e.g. `idet`) | `idet` | `None`, `None` |

### Parser: strongest avg channel

**Location:** `_select_avg_fluorescence()` (fluo l. 120–151). Among `avg_<element>_<line>` channels whose length equals the energy length, the one with the largest `nansum(|x|)` wins (fluo l. 140–147).

## Standard behaviour

1. **Entry selection.** Top-level object is an `h5py.Group` with `attrs["NX_class"] == "NXentry"` (fluo l. 199–200, 210–214).
2. **Plotselect first.** `_plotselect()` reads `plotselect.attrs["signal"]` and `["axes"]`, loads both datasets from the `plotselect` group, requires equal 1D shape, converts energy to eV, returns the signal name (fluo l. 98–117).
3. **Avg fallback.** `_find_energy()` tries `avg_energy`, `enmonound`, `enmono`, `energy` in `instrument/` then `measurement/`; a name may be a bare dataset or a group with a `data` child (fluo l. 53, 82–95). Then `_select_avg_fluorescence()` (see above).
4. **1D guard.** `_dataset_1d()` accepts only datasets with `ndim == 1` and length > 1 (fluo l. 65–69).
5. **Metadata.** `title`, `sample/name` and `start_time` are read when they are datasets; bytes are decoded as UTF-8 (fluo l. 224–248). `start_time` goes through `parse_datetime(text, tzinfo=Europe/Paris)` (fluo l. 248, 43).
6. **Store.** `self._data[sanitize_entry_name(group_name)]` (fluo l. 250–254).
7. **Propagation.** The first non-empty `element_name` and the first non-empty `edge_name` across all entries are copied into entries that lack them (fluo l. 258–288).

## Special behaviour

1. **Two layouts, one parser.** Entries in one file may use different layouts; averaged scans give element/edge, individual repeats (plotselect, diode signal) do not (fluo l. 259–266).
2. **Time zone is a fallback only.** The comment (fluo l. 41–42) says ID21 timestamps carry their own offset.
3. **Element and edge may stay `None`.** A bare diode signal names neither; the docstring says an ELN can override (fluo l. 25–26).
4. **Matching does the heavy lifting.** `matches_file` runs `_extract_scan` and therefore loads full 1D datasets (fluo l. 198–203).
5. **Errors are swallowed in matching.** Any exception returns `False` (fluo l. 204–205).

## Behaviour to investigate

1. **Edge granularity.** For `La1` the result is `"L"` (fluo l. 62), not a sub-shell edge such as `L3`. `specs_xy.py` maps `L` to `"L2,3"` and `M` to `"M4,5"` (xy l. 35); the NXDL edge enumeration should be checked against what this parser emits.
2. **Propagation mixes entries.** Element and edge are each taken from the first entry that has one (fluo l. 268–283). A file with scans of two different elements gives all entries the first element; element and edge may come from different entries.
3. **Bytes attributes.** `signal_name[0]` (fluo l. 111) assumes a `str` or an array of strings; a fixed-length `bytes` attribute would give an `int`. The `NX_class` comparison (fluo l. 200, 212) is also `== "NXentry"`; it fails if h5py returns `bytes`. Verify with real files.
4. **`axes == "."`.** An NXdata placeholder is not handled (fluo l. 112); `plot.get(".")` returns `None` and the scan is skipped silently.
5. **keV heuristic.** `np.nanmax(np.abs(energy)) < 100.0` (fluo l. 79) misreads a soft X-ray scan given in eV below 100 eV, and all-NaN input gives a `RuntimeWarning` and no conversion.
6. **Heuristic regexes.** `_CORR_FLUO` assumes the pattern `<El><K|L|M>a?…_corr_norm` (fluo l. 48–50); other names give `None`. `_AVG_FLUO` needs a capital line letter.
7. **Ties and shape.** Only channels with length equal to the energy axis count (fluo l. 138); ties go to the first (fluo l. 141).
8. **Repeated decode code.** Title, sample and start time each repeat the bytes/str handling (fluo l. 224–247); `str(value)` of an array gives its repr.
9. **Name collisions.** `sanitize_entry_name` may map different scan names (e.g. `1.1`, `1_1`) to the same key; later entries overwrite earlier ones (fluo l. 250).
10. **Unused return.** `_find_energy` returns a name that is never used (fluo l. 94, 180).
11. **Cost.** The file is read twice, once to match and once to parse.

## Scanner findings

No scanner run was performed for `pynxtools-xas`.
