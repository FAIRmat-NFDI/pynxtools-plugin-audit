# NOMAD Oasis ELN and configuration parsers (`pynxtools-em`)

## Source files reviewed

- `src/pynxtools_em/parsers/oasis_eln.py` — `NxEmNomadOasisElnSchemaParser` (160 lines).
- `src/pynxtools_em/parsers/oasis_config.py` — `NxEmNomadOasisConfigParser` (208 lines).
- Imported, **not** reviewed: `configurations/oasis_eln_cfg.py` (`OASISELN_EM_ENTRY_TO_NEXUS`, `OASISELN_EM_PROJECT_TO_NEXUS`, `OASISELN_EM_SAMPLE_TO_NEXUS`, `OASISELN_EM_USER_TO_NEXUS`), `configurations/oasis_eln_config_cfg.py` (`OASISCFG_EM_CITATION_TO_NEXUS`, `…_CSYS_…`, `…_NOTE_…`, `…_PROJECT_…`, `…_SAMPLE_…`), `concepts/mapping_functors_pint.py` (`add_specific_metadata_pint`).
- Project: [pynxtools-em, branch develop](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop), parsers in [`src/pynxtools_em/parsers`](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop/src/pynxtools_em/parsers).

**Line-number note:** References below refer to the files in the develop branch on 14th October 2026. `eln l.` = `oasis_eln.py`, `cfg l.` = `oasis_config.py`.

## At a glance

| | ELN | Config |
|---|---|---|
| **Class** | `NxEmNomadOasisElnSchemaParser` (eln l. 38–160) | `NxEmNomadOasisConfigParser` (cfg l. 39–208) |
| **Input file** | name ends with `eln_data.yaml` or `eln_data.yml` (eln l. 48) | name ends with `.oasis.specific.yaml` or `.oasis.specific.yml` (cfg l. 45–47) |
| **Reader** | `yaml.safe_load`, `utf-8` (eln l. 68–69) | `yaml.safe_load`, `utf-8` (cfg l. 67–68) |
| **Raw-data storage** | `self.flat_metadata`, a `FlatDict` with `/` delimiter (eln l. 52, 69) | same (cfg l. 51, 68) |
| **Parse stages** | entry, project, sample, atom types, user (eln l. 87–91) | reference frames, citations, notes, experiment description, sample, user (cfg l. 85–97) |
| **Mapping config** | `OASISELN_EM_ENTRY/PROJECT/SAMPLE/USER_TO_NEXUS` | `OASISCFG_EM_CSYS/CITATION/NOTE/PROJECT/SAMPLE_TO_NEXUS` and `OASISELN_EM_USER_TO_NEXUS` |
| **Hand-coded writes** | `sample/chemical_formula`, `sample/atom_types`, ORCID `identifier` | `experiment_description` |
| **Identifiers** | `[entry_id]` or `[entry_id, user_id]` | `[entry_id]`, `[entry_id, csys_id|cite_id|note_id]` |
| **Output location** | `/ENTRY[entryN]/…` (project, sample, user) | `/ENTRY[entryN]/…` (coordinate systems, citations, notes, description) |
| **Checksum** | sha256 computed and logged (eln l. 82–86) | sha256 computed and logged (cfg l. 80–84) |

## General structure of an ELN/config parser

Neither class reads measurement data. Both serialise *context* that the instrument file does not contain: who measured, which sample, which project, which coordinate systems. The data arrive from NOMAD Oasis as YAML and are mapped onto `NXem` paths through declarative tables.

