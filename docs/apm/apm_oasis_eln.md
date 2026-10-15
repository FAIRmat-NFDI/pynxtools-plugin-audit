# NOMAD Oasis ELN YAML parser `eln_data.yaml` (`pynxtools-apm`)

## Source files reviewed

- `pynxtools_apm/…/oasis_eln.py` — `NxApmNomadOasisElnSchemaParser` (224 lines). The exact folder was not stated.
- Imported: `add_specific_metadata_pint`; eleven mapping tables from `pynxtools_apm.configurations.oasis_eln_cfg` (`APM_ENTRY_TO_NEXUS`, `APM_PROJECT_TO_NEXUS`, `APM_SAMPLE_TO_NEXUS`, `APM_SPECIMEN_TO_NEXUS`, `APM_MEASUREMENT_TO_NEXUS`, `APM_INSTRUMENT_STATIC_TO_NEXUS`, `APM_INSTRUMENT_DYNAMIC_TO_NEXUS`, `APM_INSTRUMENT_SPECIMEN_TO_NEXUS`, `APM_RANGE_TO_NEXUS`, `APM_RECON_TO_NEXUS`, `APM_WORKFLOW_TO_NEXUS`, plus `APM_USER_TO_NEXUS`); `parse_composition_table`; `logger`.
- External: `flatdict`, `pyyaml`, `ase.data.chemical_symbols`.
- Project: [pynxtools-apm repository](https://github.com/FAIRmat-NFDI/pynxtools-apm).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `eln l.` = `oasis_eln.py`.

## At a glance

|                        |                                                                                                                                                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Input format**       | `eln_data.yaml` / `eln_data.yml` dump of an instance of a NOMAD custom-schema ELN (eln l. 46–55, 65)                                                                                                                                       |
| **Parser class**       | `NxApmNomadOasisElnSchemaParser` (eln l. 45–223)                                                                                                                                                                                           |
| **Reader**             | `yaml.safe_load` → `FlatDict(…, delimiter="/")` (eln l. 71)                                                                                                                                                                                |
| **Raw-data storage**   | `self.yml` (a `FlatDict`)                                                                                                                                                                                                                  |
| **Constructor**        | `(file_path="", entry_id=1, verbose=False)`; `entry_id ≤ 0` becomes 1 (eln l. 63, 67)                                                                                                                                                      |
| **Output from parser** | Template entries under `/ENTRY[entry<id>]/…` from four hand-written methods and eleven mapping tables (eln l. 202–223)                                                                                                                     |
| **Target definition**  | `NXapm`; compliance is checked later by the dataconverter, not here (eln l. 57–60)                                                                                                                                                         |
| **Project context**    | Supplies what vendor files (pos, epos, apt, rng, rrng …) do not contain: sample, specimen, users, instrument, laser, workflow. The custom schema and NXapm do not share a harmonised vocabulary, hence "hardcoded" mapping (eln l. 51–55). |

**Standard behaviour.** `parse()` runs `parse_sample_composition`, `parse_atom_types`, `parse_user`, `parse_pulser_source`, then applies eleven mapping tables with identifier `[entry_id, 1]` through `add_specific_metadata_pint` (eln l. 202–223).

**Comparison with `oasis_config.py`.** That file reads a deployment-level `*.oasis.specific.yaml`; this one reads the per-experiment ELN dump. This class has no `supported` flag and no `parse` hash.

## Formula / transformation

### Parser: composition table

**Location:** `parse_sample_composition()` (eln l. 80–117). `parse_composition_table(list)` returns a dict with `normalization` and one `(value, error)` tuple per element symbol.

| `normalization`                           | Written                                                 | Unit variable |
| ----------------------------------------- | ------------------------------------------------------- | ------------- |
| `%`, `at%`, `at-%`, `at.-%`, `ppm`, `ppb` | `…/chemical_composition/normalization = "atom_percent"` | `at.-%`       |
| `wt%`, `wt-%`, `wt.-%`                    | `"weight_percent"`                                      | `wt.-%`       |
| anything else                             | function returns without writing                        |               |

For every symbol in `ase.data.chemical_symbols[1:]` present in the dict as a 2-tuple: `ELEMENT[<symbol>]/chemical_symbol`, `composition` (value), and `composition_errors` if the error is not `None` (eln l. 105–115). The `@units` lines are commented out (eln l. 113, 116) and the `unit` variable is unused.

### Parser: atom types

**Location:** `parse_atom_types()` (eln l. 119–133). `specimen/atom_types` is split at commas, stripped, kept only if it is a valid chemical symbol, de-duplicated in a `set` and written as `", ".join(list(set))` to `/ENTRY[entry<id>]/specimen/atom_types`. Invalid input is silently ignored (eln l. 128).

### Parser: users and ORCID

**Location:** `parse_user()` (eln l. 135–160). For each non-empty dict: map with `APM_USER_TO_NEXUS` and `[entry_id, user_id]`; if `orcid` is present, write `userID[user<n>]/identifierNAME[identifier] = orcid` and `…/@type = "DOI"` (eln l. 153–158).

### Parser: pulser sources

**Location:** `parse_pulser_source()` (eln l. 162–200). Returns immediately if `instrument/pulser/pulse_mode == "voltage"`. Otherwise, for each dict in `instrument/laser_source` it writes `name` and, for `power`, `pulse_energy`, `wavelength` given as `{value, unit}`, the value and `@units` under `measurement/eventID[event1]/instrument/pulser/sourceID[source<n>]/` (eln l. 176–196).

## Standard behaviour

1. **Load.** If the file name ends with `eln_data.yaml` / `eln_data.yml`, remember the path (eln l. 65–66); open UTF-8 and flatten (eln l. 69–71); on `OSError` use an empty `FlatDict` (eln l. 75–78).
2. **Composition, atom types, users, pulser** as above.
3. **Mapping tables.** In order: entry, project, sample, specimen, measurement, instrument static, instrument dynamic, instrument specimen, range, reconstruction, workflow (eln l. 209–222), each with identifier `[entry_id, 1]`. Later tables can overwrite earlier writes.

## Special behaviour

1. **Custom schema, hard-coded.** The mapping is explicit rather than generic (eln l. 51–55).
2. **No compliance check.** The parser does not verify the NXapm result (eln l. 57–60).
3. **Silent clean-up of atom types.** Invalid symbols are dropped without a message (eln l. 128).
4. **Laser details only when relevant.** Not read for `pulse_mode == "voltage"` (eln l. 164–167).
5. **Fixed second identifier** `1` for all table-driven writes (eln l. 208).

## Behaviour to investigate

1. **Constructor crash on wrong names.** If the name does not end with `eln_data.yaml/yml` (or the default `""` is used), `self.file_path` is never set, and `open(self.file_path)` at eln l. 70 raises `AttributeError`, which the `except (OSError, FileNotFoundError)` does not catch.
2. **`safe_load` of an empty file** returns `None`; `FlatDict(None, …)` fails (eln l. 71). Invalid YAML is not caught either.
3. **ppm and ppb treated as at.-%.** Both are accepted under `normalization = "atom_percent"` with the unit variable `at.-%` (eln l. 90–99). No scaling is applied here; whether `parse_composition_table` converts is not visible. The `@units` lines are commented out, so the unit is never written.
4. **Early return on unknown normalization.** The composition values are dropped altogether (eln l. 103–104). If `normalization` is missing the elements are written without a `normalization` field (eln l. 89).
5. **Non-deterministic atom types.** The comma-joined set (eln l. 131) has an unstable order between runs; the same pattern is in `ifes_ranging.py`. Both can write `specimen/atom_types`, so the final value depends on call order.
6. **`atom_types` type.** `.split(",")` (eln l. 124) fails with `AttributeError` if YAML gives a list.
7. **ORCID typed as DOI.** `@type = "DOI"` for an ORCID (eln l. 158) is likely wrong; check the NXDL enumeration.
8. **`KeyError` in laser parsing.** `laser_dict[qnt]` for `power`, `pulse_energy`, `wavelength` has no `in` check (eln l. 187); a laser without one of them stops the conversion.
9. **Duplicated target strings.** `trg_sta` and `trg_dyn` are identical (eln l. 176–183).
10. **Misleading warning.** `"pulse_mode != voltage but no laser details specified"` is also logged when `pulse_mode` is absent or `laser_source` is not a list of dicts (eln l. 165–167, 199).
11. **Overwrite order.** Table-driven writes after the four methods can replace their output (eln l. 204–222).
12. **No `supported` flag or hash**, unlike `oasis_config.py`; an unreadable file yields an empty parser that silently writes nothing (eln l. 75–78).
13. **Verbose logging** prints every key/value (eln l. 72–74).

## Scanner findings

No scanner run was performed for `pynxtools-apm`.
