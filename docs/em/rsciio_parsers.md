# rosettasciio-backed parsers (`pynxtools-em`)

## Source files reviewed

- `src/pynxtools_em/parsers/rsciio_velox.py` — `RsciioVeloxParser` (428 lines).
- `src/pynxtools_em/parsers/rsciio_gatan.py` — `RsciioGatanParser` (316 lines).
- `src/pynxtools_em/parsers/rsciio_msa.py` — `RsciioEmsaParser` (237 lines).
- `src/pynxtools_em/parsers/rsciio_mrc.py` — `RsciioMrcParser` (843 lines).
- `src/pynxtools_em/parsers/rsciio_bruker.py` — `RsciioBrukerParser` (73 lines).
- Imported, **not** reviewed: `configurations/rsciio_velox_cfg.py`, `configurations/rsciio_gatan_cfg.py`, `utils/velox_utils.py`, `utils/gatan_utils.py`, `utils/rsciio_mrc_utils.py`, `utils/rsciio_hspy_utils.py` (`all_req_keywords_in_dict`), `utils/string_conversions.py` (`string_to_number`), `methods/ebsd.py` (`has_hfive_magic_header`), `concepts/mapping_functors_pint.py`.
- Project: [pynxtools-em, branch develop](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop), parsers in [`src/pynxtools_em/parsers`](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop/src/pynxtools_em/parsers).

**Line-number note:** References below refer to the files in develop branch on 14th October 2026. In the general sections `l.` is given together with the file; in per-parser sections `l.` refers to that parser's file.

## At a glance

|                             | Velox                                                                                 | Gatan                                                                            | MSA                                                       | MRC                                           | Bruker                       |
| --------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------- | ---------------------------- |
| **File**                    | `rsciio_velox.py`                                                                     | `rsciio_gatan.py`                                                                | `rsciio_msa.py`                                           | `rsciio_mrc.py`                               | `rsciio_bruker.py`           |
| **Class**                   | `RsciioVeloxParser` (l. 55)                                                           | `RsciioGatanParser` (l. 48)                                                      | `RsciioEmsaParser` (l. 50)                                | `RsciioMrcParser` (l. 42)                     | `RsciioBrukerParser` (l. 27) |
| **Format**                  | ThermoFisher Velox `.emd` (HDF5)                                                      | Gatan DM `dm2/dm3/dm4`                                                           | (E)MSA `.msa`                                             | MRC image stack plus sidecar                  | Bruker `.bcf`                |
| **rsciio reader**           | `emd.file_reader` (l. 101)                                                            | `digitalmicrograph.file_reader(lazy=False, order="C", optimize=True)` (l. 77–79) | `msa.file_reader(lazy=False, encoding="latin-1")` (l. 82) | `mrc.file_reader` (l. 86)                     | `bruker.file_reader` (l. 53) |
| **Constructor input**       | `file_path: str`                                                                      | `file_path: str`                                                                 | `file_path: str`                                          | `file_paths: list[str]` (l. 47)               | `file_path: str`             |
| **Extension / magic check** | `.emd` + HDF5 magic (l. 96–99)                                                        | suffix `dm2/dm3/dm4` (l. 74)                                                     | `.msa` (l. 79)                                            | `.mrc` (l. 58, 69, 76)                        | none                         |
| **Version gate**            | `Core/MetadataDefinitionVersion` and `Core/MetadataSchemaVersion` (l. 72–81, 114–130) | none (TODO l. 91)                                                                | none (TODO l. 65, 94)                                     | none                                          | none                         |
| **Metadata mapping**        | config tables + hand-coded lenses/apertures (l. 166–267)                              | config tables (l. 130–143)                                                       | hand-coded start time and beam voltage (l. 141–165)       | hand-coded from sidecar (l. 624–663)          | none (stub, l. 71–73)        |
| **Data written as**         | `spectrumID`, `imageID` or `DATA[data1]` (l. 300–360)                                 | same, with source annotation (l. 184–244)                                        | `spectrumID[spectrum1]/spectrum_0d` (l. 193)              | `imageID[imageN]/stack_2d` (l. 573, 677, 784) | nothing                      |
| **Status**                  | complete                                                                              | complete                                                                         | single 1D spectrum only                                   | partial (sidecar metadata mostly not written) | placeholder                  |

## General structure of an RSCIIO-backed parser

