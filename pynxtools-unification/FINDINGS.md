# pynxtools plugins: architecture review and findings

Date of review: 2026-10-16. Branch state as checked out under `packages/`:

| Package | HEAD | Reader class | Base class |
|---|---|---|---|
| pynxtools | `2d8d4593` (v0.16.0, branch `pynxtools-dev`) | — (core) | — |
| pynxtools-apm | `c839a42` | `APMReader` | `BaseReader` |
| pynxtools-ellips | `95c2547` | `EllipsometryReader` | `MultiFormatReader` |
| pynxtools-em | `340f154` | `EMReader` | `BaseReader` |
| pynxtools-igor | `07ed951` | `IgorReader` | `MultiFormatReader` |
| pynxtools-microstructure | `4b06a27` | `MICROSTRUCTUREReader` | `BaseReader` |
| pynxtools-raman | `9a30f9b` | `RamanReader` | `MultiFormatReader` |
| pynxtools-spm | `a57cd20` | `SPMReader` | `BaseReader` |
| pynxtools-xas | `d7dcad5` | `XASReader` | `MultiFormatReader` |
| pynxtools-xps | `43c5bbe` | `XPSReader` | `MultiFormatReader` |
| pynxtools-xrd | `ba9b33a` | `XRDReader` | `MultiFormatReader` |

All links below are relative to this file. Line numbers refer to the commits listed above.

---

## 1. Summary

1. The plugins use **two base classes**. Six of them are built on `MultiFormatReader` (MFR): ellips, igor, raman, xas, xps and xrd. Four still subclass the bare `BaseReader` and implement their own pipeline: apm, em, microstructure and spm.
2. The plugins check file formats in **five different ways**:
   - by extension only (MFR core, igor, xrd, spm);
   - by extension, then a hard-coded single parser with `is_mainfile` (ellips, raman);
   - with a parser registry and `is_mainfile` / `match_failure_reason` / version ranges / an ambiguity check (xas, xps);
   - by suffix rules plus "try every parser and let it decide" (em, apm);
   - by an extension → vendor → software-version tree that is driven by **ELN values the user types in** (spm).
3. There are **four mapping languages** for getting from source data to NeXus paths:
   - the MFR flat JSON config with `@attrs/@data/@eln/@link` tokens (ellips, igor, raman, xas, xps, xrd, json_map);
   - Python "functor" dictionaries with `prefix_trg`, `map_to_f8`, pint units, `use`, and so on (apm, em, microstructure);
   - a nested JSON with `raw_path`, `@default:` and `@default_link:` (spm);
   - hard-coded template keys in Python (every plugin, in varying amounts).