1. **Constructor.** Name gate on the *file name* (`pathlib.Path(file_path).name.endswith(...)`, eln l. 48, cfg l. 45–47); on mismatch a warning and `supported = False` (eln l. 60–63, cfg l. 59–62). Otherwise store `file_path`, `entry_id` (clamped to ≥ 1), `verbose`, initialise an empty `FlatDict({}, "/")`, call `check_if_supported()`, log at debug level if not supported (eln l. 49–58, cfg l. 46–57).
2. **`check_if_supported()`.** Open the file with `utf-8`, load with `yaml.safe_load`, wrap in `fd.FlatDict(..., "/")`, optionally log every key/value (`verbose`), set `supported = True`. Only `OSError`/`FileNotFoundError` are caught (eln l. 65–77, cfg l. 64–75).
3. **`FlatDict` semantics.** Nested dictionaries become `a/b/c` keys; *lists are not flattened* and stay values. This is what the list-of-dictionary handling relies on (see below).
4. **`parse(template)`.** If `supported`: compute and log sha256 of the file, then run the stage methods in a fixed order (eln l. 79–92, cfg l. 77–98). Each stage takes and returns `template`.
5. **Declarative mapping.** `add_specific_metadata_pint(cfg_table, flat_metadata, identifier, template)` copies values from the flat dict to the template according to a config table and resolves the identifier list into the template path. The tables are in the `configurations` package and were not reviewed here.
6. **List-of-dicts sections.** `user`, `custom_coordinate_system`, `citation`, `note` arrive as lists of dictionaries "from the custom schema" (comments eln l. 145, cfg l. 107). The parsers check `isinstance(list)` and `all(isinstance(entry, dict))`, enumerate with a one-based counter, skip empty dictionaries and call the mapping once per dictionary with `[entry_id, counter]`.
7. **No unit handling by hand.** Unit conversions are delegated to the `_pint` mapping functor.

## Formula / transformation (shared)

### One-based counter per list section

$$
\text{id}_1 = 1,\qquad \text{id}_{k+1} = \text{id}_k + 1\ \text{for each non-empty dict}
$$

Empty dictionaries are skipped *before* the counter is incremented, so ids stay consecutive (eln l. 147–149, 159; cfg l. 106–117, 129–140, 152–163).

### Identifier forms

| Form | Used for |
|---|---|
| `[entry_id]` | scalar sections: entry, project, sample (eln l. 96–111; cfg l. 89–94, 202–206) |
| `[entry_id, n]` | per-item sections: user (eln l. 149–153), coordinate system (cfg l. 111–116), citation (cfg l. 134–139), note (cfg l. 157–162) |

## Standard behaviour

1. **Gate on name** (see general structure 1).
2. **Load YAML** and flatten.
3. **Checksum** the file (`open(file_path, "rb", 0)`, eln l. 82–83, cfg l. 80–81).
4. **Run stages** in the fixed order listed in the table.
5. **Return the template**, always (also if `supported` is false).

## Special behaviour

1. **`supported` means "loaded", not "contains something".** It is set to `True` as soon as the YAML parses (eln l. 74, cfg l. 72); the "finds no content" debug message (eln l. 55–58, cfg l. 54–57) can therefore only appear after an I/O error.
2. **Silent skip of unexpected shapes.** If a section is not a list, or contains a non-dict, nothing is written and nothing is logged (eln l. 142–143, cfg l. 104–105, 124–128, 147–151).
3. **No cross-parser coordination.** The ELN and the config parser both map `OASISELN_EM_USER_TO_NEXUS`; whichever runs later writes last (eln l. 149–153, cfg l. 95–97).
4. **No source annotation.** Neither class writes `PROCESS[process]/input` information; only the log carries the checksum.

## Behaviour to investigate

1. **File-name gate is a suffix test.** `endswith("eln_data.yaml")` (eln l. 48) accepts `my_eln_data.yaml` and `xeln_data.yaml`; the config gate (`.oasis.specific.yaml`) is stricter because of the leading dot.
2. **YAML errors.** `yaml.YAMLError` is not caught (eln l. 75, cfg l. 73); malformed files raise out of the constructor.
3. **Order dependency.** Where several stages can write the same template key, the later one wins; see config 3 and 4.
4. **Copy-paste structure.** `parse_citations`, `parse_notes` (cfg l. 120–141, 143–164), `parse_reference_frames` (cfg l. 100–118) and `parse_user` (eln l. 138–160) are the same loop with different tables and counters.
5. **Verbose log labels differ** (`value` in eln l. 72, `val` in cfg l. 70).
6. **Type checks and `is True`.** `all(...) is True` (cfg l. 126–128, 149–151, 175–177) is redundant with the truthiness of `all`.

---

## Parser: `oasis_eln.py` — `NxEmNomadOasisElnSchemaParser`