All five classes share one skeleton, each following the pattern *constructor → `check_if_supported()` → `parse()` → `parse_content()` → `process_event_data_em_*()`*.

1. **Constructor.** Guard `if file_path:` (Velox l. 61, Gatan l. 54, MSA l. 56, Bruker l. 33), clamp `entry_id` (`entry_id if entry_id > 0 else 1`), store `verbose` (default `DEFAULT_VERBOSITY`), initialise an `id_mgn` counter dict, call `check_if_supported()`, log at debug level if unsupported. Without a path: warning and `supported = False`. MRC deviates (list of paths, see below).
2. **`check_if_supported()`.** Cheap format gate (extension and for Velox the HDF5 magic number), then the *full* rsciio read into `self.objs` — rosettasciio has no "peek" mode here, so detection already loads the data. Out-of-memory is an open TODO in Velox (l. 102–106), Gatan (l. 80–81) and Bruker (l. 54).
3. **rsciio object contract.** `file_reader` returns a list of dicts. The parsers check for `data`, `axes`, `metadata`, `original_metadata` and (Velox, Gatan) `mapping` with `all_req_keywords_in_dict` (Velox l. 107–112, Gatan l. 83–89, MSA l. 83–93). Used keys: `obj["data"]` (ndarray), `obj["axes"]` (list of dicts with `offset`, `scale`, `units`, `size`), `obj["metadata"]` (HyperSpy-style, flattened, `General/title` required), `obj["original_metadata"]` (vendor tags, flattened).
4. **`parse()`.** If `supported`: open the file, compute sha256 with `get_sha256_of_file_content`, log it, call `parse_content()` (Velox l. 142–151, Gatan l. 101–110, MSA l. 109–118, Bruker l. 60–69; MRC l. 544–560 with mode dispatch).
5. **`parse_content()`.** Loop over `self.objs`, skip non-dict or incomplete objects, hand each to `process_event_data_em_data()` (Velox l. 153–164, Gatan l. 112–128, MSA l. 120–139).
6. **`process_event_data_em_data()`.** Require `General/title`, compute the *unit combination* with a vendor-specific helper, pick NXdata flavour, write the signal and axes into the template under `/ENTRY[entry{n}]/measurement/eventID[event{m}]/…`.
7. **`process_event_data_em_metadata()`.** Flatten `original_metadata` with `fd.FlatDict(…, "/")` and push it through `add_specific_metadata_pint(cfg, flat, identifier, template)` for each config table (Velox l. 249–266, Gatan l. 137–142), or write hand-coded paths (Velox lenses/apertures, MSA, MRC).
8. **Template values.** Arrays go as `{"compress": array, "strength": DEFAULT_COMPRESSION_LEVEL, "chunks": prioritized_axes_heuristic(array, np.arange(array.ndim))}`; scalars as plain values with `/@units` strings produced by pint (`f"{ureg.Unit(units)}"`).
9. **Source annotation.** `annotate_information_source(src, trg, file_path, checksum, template)` writes `PROCESS[process]/input/{file_name, checksum, algorithm, context}` (Velox l. 269–279, Gatan l. 145–155). It is active in Gatan, commented out in Velox (l. 301–307, 321–327, 341–347), absent in MSA (`# TODO source annotation`, l. 192) and MRC.

## Formula / transformation (shared)

### Axis arrays

Velox l. 371–424, Gatan l. 257–315, MSA l. 213–232, MRC l. 585–610 (and twins).

$$
x_k = o + k\cdot s,\qquad k=0,\dots,N-1
$$

`o = axis["offset"]`, `s = axis["scale"]`. `N = np.shape(obj["data"])[idx]` in Velox/Gatan, `axis["size"]` in MSA/MRC. dtype `float32` in Velox, Gatan and MSA, `float64` in MRC; `uint32` for the MRC `indices_image` axis (l. 613–616).

### Axis index attribute

`@AXISNAME_indices[<name>_indices] = len(axis_names) - 1 - idx` (Velox l. 365–368, Gatan l. 251–254, MRC l. 585–589). MSA writes `0` for its single axis (l. 210). Both Velox (l. 363–364) and Gatan (l. 254) carry a TODO that the reversed index must be checked with non-square arrays; the Gatan comment at l. 244 notes that, unlike Nion, the axis names are not reversed. In the MRC parser `axis_names = ["indices_image", "axis_j", "axis_i"]` is in array-dimension order and the same formula is applied (l. 582–589).

