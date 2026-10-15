# Ranging-definition file wrapper (`ifes_apt_tc_data_modeling`) for `pynxtools-apm`

## Source files reviewed

- `pynxtools_apm/…/ifes_ranging.py` — `IfesRangingDefinitionsParser`, eight `extract_data_from_*` functions, `add_unknown_iontype()` and `add_standardize_molecular_ions()` (475 lines). The exact folder was not stated.
- Imported, **not supplied**: `ifes_apt_tc_data_modeling` readers (`ReadEnvFileFormat`, `ReadFigTxtFileFormat`, `ReadPyccaptRangingFileFormat`, `ReadImagoAnalysisFileFormat`, `ReadRngFileFormat`, `ReadRrngFileFormat`, `ReadCamecaHfiveFileFormat`, `ReadAnalysissetFileFormat`) and utilities (`create_nuclide_hash`, `nuclide_hash_to_nuclide_list`, `nuclide_hash_to_human_readable_name`, `MAX_NUMBER_OF_ION_SPECIES`, `MAX_NUMBER_OF_ATOMS_PER_ION`, `MQ_EPSILON`); `pynxtools_apm` constants (`DEFAULT_COMPRESSION_FILTER`, `DEFAULT_COMPRESSION_LEVEL`, `MAKE_RANGING_DEFINITIONS_UNIQUE`, `get_pynxtools_apm_version`), `VALID_FILE_NAME_SUFFIX_RANGE`; `prioritized_axes_heuristic`.
- Project: [pynxtools-apm repository](https://github.com/FAIRmat-NFDI/pynxtools-apm).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `rng l.` = `ifes_ranging.py`.

## At a glance

|                        |                                                                                                                                                                         |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input format**       | Atom-probe ranging definitions: `.env`, `.fig.txt`, `range_.h5` (pyccapt), `.analysis` (IVAS/Imago), `.rng`, `.rrng`, `.hdf5` (Cameca), `.analysisset` (rng l. 433–465) |
| **Parser class**       | `IfesRangingDefinitionsParser` (rng l. 350–474)                                                                                                                         |
| **Reader**             | One third-party reader per format; each exposes a dict with a `molecular_ions` list (rng l. 251–347)                                                                    |
| **Raw-data storage**   | `self.meta = {file_format, file_path, entry_id}` (rng l. 355–359)                                                                                                       |
| **Output from parser** | Template entries under `/ENTRY[entry<id>]/atom_probeID[atom_probe]/ranging/peak_identification/…` (rng l. 64, 95, 233–236, 416–418)                                     |
| **Per ion**            | `ionID[ion<n>]/{nuclide_hash, charge_state, mass_to_charge_range (+@units), nuclide_list, name}` and optional `charge_state_analysis/…` (rng l. 99–230)                 |
| **Target definition**  | `NXapm` ranging section (`NXion`, `peak_identification`)                                                                                                                |
| **Project context**    | Replaces vendor-specific range parsing with one normalised ion model; also derives `specimen/atom_types`                                                                |

**Standard behaviour.** The constructor selects the first suffix from `VALID_FILE_NAME_SUFFIX_RANGE` that the file name ends with (rng l. 360–367). `parse()` writes a maximum atoms-per-ion number and the program name and version, adds an `ion0` "unknown" type, dispatches by suffix to the matching reader, writes all molecular ions through `add_standardize_molecular_ions()`, and finally derives `atom_types` from the ions (rng l. 406–474).

**Comparison with `ifes_reconstruction.py`.** Same wrapper pattern (suffix → function), but every reader here feeds one shared writer, whereas the reconstruction functions each write their own quantities.

## Formula / transformation

### Parser: unknown ion type

**Location:** `add_unknown_iontype()` (rng l. 61–87). Ion `ion0` has `nuclide_hash = create_nuclide_hash([])` (uint16), `charge_state = 0` (int8), `mass_to_charge_range = [[0, MQ_EPSILON]]` float32 in Da, the matching `nuclide_list` and a readable name.

### Parser: number of ion types

**Location:** rng l. 94, 231, 236.

$$
\text{number\_of\_ion\_types} = N_{\text{ions}} + 1
$$

`ion_id` starts at 1 and is incremented after each ion, so after the loop it equals `N + 1`, which counts `ion0` as well.

### Parser: charge-state model

**Location:** rng l. 125–230. If `ion.charge_state_model["n_cand"] > 0` the config is written (nuclides, range, `min_abundance`, `min_half_life` in s, `sacrifice_isotopic_uniqueness`); for `n_cand == 1` scalars (charge state, mass in Da, natural abundance product, shortest half-life in s), for `n_cand > 1` the same quantities as 1D arrays and `nuclide_hash` as a 2D matrix.

### Parser: atom types from ions

**Location:** `update_atom_types_ranging_definitions_based()` (rng l. 369–404). For ions `1 … N` take `nuclide_list[:, 1]`, keep values with `0 < Z ≤ 118`, map through `ase.data.chemical_symbols`, write the comma-joined set to `/ENTRY[entry<id>]/specimen/atom_types`.

## Standard behaviour

1. **Suffix detection.** Lower-cased file name against `VALID_FILE_NAME_SUFFIX_RANGE`, first match wins; otherwise `supported = False` and a warning (rng l. 360–367).
2. **Fixed header values.** `maximum_number_of_atoms_per_molecular_ion` (uint32), `programID[program1]/program = "pynxtools-apm"` with `@version` (rng l. 419–429).
3. **Unknown ion.** `add_unknown_iontype()` (rng l. 431).
4. **Dispatch** (rng l. 433–465):

| Suffix | Function | Reader dict |
|---|---|---|
| `.env` | `extract_data_from_env_file` (rng l. 248) | `env` |
| `.fig.txt` | `…_fig_txt_file` (rng l. 259) | `fig` |
| `range_.h5` | `…_pyccapt_file` (rng l. 272) | `pyc` |
| `.analysis` | `…_imago_file` (rng l. 285) | `imago` |
| `.rng` | `…_rng_file` (rng l. 298) | `rng` |
| `.rrng` | `…_rrng_file` (rng l. 309) | `rrng` |
| `.hdf5` | `…_cameca_hfive_file` (rng l. 320) | `cameca` |
| `.analysisset` | `…_analysisset_file` (rng l. 335) | `analysisset` |

5. **Per format.** Create the reader with `MAKE_RANGING_DEFINITIONS_UNIQUE`, warn if more than `np.iinfo(np.uint8).max + 1 = 256` molecular ions, call `add_standardize_molecular_ions()`.
6. **Per ion.** Compressed-array dicts `{"compress", "filter", "strength", "chunks"}` (chunks from `prioritized_axes_heuristic`) for hash and list; scalars for charge state and name (rng l. 99–123).
7. **Fallback.** For an unhandled suffix or empty path, `number_of_ion_types = 1` (rng l. 466–471).
8. **Atom types.** `update_atom_types_ranging_definitions_based()` (rng l. 473).

## Special behaviour

1. **`ion0` is always present** and means "unidentified" (rng l. 63).
2. **Ions are numbered from 1**, indices live in `[0, 256)` (rng l. 245).
3. **Ranging is not resolved recursively.** `ranging` is a group with unbounded `NXion` members and possibly several operators (rng l. 240–244).
4. **Missing background and peak search data.** Not available in RNG/RRNG files (rng l. 424–425).
5. **Mass-to-charge distribution** is filled by the default plot elsewhere (rng l. 423).
6. **`entry_id` is stored unvalidated** (rng l. 358); no `entry_id > 0` rule as in the Oasis parsers.

## Behaviour to investigate

1. **Warning without limit.** More than 256 definitions only logs a warning (rng l. 252–253 and seven copies); the message refers to `MAX_NUMBER_OF_ION_SPECIES` (rng l. 57) but the check uses the literal 256, so they can diverge.
2. **Non-deterministic `atom_types`.** `", ".join(list(unique_elements))` iterates a `set` of strings (rng l. 399); with hash randomisation the order differs between runs. The same pattern exists in `oasis_eln.py`. Sorting would make files reproducible.
3. **Overwrite order.** This method writes `specimen/atom_types` (rng l. 402) and the ELN parser can write the same key; the final value depends on the call order in the caller (not supplied).
4. **Comment vs code.** The comment says "second row" of `nuclide_list` gives the atom number (rng l. 389), but the code takes column index 1 (`[:, 1]`, rng l. 388). Confirm the column order of `nuclide_list`.
5. **Unit strings.** `@units` for ranges is `f"{ion.ranges.units}"` (rng l. 76 uses `"Da"`, rng l. 113 uses pint formatting); `"Da"` is hard-coded for mass and `"s"` for half-lives (rng l. 143, 163, 170, 202, 230). Verify that pint's string equals the NXDL-accepted unit string.
6. **Dead branch.** The inner `else` (rng l. 466–468) is reachable only if a suffix is listed in `VALID_FILE_NAME_SUFFIX_RANGE` but not dispatched.
7. **Silent partial results.** If no ion has a valid nuclide list the `atom_types` write is skipped without a message (rng l. 400–402).
8. **Type of `number_of_ion_types`.** A `np.uint32` on the main path (rng l. 236) and a plain `int` in the fallback (rng l. 468, 471).
9. **Suffix order.** Matching is by first `endswith` hit in tuple order (rng l. 360–363); overlapping suffixes (`.analysis` vs `.analysisset`, `.rng` vs `.rrng`) work only because none is a suffix of another (checked for the dispatch list).
10. **Duplicate reader code.** Seven near-identical extract functions (rng l. 248–347) would be one function plus a table.
11. **Import order.** `WARNING_TOO_MANY_DEFINITIONS` is defined between two import groups (rng l. 57–58).
12. **`prefix` defined twice** in `update_atom_types…` (rng l. 372, 381).
13. **Charge-state analysis keys.** The `min_abundance_product` entry is commented out (rng l. 137–139).

## Scanner findings

No scanner run was performed for `pynxtools-apm`.
