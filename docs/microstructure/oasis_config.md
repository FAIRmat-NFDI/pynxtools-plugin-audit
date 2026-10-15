# NOMAD Oasis deployment config parser `*.oasis.specific.yaml` (`pynxtools-microstructure`)

## Source files reviewed

- `pynxtools_microstructure/…/oasis_config.py` — `NxMicrostructureNomadOasisConfigParser` (165 lines). The exact folder was not stated.
- Imported: `OASISCFG_MICROSTRUCTURE_CITATION_TO_NEXUS` and `OASISCFG_MICROSTRUCTURE_PROJECT_TO_NEXUS` (`pynxtools_microstructure/configurations/oasis_eln_config_cfg.py`); `add_specific_metadata_pint` (`pynxtools_em.concepts.mapping_functors_pint`); `get_sha256_of_file_content` (`pynxtools_em.utils.get_checksum`); `logger` (`pynxtools_microstructure.utils.custom_logging`).
- External: `flatdict`, `pyyaml`.
- Project: [pynxtools-microstructure](https://github.com/FAIRmat-NFDI/pynxtools-microstructure).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `oasis l.` = `oasis_config.py`.

## At a glance

| | |
|---|---|
| **Input format** | YAML file named `*.oasis.specific.yaml` or `*.oasis.specific.yml` (oasis l. 38–40) |
| **Parser class** | `NxMicrostructureNomadOasisConfigParser` (oasis l. 34–164) |
| **Reader** | `yaml.safe_load` into `flatdict.FlatDict(…, "/")` (oasis l. 59–60) |
| **Raw-data storage** | `self.flat_metadata` (oasis l. 44) |
| **Output** | Entries in the `template` dict via `add_specific_metadata_pint` and direct assignments (oasis l. 99–161) |
| **Constructor arguments** | `file_path`, `entry_id` (≤ 0 becomes 1), `verbose` (oasis l. 37, 42–43) |
| **Companion argument** | `parse(template, mtex_hfive_file_path)` takes the path of the `.mtex.h5` file (oasis l. 69) |
| **Target definition** | `NXem` / `NXmicrostructure` instances under `ENTRY[entry<id>]` |
| **Project context** | Adds deployment- and dataset-level context (citation, project, users, start time, canonical file path) that MTex output lacks; counterpart to `nxs_mtex.py` |

**Standard behaviour.** The constructor accepts only matching file names, loads the YAML, and flags the parser as supported. `parse()` hashes the file, then `parse_example()` maps the first citation, the project block, an `experiment_description` text, users, a start time and a file-path alias into the template.

## Formula / transformation

### Parser: experiment description

**Location:** oasis l. 82–131. From the first non-empty citation dict, the values of `title`, `author`, `doi` (in that order, if present) are appended as `"<value>, "` (oasis l. 107–115). They are joined with `"\n"`, stripped, a trailing `,` removed (oasis l. 128–131):

```text
title, \nauthor, \ndoi
```

Written to `/ENTRY[entry<id>]/experiment_description`.

### Parser: file-path alias

**Location:** oasis l. 150–162. For each `{src, trg}` pair:

```python
mtex_hfive_file_path.rsplit("/", 1)[1] == f"{src.rsplit('/', 1)[1]}.mtex.h5"
```

On a match, `trg` is written to `…/roiID[roi1]/ebsd/indexing/microstructureID[microstructure1]/configuration/programID[program1]/mtex/COLLECTION[path]/file_name` and the loop stops. Example: `src = "/data/ebsd/sample_a"`, MTex file `/tmp/work/sample_a.mtex.h5` → match; `file_name` becomes the `trg` string, e.g. a path on the Oasis.

## Standard behaviour

1. **Gate.** File name suffix check (oasis l. 38–40); otherwise a warning and no further state (oasis l. 51–54).
2. **Load.** `check_if_supported()` opens UTF-8, builds a `FlatDict` with `/` as delimiter, optionally logs every key and value, sets `supported = True` (oasis l. 56–67). `OSError`/`FileNotFoundError` log "not found" and return unsupported.
3. **Hash.** `parse()` computes SHA-256 of the file (oasis l. 71–73), logs it (oasis l. 74–76), then calls `parse_example()`.
4. **Citation** (oasis l. 86–117)
   - requires `citation` to be a list whose entries are all dicts (oasis l. 87–92);
   - each non-empty dict is mapped with `OASISCFG_MICROSTRUCTURE_CITATION_TO_NEXUS` and identifier `[entry_id, cite_id]` (oasis l. 94–105);
   - **only the first** non-empty citation is used; the loop breaks after it (oasis l. 116–117).
5. **Project** — the whole flat metadata through `OASISCFG_MICROSTRUCTURE_PROJECT_TO_NEXUS` with identifier `[entry_id]` (oasis l. 119–125).
6. **Description** — written if the list from step 4 is non-empty (oasis l. 127–131).
7. **Users** — each dict in `user` with a `name` becomes `userID[user<n>]/name`; `n` counts only named users (oasis l. 133–140).
8. **Start time** — `start_time` copied unchanged if not the empty string (oasis l. 144–148).
9. **File alias** — as above (oasis l. 150–162).
10. **Return** the template (oasis l. 164).

## Special behaviour

1. **Flat keys.** `FlatDict` with `/` flattens nested mappings, so a nested key is `parent/child`; lists are kept as values (relied on at oasis l. 88, 135, 152).
2. **Mapping tables live elsewhere.** What `add_specific_metadata_pint` writes is decided by the two `OASISCFG_*` tables (not supplied).
3. **Cross-plugin imports.** This module depends on `pynxtools_em` (oasis l. 24–25), as does `nxs_mtex.py`.
4. **Intentional single-citation rule.** The comment says the first reference is assumed to be the dataset (oasis l. 116–117).
5. **OpenAlex note.** A comment (oasis l. 142–143) says `start_time` can come from OpenAlex, such as a publication date.
6. **TODO** for other description sources, e.g. AI summaries (oasis l. 84).

## Behaviour to investigate

1. **`supported` is unset for wrong names.** The `else` branch only warns (oasis l. 51–54); a later `parse()` raises `AttributeError` on `self.supported`.
2. **Narrow exception handling.** An empty YAML (`safe_load` returns `None`) or invalid YAML (`yaml.YAMLError`) is not caught (oasis l. 59–60); `FileNotFoundError` is redundant next to `OSError`; any `OSError` is reported as "not found" (oasis l. 65–66).
3. **Support check checks nothing.** `supported` becomes `True` for any readable YAML (oasis l. 64), regardless of content.
4. **Alias crash.** `rsplit("/", 1)[1]` raises `IndexError` for a path without `/` (oasis l. 156–157); backslash separators are not handled.
5. **Cite counter is dead.** `cite_id` increments after the first citation, then the loop breaks (oasis l. 94, 105, 116), so identifier `[entry_id, 2]` can never occur.
6. **List-valued author.** If `author` is a list or dict, the f-string at oasis l. 114 writes its Python representation.
7. **Description formatting.** Interior separators are `", \n"` (oasis l. 114, 128); a trailing comma is stripped, a trailing `, ` is not.
8. **Description overrides.** It is written after the project mapping (oasis l. 119–131), so it replaces any `experiment_description` produced there.
9. **`start_time` is unconditional.** The comment says "when no other qualified pieces of information are available" (oasis l. 143), but the code does not check the template (oasis l. 144–148); no ISO 8601 or time-zone validation.
10. **`user` shape.** The code expects a list of dicts (oasis l. 135–136). A mapping (flattened to `user/name`) fails the `"user" in …` test and is ignored without a message; a list of strings makes `"name" in user_dict` a substring test.
11. **Hash not stored.** `file_path_sha256` is only logged and kept on the object (oasis l. 73–76).
12. **Hard-coded target.** `roiID[roi1]`, `microstructureID[microstructure1]`, `programID[program1]` (oasis l. 160) must match what `nxs_mtex.py` writes (mtex l. 227).
13. **`parse()` signature.** The extra `mtex_hfive_file_path` parameter is needed for the alias only (oasis l. 69, 80, 156–158); without it, nothing else changes.
14. **Verbose logging** prints every key/value, which can expose private fields in logs (oasis l. 61–63).

## Scanner findings

No scanner run was performed for `pynxtools-microstructure`.