### Energy detection for the long name

`ureg.Quantity(units).to_base_units().units == "kilogram * meter ** 2 / second ** 2"` → `Energy (<unit>)` else `Coordinate along <x>-axis (<unit>)` (Velox l. 414–424, Gatan l. 305–312). MSA hard-codes electron volt (l. 216, 229–232). MRC always writes the coordinate label (l. 605–610).

### Unit combination and NXdata selection

`velox_image_spectrum_or_generic_nxdata(axes)` (Velox l. 289) and `gatan_image_spectrum_or_generic_nxdata(axes)` (Gatan l. 169) return a key that is tested against `*_WHICH_SPECTRUM` → `(group name, axis_names)` and `*_WHICH_IMAGE`; everything else becomes `DATA[data1]` with names `axis_i … axis_n` cut with `len(unit_combination.split("_"))` (Velox l. 358–360, Gatan l. 242–244). MRC uses `get_dimension_analysis_keyword(obj["axes"])` and accepts only `"dimensionless;meter;meter"` with `ndim == 3` (l. 565–571, 669–675, 776–782). The helper modules were not part of the upload.

## Standard behaviour

1. **Gate.** Suffix/magic check, then `file_reader`; rsciio exceptions caught: `OSError`, `FileNotFoundError` (all), plus `ValueError` in Velox (l. 138) and MSA (l. 105).
2. **Validate objects.** Each object must be a `dict` with the required keys; indices of acceptable objects are stored (`obj_idx_supported`, Velox l. 131, MSA l. 100; Gatan keeps a local list, l. 84, 92).
3. **Support decision.** `supported = True` if at least one object passes (Velox l. 134–137, Gatan l. 95–96, MSA l. 103–104).
4. **Checksum.** sha256 of the whole file, logged only (Velox l. 145–149, Gatan l. 103–107, MSA l. 111–115).
5. **Per-object processing.** Title check, unit combination, group selection, signal + axes writing as described above.
6. **Metadata.** Called from inside the data function (Velox l. 426, MSA l. 234), or from `parse_content` before the data function (Gatan l. 123).
7. **Counters.** `id_mgn["event_id"]` identifies the `eventID` group; Velox increments at the end of a successful object (l. 427), Gatan inside the data function (l. 178) and again in `parse_content` (l. 125).

## Special behaviour

1. **Several rsciio objects per file** are written as several events (Velox, Gatan); MSA rejects files with more than one object (l. 84–88) or with a non-1D axis list (l. 95–99); MRC rejects `len(objs) != 1` (l. 87–91).
2. **`mapping`** is required for Velox and Gatan only.
3. **Velox version gate** accepts only `Core/MetadataDefinitionVersion == "7.9"` and `Core/MetadataSchemaVersion == "v1/2013/07"` (l. 72–81).
4. **MRC modes.** `self.config["mode"]` ∈ `em_mrc_only`, `et_mrc_mdoc`, `et_mrc_rawtlt`, `et_mrc_shifts`, `em_mrc_xml`; later checks overwrite the mode set by earlier ones (l. 97, 105–107, 331, 385, 487, 541).
5. **Memory release.** Only `process_data_mode_em_mrc_only` clears `self.objs` and calls `gc.collect()` (MRC l. 836–839).
6. **Unused counters.** `id_mgn` keys `event_img`, `event_spc`, `roi`, `eds_img` (Velox l. 65–71) and `event_spc`, `roi` (MSA l. 60–64) are never read.

## Behaviour to investigate

1. **Detection loads everything.** Every parser reads the full file in the constructor (see general structure 2); the content stays in `self.objs` for the lifetime of the object.
2. **Event counter in Gatan.** `parse_content` writes metadata and data for event *N* (l. 123–124), the data function increments to *N+1* (l. 178) and `parse_content` increments again (l. 125): event ids run 1, 3, 5, … and objects that return early (l. 165, 171) still advance by one.
3. **Axis-index formula** (see Formula) is only exercised with the TODO'd assumption; verify with a non-square image and a spectrum image in Velox, Gatan, MRC.
4. **`split("_")` on the unit combination** (Velox l. 359, Gatan l. 243) while other code splits `;` — see the same question for Nion (`nxs_nion.md`, behaviour 10).
5. **Duplicated blocks.** Gatan l. 263–285 and l. 286–315 build the same `float32` axis twice; MRC has three nearly identical writer functions (l. 562–665, 667–763, 773–841; comment at l. 843).
6. **Different exception sets.** Gatan and Bruker do not catch `ValueError` from rsciio; Velox does not catch `KeyError` from the version lookup (see Velox 2).
7. **`dm5`.** See Gatan 1.
8. **Source annotation** is inconsistent across parsers (see general structure 9); output provenance therefore differs by format.