### At a glance

| | |
|---|---|
| **Input** | `eln_data.yaml`/`.yml` produced by the NOMAD Oasis NXem ELN schema |
| **Class docstring** | "not to copy over everything but only specific pieces of information relevant from the NeXus perspective" (l. 39–43) |
| **Stages** | `parse_entry` (l. 94–99), `parse_project` (l. 101–106), `parse_sample` (l. 108–113), `parse_atom_types` (l. 115–136), `parse_user` (l. 138–160) |
| **Mapping tables** | `OASISELN_EM_ENTRY_TO_NEXUS`, `OASISELN_EM_PROJECT_TO_NEXUS`, `OASISELN_EM_SAMPLE_TO_NEXUS`, `OASISELN_EM_USER_TO_NEXUS` (l. 27–32) |
| **Extra dependency** | `ase.data.chemical_symbols` for element validation (l. 24, 131) |

### Formula / transformation

**Chemical formula or atom types (l. 115–136).**

- If `sample/chemical_formula` exists and is not `""`: write `/ENTRY[entryN]/sampleID[sample]/chemical_formula` and return (l. 117–124). The comment states that Hill convention is assumed and that NOMAD checks it during parsing and normalisation (l. 121–122).
- Otherwise, if `sample/atom_types` exists: split on `,`, `strip`, keep tokens that are in `chemical_symbols[1::]` (i.e. real elements; index 0 is the placeholder `"X"`), collect in a `set`, write the comma-joined list to `…/sampleID[sample]/atom_types` (l. 126–135). Invalid tokens are dropped silently (l. 133).

**ORCID (l. 155–158).** If a user dict has `orcid`: write `…/userID[userN]/identifier = <orcid>` and `…/identifier/@type = "DOI"`.

### Standard behaviour

1. Gate on `eln_data.yaml|yml` (l. 48), load, flatten with `delimiter="/"` (l. 69).
2. `parse_entry`, `parse_project`, `parse_sample`: one mapping call each with `[entry_id]` (l. 96–97, 103–104, 110–111).
3. `parse_atom_types`: formula preferred, atom list as fallback (above).
4. `parse_user`: for each non-empty dict map with `[entry_id, user_id]` (l. 149–153), add ORCID identifier (l. 155–158), increment `user_id` (l. 159).

### Special behaviour

1. **Fallback logic is exclusive.** If a non-empty `chemical_formula` was written, `atom_types` is not looked at (l. 124).
2. **Silent filtering** of invalid element symbols (comment l. 133).
3. **`sampleID[sample]`** is a fixed instance name for the hand-coded sample fields (l. 118).
4. **Same table for user as in the config parser**, but with a two-element identifier (see config 3).

### Behaviour to investigate

1. **Non-deterministic order.** `", ".join(list(unique_elements))` (l. 135) joins a `set`; the order of elements can change between interpreter runs. Sorting (or preserving input order) would make the NeXus output reproducible.
2. **Type assumptions.** `self.flat_metadata[src].split(",")` (l. 129) fails with `AttributeError` if `sample/atom_types` is not a string (e.g. a YAML list or `None`).
3. **ORCID typed as `DOI`.** l. 158 labels an ORCID iD with `@type = "DOI"`; check against the identifier types allowed by the NXem/NXuser definition.
4. **Formula only checked for `!= ""`** (l. 120); a `None` value passes and is written.
5. **Sample path split.** The mapped sample fields (`OASISELN_EM_SAMPLE_TO_NEXUS`) and the hand-coded `sampleID[sample]` (l. 118) must agree on the instance name; confirm in the config table.
6. **Duplicate-write risk** for ids: `user_id` advances only for non-empty dicts, so reordering the YAML list changes ids.
7. **Wrong file with right suffix.** Any YAML matching the file-name gate is accepted (general investigate 1).

---

## Parser: `oasis_config.py` — `NxEmNomadOasisConfigParser`

### At a glance