4. **Copy-paste duplication** is large. The best design, the XAS/XPS `_Parser` with versioning, exists in four slightly different copies (xas, xps, raman, ellips). APM, EM and microstructure share around 15 forked utility modules that have since drifted (§5.1).
5. The plugins handle **the ELN in seven different ways** (§5.4), even though NOMAD always writes the same `*_eln_data.yaml` layout ([dataconverter.py:248-252](../packages/pynxtools/src/pynxtools/nomad/schema_packages/dataconverter.py#L248)).
6. I found a number of **real bugs**, several of them silent data loss. They are listed in §6 and most of them come from one of the inconsistencies above.
7. On **resources**: some detection steps read whole files (Velox EMD), every parser re-hashes the full file, a full `deepcopy` of the template is made (spm), templates are copied after `read` (xps, spm), HDF5 files are loaded eagerly and opened twice (json_map), and the reader module is re-executed on every `get_reader` call.

---

## 2. The core: `BaseReader` and `MultiFormatReader`

### 2.1 `BaseReader`
[base/reader.py:13-43](../packages/pynxtools/src/pynxtools/dataconverter/readers/base/reader.py#L13)

- The abstract `read(template, file_paths, objects)` has **no `**kwargs`** (L33-38). `transfer_data_into_template` still calls `data_reader().read(template=..., file_paths=..., **kwargs)` ([convert.py:137](../packages/pynxtools/src/pynxtools/dataconverter/convert.py#L137)), and the CLI injects `config_file` there ([cli.py:234](../packages/pynxtools/src/pynxtools/dataconverter/cli.py#L234)). Any plugin that copies the base signature (apm, em, microstructure, spm) therefore fails with a `TypeError` when `-c` or a params file adds keys.
- `supported_nxdls = [""]` is the only class-level contract. Nothing declares the supported file formats, so a host such as NOMAD cannot ask "which reader can handle this file?".

### 2.2 `MultiFormatReader`
[multi/reader.py](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py)

**What it does well:** a fixed pipeline (objects → files → `setup_template` → config → `post_process` → `fill_from_config`), callback hooks, built-in ELN and config handlers, `processing_order`, multi-entry support through `get_entry_names()`, `!` optional-group removal, and `*` wildcard expansion.

**Gaps that push plugins to override `read()` or skip MFR altogether:**

| # | Location | Finding |
|---|---|---|
| C1 | [L521-528](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L521) | Dispatch uses `os.path.splitext(...)[1]`, which returns **only the last suffix**. Compound suffixes that apm/em/microstructure depend on (`.mtex.h5`, `.oasis.specific.yaml`, `range_.h5`, `_trimmed.txt`, `.mrc.mdoc`) cannot be registered. |
| C2 | [L522](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L522) vs [L528](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L528) | The ordering key is **not lower-cased**, but dispatch is. `FILE.IBW` or Bruker `.FLT` is dispatched correctly but ignores `processing_order` and is sorted last. |
| C3 | L528-537 | Dispatch looks **only at the extension**. MFR has no notion of content sniffing or of "one extension, several parsers" (`.txt`, `.h5`, `.dat`, `.xml`, `.json`), so each plugin builds its own detection. |
| C4 | [L534](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L534) | A missing file only triggers a warning and the conversion continues, so it can "succeed" with an empty template. |
| C5 | [L498-565](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L498) | There is no "finalize" hook after `fill_from_config`. That is why raman, xas, xps and xrd override `read()` to post-edit the template (`/@default`, link `@target`, unit checks, dropping skeleton keys), and why they all hard-code `suppress_warning=True` and **drop the caller's kwargs** while doing so. |
| C6 | [L387](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L387) | `handle_eln_file` calls `get_entry_names()[0]` **while files are still being dispatched**, so the ELN is bound to whatever entry exists at that moment, usually `entry`. That explains why xas/xps re-parse with `parent_key="/ENTRY"` and add a generic-entry fallback in `get_eln_data`. |
| C7 | [L271](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L271) | `sorted(config_dict.items())` runs **once per entry**, inside the entry loop. It is cheap per call, but O(entries × keys log keys) for XPS files with hundreds of regions. |
| C8 | [L246](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L246) | `has_missing_main` uses `key.startswith(optional_group)` without a trailing `/`. Removing `/ENTRY[e]/sample` therefore also drops `/ENTRY[e]/sample_stage/...`. |
| C9 | [L144-157](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L144) + [utils.py:369](../packages/pynxtools/src/pynxtools/dataconverter/readers/utils.py#L369) | `is_boolean` is an **unanchored** regex (`True|False|...|On|Off|Yes|No`). Any literal fallback that contains "No", "Yes", "On" or "Off" ("November sample", "Notes", "Offset", …) is classed as boolean, and `to_bool()` then returns `None`, so **the value is silently dropped**. I reproduced this: `'["@eln", "November sample"]'` → `{}`. |
| C10 | [L555](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L555) | `suppress_warning` is a reader kwarg that is popped late. Every MFR plugin hard-codes it to `True`, so missing config values are never reported, which hides config mistakes (see XRD in §4.6). |
| C11 | [L108](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L108), L223-227 | Link handling is split: `@link:` tokens are rewritten in `link_callback`, again after resolution, and `/entry/` is replaced by plain string substitution. No check is made that the link target exists, and XPS has to add `@target` itself ([xps reader.py:934-935](../packages/pynxtools-xps/src/pynxtools_xps/reader.py#L934)). |
| C12 | — | **No config validation**: keys are never checked against the NXDL template, and tokens other than the four known prefixes (for example `@attr:` in XRD) silently fall back to `identity` and write the *path string* as the value. |

### 2.3 Other core points

- `get_reader` ([convert.py:34-52](../packages/pynxtools/src/pynxtools/dataconverter/convert.py#L34)) runs `exec_module` on the built-in reader file on every call, and falls back to entry points only through a `FileNotFoundError`. Nothing is cached.
- `transfer_data_into_template` ([convert.py:114](../packages/pynxtools/src/pynxtools/dataconverter/convert.py#L114)) seeds NXDL-declared defaults under the literal `/ENTRY[entry]/`. Readers that produce real entry names are left with a bogus `entry` that they must delete by hand ([xas reader.py:229-237](../packages/pynxtools-xas/src/pynxtools_xas/reader.py#L229)).
- `JsonMapReader` loads HDF5 eagerly (`lazy=False`) and then opens the file **a second time** for attributes ([json_map/reader.py:270-281](../packages/pynxtools/src/pynxtools/dataconverter/readers/json_map/reader.py#L270)). It also accepts `.pickle` files through `pickle.load` (L261), which executes arbitrary code.
- `readers/utils.py` already holds `parse_yml`, `flatten_and_replace` and `FlattenSettings`. These are the right building blocks for ELN handling, but each plugin wraps them differently (§5.4).
- `pynxtools.testing.nexus_conversion.ReaderTest` is used by **all 10 plugins**. This is a good shared regression harness and is the basis of Phase 0 in the plan.

---

## 3. Overview matrix

| Plugin | Format detection | Mapping language | ELN handling | Multi-entry | Overrides `read()` | Config selection |
|---|---|---|---|---|---|---|
| apm | suffix lists → role lists (`ApmUseCaseSelector`) | Python functor dicts | own ELN parser on `*.yaml` | no (`entry1` fixed) | yes (BaseReader) | — |
| em | suffix lists, then *every* parser tries the file | Python functor dicts | own ELN parser on `eln_data.yaml` and 3 "custom" ELNs | no (`entry1`) | yes (BaseReader) | — |
| microstructure | 2 compound suffixes | Python functor dicts (imports from **pynxtools-em**) | via em-style config parser | no | yes (BaseReader) | — |
| spm | extension + ELN `experiment_technique` + ELN vendor/version | nested JSON (`raw_path`, `@default:`) | `flatten_and_replace` | no (`entry` fixed) | yes (BaseReader) | 1 JSON per formatter, user override |
| ellips | extension + `WoollamParser.is_mainfile` | MFR JSON | custom `handle_eln_file`; ELN also **configures the parser** | no | no | fixed default, user override |
| raman | extension → one hard-coded parser + `is_mainfile` | MFR JSON | `parse_yml` + heuristic key mangling | no | yes | **parser overwrites user config** |
| igor | extension | MFR JSON | own `parse_yml`, ignores entry | yes (`.entry` file / objects) | no | user |
| xas | registry, `is_mainfile`, version, ambiguity | MFR JSON | `parse_yml(parent_key="/ENTRY")` + generic fallback | yes | yes | user > parser default |
| xps | registry + metadata-parser registry, version, ambiguity | MFR JSON | as xas + atom-type extraction | yes | yes | user > parser default |
| xrd | extension (via external `fairmat_readers_xrd`) | MFR JSON built in `__init__` | none | no | yes (drops kwargs) | fixed, user override ignored |

---

## 4. Per-plugin findings

### 4.1 pynxtools-xps
[reader.py](../packages/pynxtools-xps/src/pynxtools_xps/reader.py), [parsers/base.py](../packages/pynxtools-xps/src/pynxtools_xps/parsers/base.py)

**Strengths.** XPS is the reference design for "methodical format checking":
- `_Parser` ([base.py:335-593](../packages/pynxtools-xps/src/pynxtools_xps/parsers/base.py#L335)) has `supported_file_extensions`, `supported_versions` (half-open ranges), `detect_version`, `matches_file` (positive identification, at most a few KB), `is_mainfile`, `match_failure_reason`, and `parse` → `_parse`.
- Reader dispatch ([reader.py:431-500](../packages/pynxtools-xps/src/pynxtools_xps/reader.py#L431)) probes all registered parsers, raises on ambiguity, and logs per-parser rejection reasons.
- `_XPSMetadataParser` ([base.py:621-729](../packages/pynxtools-xps/src/pynxtools_xps/parsers/base.py#L621)) lets supplementary files (Vamas results) attach to a compatible primary parser, in any order.
- The typed intermediate representation (`ParsedSpectrum`, xarray-based) is decoupled from NeXus paths.
- Each parser chooses its config (`parser.config_file`), and a user config takes precedence (`set_config_file(..., replace=False)`).

**Issues.**
- `is_mainfile` runs for **every** parser and every file, and `parse()` then calls `_is_mainfile` again ([base.py:559](../packages/pynxtools-xps/src/pynxtools_xps/parsers/base.py#L559)). Each check re-opens the file and re-reads the header, so detection costs N_parsers + 1 file opens per file.
- `parser.parse(file_path, **(self.kwargs or {}))` forwards *all* converter kwargs (`nxdl`, `output`, …) to parsers.
- `read()` override ([L910-937](../packages/pynxtools-xps/src/pynxtools_xps/reader.py#L910)):
  - sets `overwrite_keys` from "more than one extension" (`_check_multiple_extensions`, L232). This is a heuristic proxy for "multiple sources";
  - discards kwargs other than `config_file`;
  - builds a second full `Template` copy to drop orphan `@units`, check units and add link `@target`. All of that is generic core work.
- `set_config_file(replace=...)` (L341), `get_eln_data` with generic `/ENTRY` fallback (L702), `_search_metadata` (L653) and `_collect_supported_extensions` (L259) are **duplicated verbatim in pynxtools-xas**.
- `set_nxdata_defaults` (L864) contains XPS-specific `/@default` logic, while every other plugin sets `/@default` in its own way.
- `handle_eln_file` (L360-429) mixes generic ELN flattening with domain logic (formula → `atom_types`).

### 4.2 pynxtools-xas
[reader.py](../packages/pynxtools-xas/src/pynxtools_xas/reader.py), [parsers/base.py](../packages/pynxtools-xas/src/pynxtools_xas/parsers/base.py)

- `_Parser` ([base.py:57-298](../packages/pynxtools-xas/src/pynxtools_xas/parsers/base.py#L57)) is a near-copy of the XPS one. The XPS-only metadata-parser support is missing, and the error messages differ slightly.
- `versioning.py` is an XPS copy with small drift: the `_version_ranges_overlap` implementation differs (diff of xas vs xps `versioning.py`).
- `ParsedSpectrum` here uses plain numpy, while XPS uses xarray. They are two incompatible intermediate representations with the same name.
- `handle_data_file` ([L121-153](../packages/pynxtools-xas/src/pynxtools_xas/reader.py#L121)) uses `self.data.update(parser.data)`. Two files that produce the same entry name **overwrite each other silently**. XPS at least merges them (`_combine_datasets`).
- `get_data` ([L197-210](../packages/pynxtools-xas/src/pynxtools_xas/reader.py#L197)) hard-codes three token names (`energy`, `intensity`, `intensity_errors`) instead of resolving paths generically on the dataclass.
- The `read()` override ([L218-239](../packages/pynxtools-xas/src/pynxtools_xas/reader.py#L218)) deletes the skeleton `/ENTRY[entry]/` keys (core issue, §2.3) and drops kwargs.

### 4.3 pynxtools-raman
[reader.py](../packages/pynxtools-raman/src/pynxtools_raman/reader.py), [parsers/base.py](../packages/pynxtools-raman/src/pynxtools_raman/parsers/base.py)

- `_RamanParser` ([base.py:33-147](../packages/pynxtools-raman/src/pynxtools_raman/parsers/base.py#L33)) is a third copy of the parser base, with versioning but without `match_failure_reason`. `versioning.py` is a third copy too.
- Dispatch is extension → hard-coded parser (`.rod` → `RodParser`, `.txt` → `WitecParser`, [L53-59](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L53)) instead of a registry, so a second `.txt` vendor would need reader changes.
- **User config is overwritten.** `_set_parser_data` sets `self.config_file = .../config/<parser default>` unconditionally ([L81](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L81)). Files are dispatched alphabetically by extension, so a user `.json` (`.json` < `.rod` < `.txt`) is always replaced. `-c config.json` is also replaced, because MFR reads kwargs *before* dispatching.
- For a theoretical `.rod` file the reader sets `self.config_file = Path()` ([L104](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L104)), which is `"."`. `parse_flatten_json(".")` then raises `IsADirectoryError` instead of the intended clean abort.
- `get_eln_data` ([L126-176](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L126)) rebuilds ELN keys by **stripping upper-case letters** and uses a hard-coded list of "mixed notation" concepts (L148-158). This is fragile and NXDL-unaware.
- `get_attr` ([L178-206](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L178)):
  - forces `float()` on every value except a hard-coded `space_group` path;
  - mutates `missing_meta_data` as a side effect of lookup;
  - logs a misleading "No axis name" warning for any missing attribute.
- `read()` ([L225-244](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L225)):
  - writes the unused metadata under `self.callbacks.entry_name`, which holds whatever the last loop left there;
  - hard-codes `/@default = "entry"`;
  - drops kwargs.
- **Good pattern to keep:** `unused_attrs` → `COLLECTION[unused_data]`. Unmapped vendor metadata is preserved instead of silently lost, and this should become a core feature.

### 4.4 pynxtools-ellips
[reader.py](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py), [parsers/base.py](../packages/pynxtools-ellips/src/pynxtools_ellips/parsers/base.py)

- `_EllipsParser` ([base.py:27-107](../packages/pynxtools-ellips/src/pynxtools_ellips/parsers/base.py#L27)) is a fourth copy of the parser base, without versioning.
- `CONVERT_DICT` defines `"environment"` twice ([L38](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L38) and [L53](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L53)), so the first mapping is dead.
- The ELN doubles as **parser configuration** (column names, separator, number of header lines, [L64-75](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L64)). This forces `processing_order` (yaml before dat) and makes the `.dat` unreadable without an ELN ([L137-141](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L137)). Parser options should be a separate input, or should be detected from the header.
- `handle_eln_file` stores `eln_data` **and** returns the full flattened ELN into the template ([L134](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L134)). Every ELN key is therefore written even when the config does not reference it, which bypasses the config.
- `handle_dat_file` calls `WoollamParser.is_mainfile` and then `parse()`, which repeats the full check ([L142](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L142), [L150](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L150)).
- `self.data` is not initialised in `__init__`. `get_data` (L155) raises `AttributeError` when no `.dat` was given but the config references `@data`.
- `setup_template` (L163-174) and `post_process` (L176-200) hard-code `/ENTRY[entry]/...`. The software block records the **pynxtools** version rather than the plugin's, which differs from microstructure and apm.
- `set_config_file` (L107) re-implements the base method.

### 4.5 pynxtools-igor
[reader.py](../packages/pynxtools-igor/src/pynxtools_igor/reader.py)

- It re-implements `handle_eln_file`, `get_eln_data` and `set_config_file` (L132-147). `self.eln_data = None` (L118) breaks the base-class type contract. `parse_yml` is called without the entry name, so ELN values always target `/ENTRY[entry]` even in multi-entry mode.
- `get_entry_names` returns `dict_keys`, not a list ([L182](../packages/pynxtools-igor/src/pynxtools_igor/reader.py#L182)).
- `parse_note` splits on **any whitespace** ([L47](../packages/pynxtools-igor/src/pynxtools_igor/reader.py#L47)), so note values that contain spaces are truncated or dropped.
- `process_ibw_files` and `process_pxp_files` duplicate the axis, unit and metadata logic (L210-258 vs L259-332).
- **Good pattern:** file handlers only register paths, and the heavy work happens in `post_process` once all inputs, including the `.entry` description, are known. This makes processing independent of file order.

### 4.6 pynxtools-xrd
[reader.py](../packages/pynxtools-xrd/src/pynxtools_xrd/reader.py), [xrd.config.json](../packages/pynxtools-xrd/src/pynxtools_xrd/xrd.config.json)

- **All four `@link:` entries are silently dropped.** `_clean_mapping` ([L53-67](../packages/pynxtools-xrd/src/pynxtools_xrd/reader.py#L53)) looks up the link target (`"entry/experiment_result/q_norm"`) as a *key* of the config, but the keys are `"/ENTRY/..."`, so no target ever matches. If one did match, `value.copy()` on a `str` (L61) would raise `AttributeError`. The link targets in the JSON are also inconsistent: with and without a leading `/`, and one points at a group (`.../experiment_result/`).
- `_mapping_to_config` (L70-75) emits `@attr:`, but the MFR token is `@attrs`, so any such value would be written as the literal path string (C12). In practice it is dead code because no config value starts with `/`.
- The config is loaded and cleaned in `__init__` (L136-143). `read()` (L194-201) drops all kwargs, so **`-c user.json` and `overwrite_keys` are ignored**, and `suppress_warning=True` hides every missing value.
- `handle_objects` raises "provide a file" when objects are not a dict (L172-180). It runs *before* files, so `self.data` is always empty at that point.
- `suppress_warnings` (L130) is an unused class attribute.
- File reading is delegated to `fairmat_readers_xrd.read_file`, so detection is by extension only.

### 4.7 pynxtools-spm
[reader.py](../packages/pynxtools-spm/src/pynxtools_spm/reader.py), [parsers/\_\_init\_\_.py](../packages/pynxtools-spm/src/pynxtools_spm/parsers/__init__.py), [nxformatters/base_formatter.py](../packages/pynxtools-spm/src/pynxtools_spm/nxformatters/base_formatter.py)

- It subclasses `BaseReader`, and `read()` has no kwargs ([L64-69](../packages/pynxtools-spm/src/pynxtools_spm/reader.py#L64)).
- The formatter is chosen by a hard-coded `if/elif` chain on (ELN `experiment_technique`, extension) ([L109-193](../packages/pynxtools-spm/src/pynxtools_spm/reader.py#L109)). It is not cross-checked against the requested NXDL, so NXsts versus NXstm is not validated.
- **The parser is selected from user-typed ELN values** (`software/vendor`, `software/model`) through a nested dict ([parsers/\_\_init\_\_.py:56-99](../packages/pynxtools-spm/src/pynxtools_spm/parsers/__init__.py#L56)). A typo makes it fall back to "try every parser" with `except Exception: pass` ([L181](../packages/pynxtools-spm/src/pynxtools_spm/parsers/__init__.py#L181)), which **swallows genuine parse errors**. The vendor and version are written in the file headers (e.g. FLT `Program=SPMLab`, `Version=1.00`), so they can be detected.
- Indentation bug in the file loop ([L91-100](../packages/pynxtools-spm/src/pynxtools_spm/reader.py#L91)): the `else` belongs to the yaml `if`, so every data and JSON file ends up in `auxiliary_files`. The list is unused anyway. If several data files are given, the last one wins silently.
- `manually_filter_data_type` ([L37-55](../packages/pynxtools-spm/src/pynxtools_spm/reader.py#L37)) **`deepcopy`s the entire template, including image arrays**, to run a few hard-coded casts, and reports failures with `print`.
- The template is then copied again into `filled_template` (L195-203), and `/ENTRY[entry]/definition/@version` is hard-coded (L205).
- The nested config DSL (`raw_path`, `@default:`, `@default_link:`, `#note`) and `walk_though_config_nested_dict` re-implement what `fill_from_config` already does, with a different syntax.

### 4.8 pynxtools-em
[reader.py](../packages/pynxtools-em/src/pynxtools_em/reader.py), [utils/io_case_logic.py](../packages/pynxtools-em/src/pynxtools_em/utils/io_case_logic.py)

- It subclasses `BaseReader`, `read()` has no kwargs ([L76-81](../packages/pynxtools-em/src/pynxtools_em/reader.py#L76)), and `template.clear()` (L87) discards the NXDL skeleton.
- Production code imports from `examples/` ([L27-36](../packages/pynxtools-em/src/pynxtools_em/reader.py#L27)). A `production: bool = True` switch with a dead development path sits in `read()` (L89-97).
- **Brute-force dispatch:** for one data file, 15 parser classes are instantiated in sequence ([L150-171](../packages/pynxtools-em/src/pynxtools_em/reader.py#L150)). Each constructor opens the file to self-check (detection happens as a side effect of `__init__`). After that, the Tescan and JEOL parsers run, and with two files the Hitachi and MRC parsers run as well (L173-183). Nothing prevents two parsers from both claiming a file.
- Detection cost, Velox: `check_if_supported` calls `emd.file_reader` and **loads the whole EMD (data included) just to decide support** ([rsciio_velox.py:101](../packages/pynxtools-em/src/pynxtools_em/parsers/rsciio_velox.py#L101)). The in-code TODO acknowledges the memory problem.
- Detection cost, TIFF: each TIFF parser mmaps the file, opens it with PIL and reads tags separately (e.g. [image_tiff_zeiss.py:83-106](../packages/pynxtools-em/src/pynxtools_em/parsers/image_tiff_zeiss.py#L83)).
- **Full-file SHA-256 per parser:** every parser that accepts a file computes its SHA-256 just for a log line (e.g. [image_tiff_zeiss.py:165-166](../packages/pynxtools-em/src/pynxtools_em/parsers/image_tiff_zeiss.py#L165), [rsciio_velox.py:145-146](../packages/pynxtools-em/src/pynxtools_em/parsers/rsciio_velox.py#L145)).
- **Suffix logic loses files:** in `check_validity_of_file_combinations` ([L104-120](../packages/pynxtools-em/src/pynxtools_em/utils/io_case_logic.py#L104)), the loop `break`s at `.mtex.h5`. Every suffix listed after it (`.h5`, `.hdf5`, `.hdr`, `.mrc`, `.mrc.mdoc`, `.rawtlt`, `.shifts`, `.xml`) is ignored as soon as an `.mtex.h5` is present.
- **Hidden naming contract:** ELN files are recognised only by name suffix ([L125-134](../packages/pynxtools-em/src/pynxtools_em/utils/io_case_logic.py#L125)): `eln_data.yaml` or `nxs_eln_data.yml`, but not `eln_data.yml`. Any other `*.yaml` is silently ignored.
- The version concept (`EmSchemaVersion` with exact string match) differs from the xps/xas/raman `VersionRange` concept.
- **Good to keep:** the configuration dictionaries ([configurations/](../packages/pynxtools-em/src/pynxtools_em/configurations/)) with pint units and dtype casting (`map_to_f8`, `map_to_str`) are declarative and close to the MFR config. They add what MFR lacks (unit conversion, dtype enforcement, vector assembly from several source keys).

### 4.9 pynxtools-apm
[reader.py](../packages/pynxtools-apm/src/pynxtools_apm/reader.py), [utils/io_case_logic.py](../packages/pynxtools-apm/src/pynxtools_apm/utils/io_case_logic.py)

- **Crash when no `*.oasis.specific.yaml` is given:** `nx_apm_cfg` is only assigned inside `if len(case.cfg) == 1` ([L81](../packages/pynxtools-apm/src/pynxtools_apm/reader.py#L81)) but is always read at [L92](../packages/pynxtools-apm/src/pynxtools_apm/reader.py#L92), which raises `UnboundLocalError`.
- `.hdf5` appears in **both** `VALID_FILE_NAME_SUFFIX_RECON` ([L33](../packages/pynxtools-apm/src/pynxtools_apm/utils/io_case_logic.py#L33)) and `..._RANGE` ([L46](../packages/pynxtools-apm/src/pynxtools_apm/utils/io_case_logic.py#L46)). Both share the same `self.case[".hdf5"]` list, so an `.hdf5` file is added to **both** `reconstruction` and `ranging` and parsed in both roles.
- `"db.yaml"` comes after `".yaml"` in the config suffix list, so it can never match.
- `is_valid` is unconditionally `True` ([L145](../packages/pynxtools-apm/src/pynxtools_apm/utils/io_case_logic.py#L145)), which makes the "unsupported combination" branch in the reader dead code. A second reconstruction file is ignored silently (`len(...) == 1`).
- `report_workflow` computes a full-file SHA-256 of every reconstruction and ranging file (L189, L199). With several files, all of them write to the same template path, so the last one wins.
- `read()` has no kwargs, uses `template.clear()`, has a hard-coded `entry_id = 1` and contains `logger.info(os.getcwd())`.

### 4.10 pynxtools-microstructure
[reader.py](../packages/pynxtools-microstructure/src/pynxtools_microstructure/reader.py)

- `BaseReader`, no kwargs (L44-49), `template.clear()` (L55).
- It **imports internals from pynxtools-em** (`SEPARATOR`, `NxEmAtomTypesResolver`, `NxEmDefaultPlotResolver`, [L26-28](../packages/pynxtools-microstructure/src/pynxtools_microstructure/reader.py#L26)). That is a cross-plugin coupling to non-public modules (10 imports in total).
- The I/O logic is a hand-written loop over two compound suffixes (L60-66). The ELN-like YAML is used only if an `.mtex.h5` is present; otherwise it is silently ignored.
- Profiling and provenance are written inline (L96-105) in yet another layout.

---

## 5. Cross-cutting findings

### 5.1 Duplicated and forked code

| Concept | Copies | Notes |
|---|---|---|
| Parser base (`_Parser`, `is_mainfile`, `matches_file`, `_is_mainfile`, `parse`/`_parse`) | xps, xas, raman, ellips | 4 drifting variants: with or without versioning, `match_failure_reason`, metadata parsers |
| `versioning.py` (`VersionRange`, `normalize_version`, `is_version_supported`) | xps, xas, raman | logic drift in `_version_ranges_overlap` |
| `ParsedSpectrum` | xps (xarray), xas (numpy) | same name, different types |
| `set_config_file(replace=)`, `get_eln_data` with generic `/ENTRY` fallback, `_search_metadata`, `_collect_supported_extensions` | xps, xas | verbatim copies |
| `set_config_file` / `handle_eln_file` re-implementations of MFR built-ins | ellips, igor, raman, xas, xps | 5 overrides of the same 5-line method |
| `mapping_functors_pint`, `nxs_concepts`, `get_checksum`, `pint_custom_unit_registry`, `interpret_boolean`, `string_conversions`, `profiling`, `custom_logging`, `hfive_base`, `oasis_config`, `oasis_eln`, `io_case_logic`, … | apm ↔ em (↔ microstructure) | 15 shared module names, all except `get_gitrepo_commit.py` diverged (2 to 261 differing lines) |
| `/@default` / NXdata default selection | xrd, ellips, raman, xps, em, apm, spm | 7 different implementations |
| Profiling / provenance (program name, version, filling time) | apm, em, microstructure, ellips | different template paths and different "which version" |

### 5.2 File-format checking

Five strategies are in use (see §1). Only xas and xps meet all of the following:
1. positive identification beyond the extension (magic bytes, header tokens);
2. version detection with declared supported ranges;
3. ambiguity detection (more than one parser claims a file → error);
4. a diagnosable rejection reason for each parser.

Even there, a file is opened N+1 times. Nobody shares a single *probe* of the file: the first few KB, HDF5 signature and top-level keys, TIFF tags, the extension chain.

### 5.3 Hard-coding hotspots

- **Entry names:** `/ENTRY[entry]` or `entry1` are hard-coded in apm, em, microstructure, spm, ellips, raman, xrd and igor (ELN), although MFR supports `get_entry_names()`.
- **Extensions in reader code** instead of on the parser classes: raman, igor, spm, apm, em, microstructure.
- **NeXus paths in Python:** ellips `post_process`, spm `manually_filter_data_type`, raman `get_eln_data` concept list, xps `set_nxdata_defaults`, and all of apm/em/microstructure (functor dicts).
- **Parser lists** are hard-coded in reader modules. There is no entry-point or registry discovery, so adding a vendor means editing the reader.
- **Config paths** are built with `Path(__file__).parent / "config" / ...` in each plugin.

### 5.4 ELN handling: seven variants for one NOMAD output format

1. MFR built-in `handle_eln_file` (bound to the first entry at dispatch time): nobody uses it unchanged.
2. igor: `parse_yml` without an entry name.
3. raman: `parse_yml(parent_key="/ENTRY[entry]")` plus upper-case stripping heuristics.
4. xas and xps: `parse_yml(parent_key="/ENTRY")`, entry-specific override, generic fallback, datetime → ISO.
5. ellips: `flatten_and_replace`, `ignore_keys`, written *directly* into the template, and also used as parser options.
6. spm: `flatten_and_replace` inside the formatter, plus ELN-driven parser selection.
7. apm, em, microstructure: own `oasis_eln` parsers with functor dicts, recognised by file-name suffix.

### 5.5 Resource usage

| Where | Cost |
|---|---|
| em Velox detection | whole EMD loaded into RAM just to check support |
| em, apm parsers | full-file SHA-256 per accepting parser, plus `report_workflow` hashing again |
| em dispatch | ~15 constructor-time file opens and PIL decodes per data file |
| xps, xas dispatch | N_parsers + 1 header reads per file |
| spm | `deepcopy` of full template (arrays included), then a second copy |
| xps | second full `Template` copy in `read()` |
| json_map | eager HDF5 load plus a second open |
| core `get_reader` | re-executes the reader module on each call |
| MFR `fill_from_config` | config re-sorted per entry |

### 5.6 Packaging and consistency

- Minimum `pynxtools` pins range from `>=0.13.0` to `>=0.16.0` (ellips, igor, raman and xrd pin 0.13.0, xps 0.13.1, apm 0.14.1, em and microstructure 0.14, xas 0.15.2, spm 0.16.0). Plugins that rely on newer MFR features (`processing_order`, built-in `set_config_file`) should pin the version that introduced them.
- Two licence header styles are in use (REUSE SPDX vs Apache boilerplate).
- Logging: the `"pynxtools"` logger is used in most plugins, but `pynxtools-microstructure` has its own logger, apm and em use `custom_logging`, and spm uses `print`.
- Tests: all plugins use `ReaderTest`. pynxtools-xas and pynxtools-xrd have one test file each.

---

## 6. Bug list (by severity)

**Confirmed** means reproduced or unambiguous from the code path. **Likely** means it follows from reading the code but was not executed.

| # | Severity | Status | Where | Effect |
|---|---|---|---|---|
| B1 | high | confirmed (reproduced) | core [utils.py:369](../packages/pynxtools/src/pynxtools/dataconverter/readers/utils.py#L369) via [multi/reader.py:144](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L144) | literal fallbacks containing No/Yes/On/Off are silently dropped |
| B2 | high | confirmed | apm [reader.py:92](../packages/pynxtools-apm/src/pynxtools_apm/reader.py#L92) | `UnboundLocalError` when no oasis config yaml is given |
| B3 | high | confirmed | apm, em, microstructure, spm `read()` without `**kwargs` | `TypeError` with `-c` or any extra converter kwarg |
| B4 | high | confirmed | xrd [reader.py:53-67](../packages/pynxtools-xrd/src/pynxtools_xrd/reader.py#L53) | all `@link` entries dropped; `str.copy` crash path |
| B5 | high | confirmed | raman [reader.py:81](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L81) | user config silently replaced by built-in config |
| B6 | medium | confirmed | em [io_case_logic.py:106,118](../packages/pynxtools-em/src/pynxtools_em/utils/io_case_logic.py#L106) | files after `.mtex.h5` in the suffix list are ignored |
| B7 | medium | confirmed | apm [io_case_logic.py:33,46](../packages/pynxtools-apm/src/pynxtools_apm/utils/io_case_logic.py#L33) | `.hdf5` parsed as both reconstruction and ranging |
| B8 | medium | confirmed | core [multi/reader.py:246](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L246) | `!` removal also removes sibling groups that share a prefix |
| B9 | medium | confirmed | raman [reader.py:104](../packages/pynxtools-raman/src/pynxtools_raman/reader.py#L104) | theoretical `.rod` → `IsADirectoryError` instead of a clean skip |
| B10 | medium | confirmed | spm [parsers/\_\_init\_\_.py:181](../packages/pynxtools-spm/src/pynxtools_spm/parsers/__init__.py#L181) | all parser exceptions swallowed |
| B11 | medium | confirmed | xrd [reader.py:201](../packages/pynxtools-xrd/src/pynxtools_xrd/reader.py#L201) | `-c` / `overwrite_keys` ignored |
| B12 | medium | likely | xas [reader.py:150](../packages/pynxtools-xas/src/pynxtools_xas/reader.py#L150) | same entry name from two files → silent overwrite |
| B13 | low | confirmed | core [multi/reader.py:522](../packages/pynxtools/src/pynxtools/dataconverter/readers/multi/reader.py#L522) | upper-case extensions ignore `processing_order` |
| B14 | low | confirmed | igor [reader.py:47](../packages/pynxtools-igor/src/pynxtools_igor/reader.py#L47) | wave-note values with spaces lost |
| B15 | low | confirmed | ellips [reader.py:38,53](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L38) | duplicate dict key, first mapping dead |
| B16 | low | likely | ellips [reader.py:155](../packages/pynxtools-ellips/src/pynxtools_ellips/reader.py#L155) | `AttributeError` if no `.dat` but config uses `@data` |
| B17 | low | confirmed | spm [reader.py:99-100](../packages/pynxtools-spm/src/pynxtools_spm/reader.py#L99) | mis-indented `else`; multiple data files → last wins silently |
| B18 | low | confirmed | apm [io_case_logic.py:145](../packages/pynxtools-apm/src/pynxtools_apm/utils/io_case_logic.py#L145) | validity check disabled; extra reconstruction or ranging files ignored |
| B19 | info | confirmed | em [reader.py:150-183](../packages/pynxtools-em/src/pynxtools_em/reader.py#L150) | two parsers can both write into the template for the same file |

---

## 7. Patterns worth promoting to the core

| Pattern | Where it lives today | Why |
|---|---|---|
| Parser registry with `is_mainfile`, `match_failure_reason`, `supported_versions`, ambiguity check | xps, xas | methodical, diagnosable format checking |
| Metadata or sidecar parsers that attach to a compatible primary parser regardless of order | xps `_XPSMetadataParser` | covers em sidecars (Hitachi, MRC, JEOL, Tescan) and apm ranging + reconstruction |
| Per-parser default config, overridable by the user | xps, xas | removes config hard-coding from readers |
| Typed intermediate representation (`ParsedSpectrum`) | xps, xas | decouples parsing from NeXus paths and is testable |
| Deferred processing in `post_process` | igor, ellips, raman | makes processing independent of file order |
| `unused_attrs` → `COLLECTION[unused_data]` | raman | no silent metadata loss |
| Declarative unit and dtype mapping (pint, `map_to_f8`) | apm, em | unit-safe values without Python code |
| Entry-specific ELN with generic `/ENTRY/` fallback | xps, xas | one ELN for multi-entry outputs |
| Shared `ReaderTest` regression harness | all | safety net for the refactor |