---

## Parser: `rsciio_velox.py` — `RsciioVeloxParser`

### At a glance

| | |
|---|---|
| **Input** | ThermoFisher/FEI Velox `.emd`, HDF5 (l. 95–99) |
| **Reader** | `rsciio.emd.file_reader` (l. 101) |
| **Version gate** | `self.version["trg"]` holds accepted values (l. 72–81); `self.version["src"]` is initialised to `None` and never filled |
| **Metadata** | Hand-coded optics (l. 181–247) + config tables `VELOX_STATIC_ENTRY_NX`, `VELOX_STATIC_EBEAM_NX`, `VELOX_DYNAMIC_SCAN_NX`, `VELOX_DYNAMIC_VARIOUS_NX`, `VELOX_DYNAMIC_OPTICS_NX` (l. 249–256), `VELOX_STATIC_FABRICATION_NX`, `VELOX_DYNAMIC_STAGE_NX`, `VELOX_DYNAMIC_EBEAM_NX` (l. 258–266) |
| **Data** | Spectrum / image / generic (l. 300–360), axes (l. 362–424), metadata at the end (l. 426), `event_id += 1` (l. 427) |

### Formula / transformation

**Lens settings (l. 181–214).** For each name in `C1, C2, C3, Diffraction, Gun, Intermediate, MiniCondenser, Lorentz, Objective, Projector1, Projector2`: `Optics/<name>LensIntensity` → `lensID[lensN]/power_setting` with `@units = "%"` except for `Gun` (l. 197–203); `Optics/<name>LensMode` → `lensID[lensN]/mode` (l. 205–208); the lens index advances if either key exists (l. 210–214).

**Apertures (l. 216–247).** `C1…C3 Aperture` → micrometre quantity, `apertureID[apertureN]/setting` (l. 223–233); `OBJ`, `SA` → `apertureID[apertureN]/status` (l. 240–244).

### Standard behaviour

1. `.emd` suffix and HDF5 magic (`has_hfive_magic_header`, l. 96–99).
2. `emd.file_reader`, required keys, version check (l. 101–131).
3. For each object `process_event_data_em_data` (l. 161) writes the group and the axes, then calls `process_event_data_em_metadata` (l. 426).
4. Metadata values are converted with `string_to_number` over the whole flat dict (l. 170–171).
5. Identifier for the config tables is `[entry_id, event_id, 1]` (l. 168).

### Special behaviour

1. **Version check is permissive.** An object without `Core/MetadataDefinitionVersion` skips the entire version check and is accepted (l. 114 guards l. 118–130; `append` at l. 131).
2. **Annotations disabled** (l. 301–307, 321–327, 341–347).
3. **Lens name and aperture name paths** omit the event group: `/ENTRY[entryN]/measurement/instrument/ebeam_column/lensID[…]/name` (l. 211–213, 234–236, 245–247), while the settings are under `…/measurement/eventID[eventM]/instrument/ebeam_column` (l. 178).
4. **`@units` for apertures** is the pint `Unit` object itself (`qnt.units`, l. 231–233), not a string as everywhere else.
5. **`Gun`** lens intensity has no unit (l. 202).

### Behaviour to investigate

1. **Group mismatch for names.** See special 3: names land in a different NXinstrument group than the matching settings; check how the NXem validator treats this.
2. **`KeyError` on schema version.** `original_metadata["Core/MetadataSchemaVersion"]` (l. 124–127) is accessed without a membership test after the definition key was found.
3. **Aperture index collision.** The `OBJ`/`SA` loop (l. 240–247) never increments `aperture_idx`; both write to the same index and `SA` overwrites `OBJ` (and the name).
4. **In-place edit while iterating.** `original_metadata[keyword] = string_to_number(value)` inside `for keyword, value in original_metadata.items()` (l. 170–171).
5. **`self.version["src"]`** is never populated (l. 77–80); the log lines at l. 115–125 are the only record.
6. **Hard-coded version list** has a single accepted value per key (l. 72–81); newer Velox exports are skipped silently (`continue`, l. 122, 130).
7. **Id handling.** Metadata uses the event id before it is incremented (l. 426–427); early returns (l. 286, 291) skip both.
8. **Static tables** `VELOX_STATIC_*` use the dynamic identifier, so they are re-written per event.
9. **`axis_names` for generic data** are not reversed (l. 358–360, "TODO mind order").