| | |
|---|---|
| **Input** | Deployment-specific `*.oasis.specific.yaml`/`.yml` (NOMAD Oasis configuration) |
| **Class docstring** | "Parse deployment specific configuration." (l. 40) |
| **Stages** | `parse_reference_frames` (l. 100–118), `parse_citations` (l. 120–141), `parse_notes` (l. 143–164), `parse_experiment_description` (l. 166–208), then sample (l. 89–94) and user (l. 95–97) mapping inside `parse` |
| **Mapping tables** | `OASISCFG_EM_SAMPLE_TO_NEXUS`, `OASISCFG_EM_CSYS_TO_NEXUS`, `OASISCFG_EM_CITATION_TO_NEXUS`, `OASISCFG_EM_NOTE_TO_NEXUS`, `OASISCFG_EM_PROJECT_TO_NEXUS` (l. 27–32), `OASISELN_EM_USER_TO_NEXUS` from the ELN config module (l. 26) |
| **Sections read** | `custom_coordinate_system`, `citation`, `note` (lists of dicts), plus scalar sections via the tables |

### Formula / transformation

**Experiment description (l. 166–208).**

1. Look at `citation` (list of dicts); take the **first non-empty** dict (`break`, l. 193, comment "assume first reference is always to the dataset").
2. For the fields `title`, `author`, `doi` in this order, append `"<value>, "` if present (l. 184–191).
3. `message = "\n".join(parts).strip()`; remove one trailing `,` (l. 197–199).
4. Write to `/ENTRY[entryN]/experiment_description` (l. 198–200).
5. Afterwards, map `OASISCFG_EM_PROJECT_TO_NEXUS` with `[entry_id]` (l. 202–206).

The result has the form

```
<title>, 
<author>, 
<doi>
```

(each non-final line ends with `", "` before the newline).

### Standard behaviour

1. Gate on `.oasis.specific.yaml|yml` (l. 45–47), load and flatten with `"/"` (l. 68).
2. `parse()` runs in this order: reference frames, citations, notes, experiment description, sample mapping, user mapping (l. 85–97).
3. Reference frames: list-of-dicts under `custom_coordinate_system`, identifier `[entry_id, csys_id]` (l. 102–117).
4. Citations: under `citation`, identifier `[entry_id, cite_id]` (l. 122–140).
5. Notes: under `note`, identifier `[entry_id, note_id]` (l. 145–163).
6. Experiment description and project mapping as above.

### Special behaviour

1. **Citations are used twice**: mapped one by one into NeXus citation groups (l. 134–139) and the first one also condenses into the description (l. 193).
2. **Only the first citation** feeds the description; the `# TODO other cases possible, e.g. AI summaries` marks the open extension (l. 169).
3. **`parse_experiment_description` also writes the project mapping** (l. 202–206), although its name and docstring only mention the description.
4. **Scalar sections** (sample, user) are mapped directly in `parse` (l. 89–97).

### Behaviour to investigate

1. **User identifier length.** The config parser calls `OASISELN_EM_USER_TO_NEXUS` with `[self.entry_id]` against the *whole* flat dict (l. 95–97), while the ELN parser calls the same table once per user dict with `[entry_id, user_id]` (eln l. 149–153). Check the table's path template; one of the two calls may not resolve as intended.
2. **Description overwritten?** `OASISCFG_EM_PROJECT_TO_NEXUS` is applied after the description is written (l. 202–206); if the table also maps `experiment_description`, it replaces the composed text.
3. **Formatting of the composed text.** Items end with `", "` and are joined with `"\n"` (l. 190–197), so interior lines end in `", "` before the newline; only the final comma is removed (l. 199). `author` as a list or dict is rendered with Python's `repr`.
4. **`break` fires on the first non-empty dict** even if none of `title`, `author`, `doi` is present (l. 193), in which case no description is written.
5. **Unused counter.** `cite_id` is declared in `parse_experiment_description` and never used (l. 179).
6. **Unused return values.** The stage methods return `template` but `parse` ignores the returns (l. 85–88); this is harmless because `template` is mutated in place.
7. **`supported` after empty file.** An empty YAML file passes (general special 1) and all stages silently do nothing.
8. **Shared names with ELN.** Config-specific tables and ELN tables overlap for `user` (special 3 in the shared section); a short comment in the code on which parser owns which sections would remove the ambiguity.

## Scanner findings

No scanner run was performed for `pynxtools-em`.
