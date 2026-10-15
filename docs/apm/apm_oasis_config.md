# NOMAD Oasis deployment config parser `*.oasis.specific.yaml` (`pynxtools-apm`)

## Source files reviewed

- `pynxtools_apm/…/oasis_config.py` — `NxApmNomadOasisConfigParser` (171 lines). The exact folder was not stated.
- Imported: `add_specific_metadata_pint` (`pynxtools_apm.concepts.mapping_functors_pint`); `OASISCFG_APM_CITATION_TO_NEXUS`, `OASISCFG_APM_CSYS_TO_NEXUS`, `OASISCFG_APM_PROJECT_TO_NEXUS` (`pynxtools_apm.configurations.oasis_eln_config_cfg`); `logger`; `get_sha256_of_file_content`.
- External: `flatdict`, `pyyaml`.
- Related: the `pynxtools-microstructure` variant `oasis_config.py` (separate walkthrough), from which this file differs as listed below.
- Project: [pynxtools-apm repository](https://github.com/FAIRmat-NFDI/pynxtools-apm).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `cfg l.` = `oasis_config.py` of `pynxtools-apm`.

## At a glance

|                        |                                                                                                                                     |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Input format**       | YAML named `*.oasis.specific.yaml` / `*.oasis.specific.yml` (cfg l. 39–41)                                                          |
| **Parser class**       | `NxApmNomadOasisConfigParser` (cfg l. 35–170)                                                                                       |
| **Reader**             | `yaml.safe_load` → `flatdict.FlatDict(…, "/")` (cfg l. 60–61)                                                                       |
| **Raw-data storage**   | `self.flat_metadata` (cfg l. 45)                                                                                                    |
| **Constructor**        | `(file_path, entry_id, verbose=False)`; `entry_id ≤ 0` becomes 1 (cfg l. 38, 43)                                                    |
| **Output from parser** | Template entries via `add_specific_metadata_pint` and direct assignments (cfg l. 94–168)                                            |
| **Target definition**  | `NXapm`                                                                                                                             |
| **Project context**    | Adds deployment- and dataset-level context (citation, project, custom coordinate systems, users, start time) that vendor files lack |

**Standard behaviour.** The constructor accepts matching file names, loads the YAML and sets `supported`. `parse()` hashes the file, then calls `parse_reference_frames()` and `parse_example()` (cfg l. 70–80).

**Differences from the `pynxtools-microstructure` variant.** This version has `parse_reference_frames()` for `custom_coordinate_system` (cfg l. 82–101), no `mtex_hfive_file_path` argument and no file-path aliasing. Everything else (citation, project, description, users, start time) is the same logic.

## Formula / transformation

### Parser: coordinate systems

**Location:** cfg l. 82–101. For each non-empty dict in the list `custom_coordinate_system`, identifier `[entry_id, csys_id]` and the map `OASISCFG_APM_CSYS_TO_NEXUS`; `csys_id` counts only non-empty dicts.

### Parser: experiment description

**Location:** cfg l. 105–151. From the first non-empty citation dict, `title`, `author`, `doi` (if present) are appended as `"<value>, "`, joined with `"\n"`, stripped, and a trailing `,` is removed:

```text
title, \nauthor, \ndoi
```

Written to `/ENTRY[entry<id>]/experiment_description`.

## Standard behaviour

1. **Gate.** File name suffix check; otherwise only a warning (cfg l. 39–55).
2. **Load.** UTF-8 open, `FlatDict` with delimiter `/`, optional verbose key/value logging, `supported = True` (cfg l. 57–68). `OSError` → warning "not found".
3. **Hash.** SHA-256 of the file, logged (cfg l. 73–77).
4. **Coordinate systems** as above (cfg l. 78, 82–101).
5. **Citation** (cfg l. 110–141): `citation` must be a list of dicts; each non-empty one is mapped with `OASISCFG_APM_CITATION_TO_NEXUS` and `[entry_id, cite_id]`; **only the first** is used (`break`, cfg l. 140–141).
6. **Project.** The flat metadata mapped with `OASISCFG_APM_PROJECT_TO_NEXUS` and `[entry_id]` (cfg l. 143–145).
7. **Description** if any citation field was collected (cfg l. 147–151).
8. **Users.** Each dict in `user` with a `name` becomes `userID[user<n>]/name` (cfg l. 153–160).
9. **Start time.** Copied unchanged if not the empty string (cfg l. 164–168).

## Special behaviour

1. **`FlatDict` keeps lists as values**, which the code relies on (cfg l. 86, 112, 155).
2. **Mapping tables live elsewhere**; this file decides only when to apply them.
3. **Single-citation rule** is intentional (cfg l. 140–141).
4. **OpenAlex hint.** A comment says `start_time` can be a publication date (cfg l. 162–163).
5. **TODO** for other description sources (cfg l. 108).

## Behaviour to investigate

1. **`supported` unset for wrong names.** The `else` branch only warns (cfg l. 52–55); `parse()` then raises `AttributeError` on `self.supported` (cfg l. 72).
2. **Narrow exception handling.** Invalid YAML (`yaml.YAMLError`) and an empty file (`safe_load` returns `None`) are not caught (cfg l. 61); `FileNotFoundError` is already an `OSError` (cfg l. 66); any `OSError` is reported as "not found" (cfg l. 67).
3. **Support check checks nothing.** Any readable YAML sets `supported = True` (cfg l. 65).
4. **Dead counter.** `cite_id` increments (cfg l. 129) and the loop breaks immediately after (cfg l. 140), so only `[entry_id, 1]` ever occurs.
5. **Non-string citation fields.** A list-valued `author` is written by f-string as its Python repr (cfg l. 138).
6. **Description overwrite.** The description is written after the project mapping (cfg l. 143–151) and replaces any `experiment_description` it produced.
7. **`start_time` unconditional.** The comment says "when no other qualified pieces of information are available" (cfg l. 163) but the template is not checked (cfg l. 164–168); no ISO 8601 or time-zone validation.
8. **`user` shape.** A list of dicts is expected (cfg l. 155–156). A mapping flattens to `user/name` and is ignored without a message; a list of strings turns `"name" in user_dict` into a substring test.
9. **Hash not stored.** `file_path_sha256` is only logged and kept on the object (cfg l. 74–77).
10. **Empty-list behaviour.** `all([])` is true, so an empty list is accepted and does nothing (cfg l. 87, 114).
11. **Verbose logging** prints every key and value, which can expose private fields (cfg l. 62–64).
12. **`parse_reference_frames`** is silent when `custom_coordinate_system` is not a list of dicts (cfg l. 85–87).

## Scanner findings

No scanner run was performed for `pynxtools-apm`.