---

## Parser: `rsciio_gatan.py` — `RsciioGatanParser`

### At a glance

| | |
|---|---|
| **Input** | Gatan Digital Micrograph `.dm2/.dm3/.dm4` (l. 74) |
| **Reader** | `rsciio.digitalmicrograph.file_reader(lazy=False, order="C", optimize=True)` (l. 77–79) |
| **Metadata** | `GATAN_STATIC_VARIOUS_NX`, `GATAN_DYNAMIC_STAGE_NX`, `GATAN_DYNAMIC_VARIOUS_NX` via `add_specific_metadata_pint`, identifier `[entry_id, event_id, 1]` (l. 137–142) |
| **Data** | l. 157–316 (see below) |
| **Source annotation** | Active (l. 145–155, 185–191, 205–211, 225–231) |

### Formula / transformation

Spectrum: `…/spectrumID[spectrum1]/<name>/intensity` with `@long_name = "Counts"` (l. 192–203). Image: `…/imageID[image1]/<name>/real` with `@long_name = "Real part of the image intensity"` (l. 212–223). Generic: `…/DATA[data1]/data` (l. 232–244). Axis names for generic data are *not* reversed (comment l. 244, example file `241.a2c338…dm4` quoted at l. 245–246). Axis arrays and energy detection as in the shared section (l. 257–315).

### Standard behaviour

1. Suffix check (l. 74), `file_reader` (l. 77–79), required keys including `mapping` (l. 83–89), at least one acceptable object (l. 95–96).
2. `parse_content` loops over objects: optional verbose dump of `original_metadata` (l. 120–122), metadata (l. 123), data (l. 124), counter (l. 125).
3. Title check on `metadata["General/title"]` (l. 162–165); empty unit combination returns (l. 170–171).
4. `event_id` is incremented right after the prefix is built (l. 177–178).
5. Source annotation per group; `src` is always `""` here so no `context` line (l. 185–191, 153–154).

### Special behaviour

1. **Suffix test has no dot** (`("dm2", "dm3", "dm4")`, l. 74), so any filename ending in these letters passes.
2. **Version logic missing** (TODO l. 91; the commented flatten at l. 90).
3. **Explicit "no reversal"** of the generic axis names (l. 244).
4. **Axis arrays** for `units == ""` and for non-empty units are built identically; only labels differ (l. 263–285, 286–315).
5. **Memory.** `lazy=False` loads full arrays; TODO about lazy loading at l. 80–81.

### Behaviour to investigate

1. **`dm5` message vs. check.** The warning at l. 67–69 says "Gatan DM(3,4,5) file" while the check accepts `dm2/dm3/dm4` only.
2. **Double increment** of `event_id` (see shared investigate 2).
3. **`ValueError`** from rsciio not caught (l. 97).
4. **Axis-index TODO** (l. 254).
5. **Annotation `abbrev`** is `PROCESS[process]/input` and the `trg` passed is the group prefix (l. 185–191); every object writes a new annotation under its own group — verify that groups do not collide when `event_id` jumps.
6. **Unused `self.version`** (l. 59).
7. **Unit-less label** for generic data uses the raw axis name (l. 281–285).

---

## Parser: `rsciio_msa.py` — `RsciioEmsaParser`

### At a glance

| | |
|---|---|
| **Input** | EMSA/MSA spectrum, one 1D spectrum per file |
| **Reader** | `rsciio.msa.file_reader(lazy=False, encoding="latin-1")` (l. 82) |
| **Gate** | suffix `.msa` (l. 79), one object (l. 84–88), one axis (l. 95–99) |
| **Metadata** | `DATE`+`TIME` → `start_time` (l. 148–152); `BEAMKV…` → electron source voltage (l. 154–162) |
| **Data** | `…/eventID[eventN]/spectrumID[spectrum1]/spectrum_0d` with `intensity` and `axis_energy` (l. 193–232) |

### Formula / transformation

**Counts dtype (l. 196–200).** `uint64` if every channel value `is_integer()` and `≥ 0`, otherwise `float64`.

**Beam voltage (l. 157–161).** $V = \mathrm{BEAMKV}\;[\mathrm{kV}] \times 1000$ via pint (`kilovolt → volt`), written with `@units`.

**Start time (l. 148–152).** `datetime.strptime("<DATE> <TIME>", "%d-%b-%Y %H:%M").isoformat()`, naive.

**Energy axis (l. 213–232).** Standard axis formula with `offset`, `scale`, `size` from `obj["axes"][0]`, `float32`, units hard-coded `eV` (l. 216).

### Standard behaviour

1. Suffix, read, single-object and 1D checks (l. 79–104).
2. `parse_content` loops (l. 120–139) and calls `process_event_data_em_data` (l. 136).
3. Title check (l. 169–172); `XUNITS` and `NCOLUMNS` must exist in `original_metadata` (l. 174–179).
4. Write `title`, `@signal`, `intensity`, `@long_name = "Counts"`, `@axes = ["axis_energy"]`, index `0` (l. 193–211).
5. Axis and units (l. 213–232), then metadata (l. 234).

### Special behaviour

1. **Only one spectrum.** The comment at l. 236 reiterates this; `event_id` is never incremented.
2. **Encoding** `latin-1` fixed (l. 82).
3. **`proper_counts`** helper is disabled inside a module-level string (l. 38–47).
4. **Values of `XUNITS` and `NCOLUMNS` are not checked** (TODO l. 180).
5. **No source annotation** (TODO l. 192).

### Behaviour to investigate

1. **Suffix vs. docstring.** The module docstring names `*.emsa` (l. 18) but the check is `.endswith(".msa")` (l. 79); a `.emsa` file does not match.
2. **Broken beam-voltage path.** l. 156: `/ENTRY[entry{event_id}]/measurement/eventID[event{event_id}]instrument/…` uses `event_id` for the entry and lacks the slash before `instrument`.
3. **Hard-coded eV** ignores `XUNITS` (l. 216).
4. **Locale-dependent `%b`** in `strptime` (l. 151); a malformed date raises `ValueError` outside any `try`.
5. **Docstring copy-paste.** `process_event_data_em_data` says "Velox-specifically" (l. 168).
6. **`dtype` test** iterates in Python over all channels (l. 199).
7. **In-place conversion** `original_metadata[key] = string_to_number(value)` while iterating (l. 145–146).
8. **Metadata order.** Metadata is written after the data (l. 234), and only after the early returns at l. 171–179.

---

## Parser: `rsciio_mrc.py` — `RsciioMrcParser`

### At a glance

| | |
|---|---|
| **Input** | `.mrc` stack plus up to two sidecars: `.mrc.mdoc` (SerialEM), `.rawtlt`, `.xml` (FEI) in slot 1; `.shifts` in slot 2 (l. 56, 68–74) |
| **Reader** | `rsciio.mrc.file_reader` (l. 86); sidecars by hand (`re`, `xmltodict`, plain `open`) |
| **Special constructor** | `file_paths: list[str]` (l. 47); only parser that combines files |
| **Modes** | `em_mrc_only`, `et_mrc_mdoc`, `et_mrc_rawtlt`, `et_mrc_shifts`, `em_mrc_xml` (l. 97, 331, 385, 487, 541) |
| **Dispatch** | l. 552–559 |
| **Data** | `…/eventID[event1]/imageID[imageN]/stack_2d` (l. 573, 677, 784) |
| **Context** | Electron tomography tilt series and plain image stacks |

### Formula / transformation

**Unit conversions in sidecar parsing.**

| Quantity | Source → target | Lines |
|---|---|---|
| `PixelSpacing` (series) | Å → m | 137–150 |
| `Voltage` (series) | kV → V | 144–150 |
| `ImageShift` | Å → m | 253–276 |
| `StagePosition` (x, y, z) | nm → m | 277–298 |
| `TiltAngle`, `RotationAngle` | degree | 208, 222–226 |
| `Defocus` | nm | 220 |
| `ExposureTime` | s | 227 |
| `.shifts`: `TotalShiftDelta{X,Y}`, `ExcessShiftDelta{X,Y}` | µm → nm | 424–429, 466–475 |
| `.shifts`: `*ShiftDefocus` | µm → m | 430–432, 476–480 |

**Image-index axis (l. 611–616).** `indices_image = 0 … N-1` as `uint32`.

**Per-image arrays (l. 634–663).** For each key a column of length `N` (1 column) or `N × n_columns` array from the per-image `Quantity.magnitude`; written under `stageID[stage]/tilt1`, `optics/magnification`, `optics/defocus`, `optics/rotation`, `ebeam_column/scan_controller/dwell_time`, `optics/image_shift`, `stageID[stage]/position` (l. 625–633).

### Standard behaviour

1. **Pair files.** One path: must end `.mrc`. Two or three: compare stems of paths 0 and 1, then sort by suffix into `mrc_txt[0..2]` (l. 57–74).
2. **Open the MRC.** `mrc.file_reader`, require exactly one object, store `number_of_images = axes[0]["size"]`, set `mode = "em_mrc_only"` (l. 76–102).
3. **Probe sidecars** in this order: SerialEM mdoc (l. 105, 115–332), "other" tomography with rawtlt / shifts (l. 106, 334–491), FEI XML (l. 107, 493–542). Return values are ignored; success is recorded in `config["mode"]`.
4. **Supported** if `config["mode"]` exists (l. 108–113).
5. **mdoc parsing** is index-based: series header lines 0–5 hold `PixelSpacing`, `Voltage`, `Version`, `ImageFile`, `ImageSize`, `DataMode` (l. 135–183); per-image blocks start at `[ZValue = n]` (l. 190–203); per block scalars, `ImageShift`, `StagePosition` + `StageZ` (l. 205–298); required keys `TiltAngle, Magnification, PixelSpacing, SpotSize, ProbeMode, Defocus, RotationAngle, ExposureTime` (l. 313–329).
6. **rawtlt** (no `.shifts`): read floats from the file, require `len(tilts) == number_of_images`, store `TiltAngle` (l. 349–385).
7. **shifts**: `cp1252`, verify three header lines and two section headers (l. 389–404, 435–449), parse the "total" and "excess" tables with a four-float regex (l. 406–486).
8. **FEI XML**: `xmltodict`, require `Acquisition/Info` and `Acquisition/Images/Image`, store `TimeStamp` per image (l. 500–539).
9. **Write** the stack with `intensity`, `@axes = ["indices_image", "axis_j", "axis_i"]` and calibrated `axis_j`/`axis_i` (l. 575–622, 679–726, 787–834).

### Special behaviour

1. **Graceful downgrade.** A failed sidecar check returns `False`; the mode stays at `em_mrc_only` and the stack is still written (l. 97, 380–384, 400–404).
2. **Shifts beat rawtlt.** If a `.shifts` file is given, the rawtlt branch is skipped (l. 349, 386).
3. **`et_mrc_shifts` is written like rawtlt:** only `TiltAngle` is output (l. 554–555, 729–731); shift and defocus values are parsed but not written.
4. **FEI mode writes the stack only** (l. 765–771, "ADD METADATA").
5. **mdoc series metadata** (`PixelSpacing`, `Voltage`, `Version`, `ImageFile`, `DataMode`, `ImageSize`) are kept in `series_meta_data` but never written. Only seven per-image keys reach the template (l. 625–633).
6. **Parsed but unused per-image keys:** `SpotSize`, `ProbeMode`, `Binning`, `CameraIndex`, `MagIndex`, `LowDoseConSet`, `CountsPerElectron` (l. 218–238).
7. **Title** differs: "Electron tomography tilt series" (l. 574, 678) vs. "Image stack" (l. 786).
8. **Event id fixed** to `event1` (l. 573, 677, 784); `id_mgn` is never used.
9. **Memory.** `process_data_mode_em_mrc_only` (and thereby `…_fei`) deletes the objects after writing (l. 836–839); `parse()` cannot be called twice in that mode.

### Behaviour to investigate

1. **Lone `.mrc` file.** For `file_paths = [x.mrc]`, `check_if_mrc_other_electron_tomography` passes its guards (l. 337–347) and reaches `open(file_paths[1], "rb")` with `file_paths[1] == ""` (l. 349–352); this is not inside a `try`. As written the plain `em_mrc_only` mode looks unreachable and the constructor raises `FileNotFoundError`. Test with a bare `.mrc`.
2. **Indentation of the writer loop.** In `process_data_mode_et_mrc_mdoc` the block `template[path] = {…}` … `del numpy_array` (l. 654–663) is at the level of `if key in self.image_meta_data[0]` (l. 634), i.e. outside it. If a key (e.g. `ImageShift`, optional in mdoc) is absent, the loop reuses a deleted `numpy_array` and `self.image_meta_data[0][key]` raises. Same pattern in the rawtlt writer (l. 752–761) but there only `TiltAngle` is present.
3. **FEI single image.** `xmltodict` returns a dict, not a list, when `Image` occurs once; `enumerate(...)` (l. 523–525) then iterates keys and `image_dict["ImageID"]` fails with `TypeError`.
4. **Hard-coded line numbers** for the mdoc header (l. 135–183) break with any other SerialEM layout; blocks are only accepted if `ZValue` runs 0,1,2,… (l. 196).
5. **Unanchored regexes** `re.search(key + r"\s*=\s*" + rgx, line)` (l. 146, 166, 243, 264, 284) also match keys that merely end with the same text (e.g. `TargetDefocus` for `Defocus`); the first match per block wins.
6. **`data_type` ignored** in the scalar loop (l. 241–248): values are converted by `string_to_number`, not by the declared dtype.
7. **`isinstance(data_type, str)`** (l. 168) is always `False` because `data_type` is a type, not an instance.
8. **Stale variable in warnings.** l. 183 (`key` from the previous loop) and l. 327 (`key` instead of `required`) log the wrong name; l. 183 also does not `return False`.
9. **Stage units.** The author questions the nm assumption for `StagePosition` (`# are both stage values XY and Z in nanometer ???`, l. 295) and the units of `PixelSpacing` / `Voltage` (`# ???`, l. 143–144).
10. **Missing stage defaults.** `StagePosition` is zero-filled if absent (l. 278–298) and then treated as present.
11. **Pairing test.** `file_paths[1][0 : file_paths[0].rfind(".")]` and `…rfind("_")` (l. 62–66) slice the *second* path with indices of the *first*; with no `_` the slice is `[:-1]`. The third path is never compared.
12. **`.shifts` suffix case.** `.lower()` at l. 349 but `endswith(".shifts")` without it at l. 386.
13. **Uncaught `IndexError`** when a `.shifts` file is shorter than the expected line offsets (l. 400, 414, 445, 453).
14. **Encodings differ:** utf-8 for mdoc (l. 127) and rawtlt (l. 354), cp1252 for shifts (l. 389), utf-8 for XML (l. 500).
15. **Axis-index formula** for a stack (n, y, x): `indices_image` gets index 2 and `axis_i` index 0 (l. 586–589); compare with the array layout.
16. **Duplicated writers** (l. 562–665, 667–763, 773–841).
17. **Docstrings** of `check_if_mrc_other_electron_tomography`, `check_if_mrc_fei`, `process_data_mode_em_mrc_fei`, `process_data_mode_em_mrc_only` are `"""TODO"""` (l. 335, 494, 766, 774).

---

## Parser: `rsciio_bruker.py` — `RsciioBrukerParser`

### At a glance

| | |
|---|---|
| **Input** | Bruker `.bcf` (docstring l. 18, 28) |
| **Reader** | `rsciio.bruker.file_reader` (l. 53) |
| **Output** | None: `parse_content` returns the template unchanged (l. 71–73) |
| **Gate** | none beyond `file_reader` succeeding (l. 53–55) |

### Standard behaviour

1. Constructor with `file_path` guard; `objs`, `version`, `supported` initialised (l. 33–39).
2. `check_if_supported`: read the file, set `supported = True` (l. 49–55); `OSError`/`FileNotFoundError` → warning (l. 56–58).
3. `parse`: sha256 and log (l. 62–67), `parse_content` (l. 68).

### Special behaviour

1. **Placeholder.** Everything up to `parse_content` is functional, the translation to NeXus does not exist.
2. **No extension test**, unlike all other RSCIIO parsers.
3. **TODO out-of-memory** at l. 54.

### Behaviour to investigate

1. **Message mismatch.** The warning says "needs Bruker HDF5 file" (l. 46); the class handles BCF.
2. **Any path is routed** to `bruker.file_reader`; non-BCF content raises rsciio exceptions other than `OSError`/`FileNotFoundError`, which are not caught (l. 56).
3. **Cost without output.** The file is fully read twice (read + checksum) and nothing is written.
4. **Unused attributes:** `self.version` (l. 38), `self.objs` after the constructor.

## Scanner findings

No scanner run was performed for `pynxtools-em`.
