# Unifying the pynxtools plugins around `MultiFormatReader`: implementation plan

This plan builds on [FINDINGS.md](FINDINGS.md). IDs such as **C3**, **B5** or **§5.4** refer to that document.

## Goals

1. **One central element.** Every plugin reader is a `MultiFormatReader` (MFR) subclass. Plugins contribute *parsers* and *configs*, not pipelines.
2. **No hard-coding.** Extensions, versions, entry names, config paths, NeXus paths and parser lists are declared as data on parser classes, in config files or through entry points, never in `read()`.
3. **Fewer mistakes.** Configs are validated against the NXDL, nothing is dropped silently, and parse errors surface instead of being swallowed.
4. **Methodical format checking.** Every input file goes through the same probe → identify → version-check → ambiguity-check → parse sequence, with a diagnosable rejection reason for each parser.
5. **Lower resource use.** Each file is probed once, nothing is loaded fully just to detect it, hashing happens at most once and is optional, there are no template deep copies, and HDF5 is loaded lazily.

## Guiding principles

- **Additive first, then migrate, then delete.** New core APIs land in pynxtools as optional features. Plugins migrate one at a time. Duplicated plugin code is removed only after its plugin is migrated and its regression tests are green.
- **Output must not change unintentionally.** Each migration step has to reproduce the reference NeXus files of the pre-redesign baseline (Phase 0), except where a change is an explicit bug fix that is documented in the plugin changelog.
- **Keep the good ideas** listed in FINDINGS §7. Most of the new core is a promotion of code that already exists in pynxtools-xps.

## Phase overview

| Phase | Content | Repos | Depends on |
|---|---|---|---|
| 0 | Safety net: pre-redesign baseline of outputs and resources (done) | all | — |
| 1 | Quick bug fixes (no architecture change) | all | 0 |
| 2 | Core: parser framework (`FileProbe`, `FileParser`, versioning, registry) | pynxtools | 0 |
| 3 | Core: MFR v2 (dispatch, config precedence, ELN, finalize, entries, kwargs) | pynxtools | 2 |
| 4 | Core: config language unification and validation | pynxtools | 3 |
| 5 | Plugin migrations (ordered by effort) | plugins | 3 (and 4 for apm, em, microstructure, spm) |
| 6 | Resource optimisation | pynxtools + plugins | 2–5 |
| 7 | Governance: conformance tests, template, docs, pins | all | 5 |

---

## Phase 0: Safety net (done: the pre-redesign baseline)
**Issue:** the refactor touches every reader. Without a baseline, regressions in NeXus content or in resource use would go unnoticed.
**Status:** covered by the pre-redesign baseline in [`pynxtools_baseline_scripts/`](pynxtools_baseline_scripts/) (guide: [`BASELINE_GUIDE.md`](pynxtools_baseline_scripts/BASELINE_GUIDE.md)). It records enough about the current behaviour of pynxtools and its plugins to detect unintended changes, so no further Phase 0 work is required before Phase 1. The items under "Known limits" are optional and are taken up only if maintainers ask for them.

### Step 0.1: Reference outputs (done)
- `run_baseline.sh` runs the pytest suite of pynxtools and of every plugin in a `nomad-distro-dev` checkout, records every `convert()` call (mostly the `ReaderTest` examples), and replays each conversion in a fresh process. The produced `.nxs` files, all terminal output, the test results and an annotator dump of every output are kept per run.
- The em and microstructure conversion tests are skipped upstream, so [`extra_conversions.tsv`](pynxtools_baseline_scripts/extra_conversions.tsv) adds em's `tests/data/default` example, three InGaN EDS `.edaxh5` files and a microstructure `*.mtex.h5` example.
- The pinned commit of every package is in [`baseline_commits_links.md`](pynxtools_baseline_scripts/baseline_commits_links.md). Three runs from 2026-10-26 are committed under `baseline_results/`, each with 65 recorded conversions (61 `OK`, and 4 `CONVERT_FAILED` from pynxtools core tests that pass invalid inputs on purpose).

### Step 0.2: Resource numbers (done)
- Every replayed conversion has its wall time, CPU time and peak RAM in `summary_conversions.csv`, and each test suite has the same in `summary_tests.csv`.
- `monitor_resources.py` logs CPU, RAM, threads and disk I/O of every process during the run (`00_monitor/`). The three committed runs give the run-to-run noise used to set the comparison tolerances.

### Step 0.3: Comparing after each change (done)
After a migration step, rebuild the environment the same way, run the same scripts on the same machine, and compare:

```bash
../.venv/bin/python compare_baselines.py baseline_results/baseline_<before> baseline_results/baseline_<after> --out <report>
```

`compare_baselines.py` reports test outcome changes, conversion status changes, NeXus content differences (h5py, with float tolerances, volatile items such as timestamps ignored), new or removed WARNING/ERROR messages, and wall time, CPU or peak RAM changes above `--time-tol` / `--rss-tol`. Its exit code is `1` when functional regressions are found (also for resource regressions with `--fail-on-resources`). In this plan, "the baseline comparison is clean" means exit code `0`, or every reported difference is an intentional bug fix listed in the plugin changelog.

### Known limits (optional follow-ups)
These are not required steps. Each can be added later if maintainers ask for it.
- **Coverage gaps.** pynxtools-xas and pynxtools-xrd have one test file each (§5.6), so not every parser and vendor is covered. pynxtools-apm is excluded from the baseline (it is not a distro submodule). There are no large-file inputs (for example a large Velox EMD, SXM, XPS SLE or APM `.apt`).
- **No user `-c` config or upper-case extension tests**, so B3, B5, B11 and B13 are not caught by the baseline. Add such a test together with the corresponding Phase 1 fix.
- **Not in each plugin's CI.** The baseline is run by hand in a `nomad-distro-dev` checkout. There are no golden references in each plugin's `tests/data/**/ref/` and no `tests/benchmarks/` pytest-benchmark fixture in pynxtools.
- **No `open()` counts.** Resource numbers are time, CPU and peak RAM only.
- **No cross-plugin CI matrix** that installs pynxtools from a PR branch together with each plugin's `main`. Until there is one, run the baseline (which covers all plugins together) before merging core changes such as the entry-skeleton change in Step 3.8.

---

## Phase 1: Quick bug fixes

These can ship immediately, independent of the architecture work. Each one is a small PR with a regression test.

| Step | Bug | Fix |
|---|---|---|
| 1.1 | B1 `is_boolean` unanchored | Anchor it: `re.fullmatch(r"(?i)true\|false\|on\|off\|yes\|no", expr.strip())`. Make `to_bool` case-insensitive. In `try_convert`, never return `None` for a non-empty literal. |
| 1.2 | B8 prefix removal | `key == group or key.startswith(group + "/")` in `has_missing_main`. |
| 1.3 | B13 case | Lower-case the extension in `get_processing_order` and in `processing_order` itself. |
| 1.4 | B3 kwargs | Add `**kwargs` to `BaseReader.read` and to the apm, em, microstructure and spm `read()` signatures (interim fix until Phase 5). |
| 1.5 | B2 apm unbound | Initialise `nx_apm_cfg = None` before the `if`. |
| 1.6 | B7 apm `.hdf5` | Remove `.hdf5` from one list, or classify it by content (see Step 5.9). |
| 1.7 | B6 em `.mtex.h5` break | Match each file to its **longest** matching suffix once (`max(..., key=len)`) instead of breaking the suffix loop. |
| 1.8 | B4, B11 xrd | Delete `_clean_mapping` and `_mapping_to_config`, fix the four link targets in `xrd.config.json` to absolute `/ENTRY[entry]/...` paths, and drop the `read()` override (pass kwargs through). |
| 1.9 | B5, B9 raman | In `_set_parser_data`, set the config only if none is set (`replace=False` semantics). For theoretical spectra, `return {}` without touching `config_file`. |
| 1.10 | B10 spm | Catch only the parser's declared exceptions, log each rejection reason, and re-raise if no parser succeeds. |
| 1.11 | B14 igor | Split notes on line breaks only: `note.splitlines()` and `line.split("=", 1)`. |
| 1.12 | B15, B16 ellips | Remove the duplicate key and initialise `self.data = {}`. |
| 1.13 | B17 spm | Fix the indentation and raise if more than one data file is given. |
| 1.14 | B12 xas | Detect entry-name collisions and either merge (as XPS `_combine_datasets` does) or suffix the name. |
| 1.15 | B20 core pickle | Drop `.pickle` from the json_map extensions, or accept it only behind an explicit opt-in kwarg that the NOMAD dataconverter never sets. |
| 1.16 | B21 xps, xrd rounding | Compute the minimal step without rounding (compare with `np.isclose`), build the VAMAS axis as `start + i * step` unrounded, and stop rounding `y_cps`. Add a test file with a step below 0.005. |
| 1.17 | B22 xps VAMAS binding energy | Compare the abscissa label case-insensitively and flip the energy axis together with every `y` array (or don't flip and record the energy type). Add a VAMAS test file with a binding-energy axis. |
| 1.18 | B23 xrd | Map `kbeta/@units` to `@attrs:metadata/source/kBeta@units`. |
| 1.19 | B24 em | Read phase indices and imaging mode from the Oxford file, or leave the fields out when they are unknown; remove the example-specific constants. |
| 1.20 | B25, B29 time zones | Never use the converting machine's zone. If the file has no zone, take it from the ELN or a kwarg, otherwise keep the timestamp naive and log a warning. Leave `start_time` out instead of writing `0001-01-01`. |
| 1.21 | B26 xps SLE | Write the transmission function only when the file has one, and warn or raise when its length differs from the energy axis. |
| 1.22 | B27, B28 spm | Log a warning when the sensitivity unit cannot be parsed (catch pint errors only). Replace the prose `@units` in `bruker_spm_afm.json` with real lookups or `@default:` values. |
| 1.23 | B30 xps VAMAS mapping | Raise a clear "unsupported scan mode" error for `MAPPING` until it is implemented. |
| 1.24 | B31 igor | Use `Path(file).stem` for the entry name and check for collisions (same fix as 1.14). |
| 1.25 | B32 em | Write `percent` as the unit; `normalization = weight_percent` already says it is a mass fraction. |
| 1.26 | B33 xps | Fix the trailing comma in `template.json`, or delete the file and the dead `config_file` class default. |
| 1.27 | B34 readers-xrd | Leave the `Start`/`Step` header lines out when the values are unknown. |
| 1.28 | B35, B36 | Remove the duplicate keys. Parse uploaded XML with `defusedxml` or an lxml parser with `resolve_entities=False, no_network=True`. |

---

## Phase 2: Core parser framework (in pynxtools)

**Issue:** format checking is implemented five ways (§5.2), the best implementation is copied four times (§5.1), and files are opened N+1 times.
**Target:** a new module `pynxtools/dataconverter/readers/parsers/` (public API) that promotes the xps `_Parser` design.

### Step 2.1: `versioning.py` to core
Move `VersionTuple`, `VersionRange`, `normalize_version`, `is_version_supported` and `_version_ranges_overlap` from pynxtools-xps into `pynxtools.dataconverter.readers.parsers.versioning`. Reconcile the drift between the xas and xps copies, take the better tested one, and port both test suites.
**Done when:** xps, xas and raman can import it. Their local copies stay as thin re-exports until Phase 5.

### Step 2.2: `FileProbe`: inspect each file once
**Issue:** every parser re-opens and re-reads the same header, and em loads whole files just to detect them (§5.5).
**How:** create a cheap, cached, read-only view of a file:

```python
@dataclass(frozen=True)
class FileProbe:
    path: Path
    suffixes: tuple[str, ...]          # lower-cased, full chain: (".mtex", ".h5")
    size: int
    head: bytes                        # first N bytes (default 64 KiB), read once

    @cached_property
    def text_head(self) -> str | None: ...        # decoded head if it looks like text
    @cached_property
    def is_hdf5(self) -> bool: ...                # b"\x89HDF\r\n\x1a\n" at offset 0/512/1024/…
    @cached_property
    def hdf5_root_keys(self) -> frozenset[str]: ...   # opened once, groups/attrs only, no data
    @cached_property
    def tiff_tags(self) -> Mapping[int, Any]: ...     # tags only (PIL lazy / tifffile)
    @cached_property
    def is_zip(self) -> bool: ...

    def has_suffix(self, suffix: str) -> bool:        # compound-suffix aware: ".mtex.h5", "range_.h5"
        ...
```

Probes are created once per input file by the reader and passed to every parser's `matches_file(probe)`.
**Done when:** unit tests cover HDF5, TIFF, zip, text and binary probes, and a single probe of a 5 GB file reads at most a few MB.

### Step 2.3: `FileParser` base class
Promote the xps `_Parser` and make it probe-based:

```python
class FileParser(ABC):
    # --- declarative identity (no hard-coding in readers) ---
    supported_file_extensions: ClassVar[tuple[str, ...]] = ()   # compound suffixes allowed
    supported_versions: ClassVar[tuple[VersionRange, ...]] = ()
    supported_vendor: ClassVar[str | None] = None
    role: ClassVar[Literal["primary", "metadata", "sidecar"]] = "primary"
    compatible_primary: ClassVar[tuple[type["FileParser"], ...]] = ()  # for metadata/sidecar
    default_config: ClassVar[str | Mapping[str, str] | None] = None   # resource path(s) or per-suffix
    supported_nxdls: ClassVar[tuple[str, ...]] = ()                     # optional narrowing

    # --- identification (cheap, never raises) ---
    @classmethod
    def detect_version(cls, probe: FileProbe) -> VersionTuple | None: return None
    @classmethod
    @abstractmethod
    def matches_file(cls, probe: FileProbe) -> bool: ...
    @classmethod
    def match(cls, probe: FileProbe) -> MatchResult: ...   # ok | reason; wraps the three checks

    # --- parsing ---
    def parse(self, probe: FileProbe, **options) -> None: ...   # does NOT re-check
    @abstractmethod
    def _parse(self, path: Path, **options) -> None: ...
    @property
    def data(self) -> ParsedData: ...
    def post_process(self, context: "ReaderContext") -> None: ...   # ELN-dependent derivations
```

Key differences from today's copies:
- Identification is `classmethod` + probe, so no instance or file open is needed per check.
- `match()` returns a reason instead of raising, which merges `is_mainfile` and `match_failure_reason`.
- `parse()` trusts the dispatcher, so the second `_is_mainfile` disappears.
- `**options` are **explicitly declared** parser options (see Step 3.5), never the converter's kwargs.

**Done when:** the xps parsers pass their tests subclassed from `FileParser` (through a compatibility shim).

### Step 2.4: `ParsedData`: a common intermediate representation
**Issue:** `ParsedSpectrum` exists in two incompatible forms, and readers hand-write `get_attr` and `get_data` lookups (§4.2, §4.3).
**How:**

```python
@dataclass
class ParsedData:
    entry_name: str
    data: dict[str, Any]          # arrays / xarray objects addressable by "@data:<path>"
    metadata: dict[str, Any]      # flat, "/"-separated, addressable by "@attrs:<path>"
    dims: dict[str, list[str]]    # for "*" expansion
    unused: set[str] = field(default_factory=set)  # tracks metadata never consumed by the config
    source: Path | None = None
```

Plugins may subclass it (xps keeps an xarray-backed `ParsedSpectrum(ParsedData)`), but the generic MFR lookups (Step 3.4) work on the base fields.

### Step 2.5: `ParserRegistry` and discovery
**Issue:** parser lists are hard-coded in readers (§5.3).
**How:**
- `ParserRegistry(parsers: Iterable[type[FileParser]])`, with `identify(probe) -> type[FileParser]`. It raises a typed `AmbiguousFormatError` if more than one matches, and an `UnsupportedFileError` that carries every parser's reason if none matches.
- Pre-filter by extension, using an index from suffix to parsers, so only candidate parsers run `matches_file`.
- Optional discovery through an entry-point group `pynxtools.parsers.<reader>`, so a third party can add a vendor parser without touching the plugin.

**Done when:** a registry-level test checks that **no two parsers of a plugin claim the same example file** (an automatic ambiguity audit).

---

## Phase 3: `MultiFormatReader` v2 (in pynxtools)

All changes are backwards compatible: existing `self.extensions` dicts keep working.

### Step 3.1: Registry-based dispatch next to extension dispatch
**Issue:** C1 and C3. Extension-only dispatch, no compound suffixes.
**How:**
- New class attribute `parsers: ClassVar[list[type[FileParser]]] = []`. For every input file, MFR builds a `FileProbe` and then:
  1. uses the handler in `self.extensions` if the **longest matching suffix** has one (ELN yaml, config json, and legacy handlers);
  2. otherwise asks the registry built from `self.parsers` and instantiates and runs the identified parser.
- Unknown or unsupported files: by default, `UnsupportedFileError` (with reasons) instead of a warning. A `strict=False` kwarg restores "warn and skip". A missing file is always an error (C4).
- Primary parsers run first, then metadata and sidecar parsers, which attach to compatible primaries regardless of input order (the xps `_pending_metadata` logic moves into core). This replaces `processing_order` for most plugins.

**Done when:** the xps `handle_data_file` and `_collect_supported_extensions` are deleted and xps tests are green.

### Step 3.2: Config-file precedence in one place
**Issue:** five `set_config_file` re-implementations; user configs silently overwritten (B5, B11).
**How:** MFR resolves the config once, after dispatch, with a fixed precedence:
1. `config_file` kwarg (`-c`), or a `.json` input file (two user configs raise an error);
2. the identified parser's `default_config` (per-suffix mapping supported);
3. the reader's class-level `default_config`.

Configs are loaded with `importlib.resources`, never with `Path(__file__)` string building. The chosen config path is logged and recorded in the provenance (Step 3.7).
**Done when:** all `set_config_file` overrides are deleted, and a test that converts with a user `-c` config ("user config wins") passes in every plugin. The baseline has no such test (Phase 0, Known limits), so add it here where a plugin lacks one.

### Step 3.3: Unified ELN handling
**Issue:** seven variants (§5.4); ELN bound to the wrong entry (C6).
**How:**
- `handle_eln_file` stores the raw YAML and flattens it with `parent_key="/ENTRY"` (entry-agnostic), using the class-level `CONVERT_DICT` and `REPLACE_NESTED` plus a new `ELN_IGNORE_KEYS`. Datetimes are converted to ISO strings.
- `get_eln_data(key, path)` looks up `path or key` in this order: entry-specific `/ENTRY[<name>]/...`, then generic `/ENTRY/...`. This is the xps and xas logic, made generic.
- Domain extras become hooks:
  - xps formula → `atom_types` becomes an `eln_post_process(eln_data)` override;
  - ellips parser options are taken from a `parser_options` ELN section (see Step 3.5).
- ELN content enters the template **only through the config** (`@eln` tokens). Readers no longer return ELN dicts from handlers (ellips).
- Concept-name normalisation (raman's upper-case stripping) is replaced by NXDL-aware matching: resolve `@eln` without a path by looking up the *NXDL concept path* of `key`, using the existing `helpers.convert_data_converter_dict_to_nxdl_path`.

**Done when:** no plugin overrides `handle_eln_file` or `get_eln_data` except through `eln_post_process`.

### Step 3.4: Generic `get_attr`, `get_data` and `get_data_dims` on `ParsedData`
**Issue:** each plugin hand-writes lookups with different semantics: suffix match, float coercion, hard-coded token names.
**How:** the default implementations resolve against `self.parsed[entry_name]`:
- `@attrs:path`: exact key, then a suffix match on `/path` (xps `_search_metadata` semantics). Empty values (`""`, `"None"`, all-empty lists) count as missing. The key is marked as consumed in `ParsedData.unused`.
- `@data:path`: exact key in `ParsedData.data`. Nested `a/b` traversal and xarray access (`.values`, `.coords[...]`) use the json_map helpers.
- `get_data_dims`: `ParsedData.dims`.
- Type coercion is **not** done in lookups. It moves into the config (Step 4.2) or into validation.

### Step 3.5: Explicit parser options
**Issue:** xps and xas pass every converter kwarg to the parsers, while ellips takes parser options from ELN keys.
**How:** `FileParser.options_schema` (a small dataclass or pydantic model). MFR fills it from, in order: the `--parser-option key=value` CLI kwarg, a `parser_options:` section in the ELN or params file, and defaults. Unknown options are an error.

### Step 3.6: `finalize()` hook and standard post-steps
**Issue:** C5. Four plugins override `read()` only to post-edit the template, and every override drops kwargs.
**How:** add `finalize(template) -> None`, called after `fill_from_config`. Standard post-steps move into MFR and are switchable by class attributes:
- `unused_metadata_group: str | None`: writes `ParsedData.unused` to `/ENTRY[e]/COLLECTION[<group>]/...` (the raman feature, now available to all).
- Orphan `@units` removal and unit validation (from xps).
- Link `@target` attributes (from xps) and **link target existence checks** (C11).
- Default plot selection: `default_nxdata_strategy` (first NXdata, a configured name, or a callable) replaces seven implementations of `/@default` (§5.1).

After this step, `read()` is **final**: plugins must not override it. This is enforced by a conformance test (Step 7.1).

### Step 3.7: Provenance and profiling
**Issue:** four layouts for "which program and version produced this" (§5.1).
**How:** MFR writes one standard block, configurable through the `provenance_path` class attribute, containing: plugin distribution name and version (from `importlib.metadata` using the module's distribution), pynxtools version, parser class and detected file version per input, the config file used, input file names, and optional checksums (Step 6.3) and filling time. apm, em, microstructure and ellips drop their own code.

### Step 3.8: Entry-name handling in the core
**Issue:** a skeleton `/ENTRY[entry]/` is left behind when readers use real entry names (§2.3, xas workaround), and `entry`/`entry1` are hard-coded (§5.3).
**How:**
- `transfer_data_into_template` passes the NXDL template to the reader, and MFR **re-keys** NXDL default entries for each name from `get_entry_names()` before filling. It drops any `ENTRY[entry]` skeleton key that no entry claims.
- `get_entry_names()` defaults to `[p.entry_name for p in parsed]` or `["entry"]`, and must return a `list`.
- `setup_template()` may use `/ENTRY/` in keys. MFR expands it per entry, the same way it does for config keys, which removes hard-coded `/ENTRY[entry]` from ellips, spm and raman.

### Step 3.9: Kwargs and warnings
- `BaseReader.read(..., **kwargs)` (Step 1.4 made permanent).
- Retire the `suppress_warning` kwarg. Missing config values are collected and reported **once** as a summary at INFO, plus at WARNING for keys marked required in the NXDL. Plugins no longer hard-code `True` (C10).
- `overwrite_keys` becomes an explicit kwarg with documented semantics. Remove the "multiple extensions" heuristic in xps.

### Step 3.10: Core housekeeping
- Cache `get_reader` results (`functools.lru_cache`) and use entry points first, then built-ins, without exception-driven control flow.
- Sort config keys **once** in `fill_from_config`, outside the entry loop (C7).
- Deprecate `.pickle` input in `JsonMapReader`, or gate it behind an explicit `--allow-pickle`.

---

## Phase 4: One config language

**Issue:** four mapping languages (§1.3). apm and em functor dicts and spm nested JSON exist because MFR config lacks unit conversion, dtype casting, defaults and vector assembly.

### Step 4.1: Extend the MFR config grammar minimally
Keep the flat JSON (with the nested-JSON flattening already supported by `flatten_json`) and the `@attrs`/`@data`/`@eln`/`@link` tokens. Add these features:

| Need (from) | Syntax proposal |
|---|---|
| Literal default when nothing is found (spm `@default:`) | already possible with the list form `["@attrs:x", "fallback"]`, once B1 is fixed. Document it and convert spm. |
| Unit conversion (em/apm `map_to_f8` + pint) | `{"value": "@attrs:AP_WD", "unit": "m", "source_unit": "@attrs:AP_WD@unit"}` converts with pint if both are known |
| dtype enforcement (em `map_to_f8`/`map_to_str`, spm `manually_filter_data_type`) | `"dtype": "float64" \| "str" \| "int64" \| "bool"` in the same object form |
| Vector from several sources (em stage position) | `"value": ["@attrs:X", "@attrs:Y", "@attrs:Z"], "combine": "stack"` |
| Constant (`use` functor) | a plain literal, already supported |
| Timestamps with time zone (em `timestamp_functor`) | `"dtype": "datetime"` with an optional `"timezone": "@eln:..."` |

Implement this as small, separately tested resolver functions in `multi/resolvers.py`, so that `fill_from_config` stays simple.

### Step 4.2: Config validation
- New CLI command: `dataconverter validate-config <config.json> --nxdl NXxyz [--reader xyz]`. It checks that every key resolves to an NXDL concept (`helpers` path conversion), that every token prefix is known (catches `@attr:`, see C12), that link targets exist in the config or NXDL, and that dtypes match the NXDL type.
- A pytest helper in `pynxtools.testing` lets every plugin validate **all shipped configs** in CI.

### Step 4.3: Converters for the legacy mapping formats
- Add a script that turns em/apm functor dicts (`prefix_trg`, `map_to_*`, `use`) into config JSON. These dicts are declarative, so the conversion is mechanical.
- Add a script that turns spm nested configs (`raw_path`, `@default:`, `@default_link:`) into MFR config JSON.

The generated configs are reviewed by hand and committed to each plugin's `config/` directory.

---

## Phase 5: Plugin migrations

The order goes from least to most effort. Each step ends with: a clean baseline comparison (Step 0.3), duplicated code removed, no `read()` override, and a plugin pin of `pynxtools>=<release with Phases 2-4>`.

### Step 5.1: pynxtools-xps (reference migration)
- Subclass the core `FileParser` and `ParsedData`. Delete the local `versioning.py`, the `_Parser` base, `handle_data_file`, `set_config_file`, `_search_metadata`, `get_eln_data` and `_collect_supported_extensions`. `VamasResultParser` becomes `role="metadata"`.
- Keep the domain logic: `_combine_datasets` as `post_process`, atom types as `eln_post_process`, and survey-first default plotting as a `default_nxdata_strategy` callable.
- **Why first:** the core framework is extracted from this code, so this migration validates that the abstraction fits.

### Step 5.2: pynxtools-xas
Same as xps. The numpy `ParsedSpectrum` becomes a `ParsedData` subclass, and `get_data` handlers are replaced by `@data:energy` paths. Delete the `read()` override, because Step 3.8 fixes the skeleton issue.

### Step 5.3: pynxtools-xrd
- Wrap `fairmat_readers_xrd.read_file` in one `FileParser` per format (`.xrdml`, `.rasx`, `.brml`), with real `matches_file` checks: the XML root tag for xrdml and brml, the zip member list for rasx.
- Move `_extract_experiment_config` and `_normalize_units` into `post_process` and config dtypes.
- Rename the config to `config/xrd_pan.json` and use `default_config`.
- In `fairmat_readers_xrd`, stop filling in units (`deg`, `kV`, `mA`, `angstrom`) and header values when the file has none (B34), and parse XML safely (B36).

### Step 5.4: pynxtools-raman
- Add `RodParser` and `WitecParser` to `parsers`. Delete the extension handlers, `set_config_file`, the `get_eln_data` heuristics (Step 3.3) and the `get_attr` float coercion (move it to config dtypes).
- `unused_attrs` → the core `unused_metadata_group = "unused_data"`.

### Step 5.5: pynxtools-ellips
- `WoollamParser` goes into the registry. Make `matches_file` identify the header, and **detect column layout from the header** where possible. Otherwise read it from declared parser options (Step 3.5), not from top-level ELN keys. This removes `processing_order` and `_CONFIG_KEYS`.
- Delete `handle_eln_file` (no more direct ELN-to-template injection), `set_config_file`, hard-coded `/ENTRY[entry]` keys and the software block (Step 3.7).

### Step 5.6: pynxtools-igor
- Add `IbwParser` and `PxpParser` as `FileParser`s that share one axis, unit and metadata helper (removes the duplicated blocks).
- `.entry` description files are explicit parser options or a `role="metadata"` parser.
- Delete the ELN and config overrides.

### Step 5.7: pynxtools-spm
1. Switch to MFR. Wrap each `SPMBase` parser (Nanonis SXM/DAT, Omicron SM4, Bruker SPM/TXT/FLT) as a `FileParser`, with **header-based** `detect_version` and `supported_vendor`. The vendor and version are then read from the file, not from the ELN. ELN `software/vendor` and `software/model` become metadata that the parser checks for consistency, with a warning on mismatch.
2. Choose the technique (STM, STS, AFM) from the requested NXDL (`supported_nxdls` on parser and config) together with the file content, and **cross-check** it against the ELN `experiment_technique`.
3. Convert the nested configs with Step 4.3 and replace `walk_though_config_nested_dict` with `fill_from_config`.
4. Move the formatter-specific derivations (scan region, pixel centres, bias sweep) into `post_process` of the parser, writing into `ParsedData`.
5. Delete `manually_filter_data_type` (replaced by config dtypes) and both template copies.

### Step 5.8: pynxtools-microstructure
- Switch to MFR with one parser: `MtexHdf5Parser` (`supported_file_extensions=(".mtex.h5",)`, detected from HDF5 root keys).
- Replace imports from pynxtools-em internals with the core default-plot strategy and a shared, *public* `nx_atom_types` helper (see Step 5.10).

### Step 5.9: pynxtools-apm
- Switch to MFR. Reconstruction formats (`.apt`, `.pos`, `.epos`, `.ato`, `.csv`, `.h5`, …) become `role="primary"` parsers. Ranging formats (`.rrng`, `.rng`, `.env`, `.fig.txt`, `range_.h5`) become `role="sidecar"` with `compatible_primary` set to the reconstruction parsers.
- **Classify `.h5` and `.hdf5` by content** (HDF5 root keys in the probe) instead of by name, which fixes B7 properly.
- The OASIS config and ELN yaml become ELN handling (Step 3.3) plus `parser_options`.
- Convert the functor configs with Step 4.3.
- Replace `ApmUseCaseSelector` with the registry: role, multiplicity and ambiguity checks come from the core.
- Checksums go through Step 6.3.

### Step 5.10: pynxtools-em (largest effort, can run in parallel with others after Phase 4)
1. **Adapter first:** wrap each existing parser class in a `FileParser` adapter. The adapter moves its `check_if_*` logic into `matches_file(probe)`, using probe TIFF tags, HDF5 keys and magic bytes. It keeps the existing `parse(template)` code as a handler that returns a dict. Run the ambiguity audit (Step 2.5) to confirm that exactly one parser claims each example file.
2. Sidecar formats (Hitachi `.txt`, JEOL and Tescan `.hdr`, MRC `.mrc.mdoc`) become `role="sidecar"` parsers.
3. Remove the `examples/` imports from `reader.py`. The custom ELNs (`deu_berlin_koch`, `ebsd_database`, `custom_reference_frame`) become optional parsers registered through the entry-point group from Step 2.5.
4. Then **progressively** move each parser's template-writing code to `ParsedData` plus config JSON (converted from `configurations/*_cfg.py` with Step 4.3), one vendor per PR.
5. **Shared helpers:** extract the apm/em/microstructure common code (`mapping_functors_pint` until it is retired, `pint_custom_unit_registry`, `nx_atom_types`, `hfive_base`, `get_checksum`, `string_conversions`) into **one** place:
   - either `pynxtools.dataconverter.readers.utils.*`, if generic;
   - or a small shared package `pynxtools-microscopy-common`.

   Delete the forked copies (§5.1).

### Step 5.11: pynxtools-mpes (smallest change, can go first)
mpes is already an MFR reader without a `read()` override (FINDINGS §4.11).
- Add one `FileParser` for the binned HDF5 (detected from its `binned`/`axes` groups) and keep the xarray object input.
- Ship the example config as `default_config`, delete the `set_config_file` override (its log message contradicts what it does), and initialise `eln_data` as a dict.
- Read the data lazily (Step 6.2) instead of loading the whole binned array, and leave units out instead of writing `""`.

---

## Phase 6: Resource optimisation

The baseline (FINDINGS §5.5) shows that none of these costs is visible with the shipped test files: every conversion runs in about 5 s or less and below 410 MB peak RSS, and roughly 100 MB of that is start-up. Each step below therefore has to be measured on large files.

### Step 6.1: Detection without loading data
- Velox: replace `emd.file_reader` in detection with an `h5py` check of `/Data` and `/Version` in the probe ([rsciio_velox.py:101](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/340f1545aded60ba7e91133892acba6c3d255f45/src/pynxtools_em/parsers/rsciio_velox.py#L101)).
- TIFF: one tag read in the probe, shared by all TIFF parsers.
- Target: peak RSS during detection stays below 2× the probe size, and each input file is opened at most twice (probe and parse). The baseline (Step 0.2) has no large-file inputs and no `open()` counts, so measuring this target needs one of the optional follow-ups from Phase 0.

### Step 6.2: Lazy data in the template
- Allow handlers and parsers to place `h5py.Dataset`, `dask.array` or a `LazyArray(callable)` in `ParsedData.data`, and teach the `Writer` to stream them chunk-wise. The writer already supports chunked writes ([chunk.py](https://github.com/FAIRmat-NFDI/pynxtools/blob/59f03be0d6422c29c0e72447ffa431624db3e5f5/src/pynxtools/dataconverter/chunk.py)).
- JsonMapReader: `hdfdict.load(lazy=True)` and read attributes in the same pass (one open).

### Step 6.3: Hashing once, optionally
Compute checksums at most once per input file (streamed, 1 MiB blocks) in the core provenance step (Step 3.7), controlled by `--checksums {none,sha256}`. The NOMAD default is `sha256`; the CLI default is `none`. Delete the per-parser `get_sha256_of_file_content` calls and the apm `report_workflow` hashing.

### Step 6.4: No template copies
- Remove the spm `deepcopy` and `filled_template`, and the xps `final_template` rebuild. Make `Template.remove_none_values()` plus `finalize()` operate in place.
- Check that peak RSS of a conversion is at most about 1.3× the size of the largest array, and that the baseline comparison (Step 0.3) shows no peak RAM regression.

### Step 6.5: Core micro-optimisations
`get_reader` caching (Step 3.10), sorting config keys once (C7), and hoisting the nested helpers and regex in `resolve_special_keys` to module level (today `try_convert` and `parse_config_value` are redefined on every call).

---

## Phase 7: Governance and keeping it unified

### Step 7.1: Plugin conformance test suite
Ship `pynxtools.testing.conformance` with a parametrised pytest suite that every plugin runs. It asserts:
- the reader subclasses `MultiFormatReader` and does not override `read`;
- every parser in `reader.parsers` declares `supported_file_extensions` and implements `matches_file`;
- no two parsers claim the same example file (ambiguity audit);
- every reference output is valid against its application definition (today 49 of 58 baseline outputs are not, FINDINGS §5.5);
- every shipped config passes `validate-config`;
- `read()` accepts arbitrary kwargs, honours `-c`, and handles upper-case extensions;
- no top-level module imports another plugin's private modules.

Run `preliminary_audit_scans/run_all.sh` in CI as a report (not gating), so new hard-coded units, rounding, swallowed errors and time-zone assumptions (FINDINGS §5.7, §5.8) show up in review.

### Step 7.2: Plugin template
Update the pynxtools plugin cookiecutter so new plugins start from the Phase 3 structure: `parsers/`, `config/`, a reader of about 30 lines, and the conformance test enabled.

### Step 7.3: Consistent packaging
- Use one minimum `pynxtools` pin across all plugins, set to the release that contains Phases 2-4 (§5.6).
- Use one licence header style (REUSE SPDX, as pynxtools does), one ruff and mypy configuration, and the shared `"pynxtools"` logger hierarchy (`pynxtools.<plugin>`). Replace `print` with the logger.

### Step 7.4: Documentation
- Write a "How to write a pynxtools reader" guide around `FileParser`, `ParsedData`, config tokens and `finalize`.
- Write a config language reference (Step 4.1) with examples taken from real plugins.
- Write a migration guide (from BaseReader, from nested or functor configs).

---

## Target shape of a plugin reader (after Phase 5)

```python
class XPSReader(MultiFormatReader):
    supported_nxdls = ["NXmpes", "NXxps"]
    parsers = [PHIParser, ScientaHDF5Parser, ScientaIgorParser, ScientaTXTParser,
               SPECSSLEParser, SPECSXMLParser, SPECSXYParser,
               VamasExportParser, VamasParser, VamasResultParser]   # role declared on class
    default_config = "pynxtools_xps:config/template.json"
    CONVERT_DICT = {...}                     # ELN vocabulary only
    unused_metadata_group = "unused_data"
    default_nxdata_strategy = survey_first   # callable

    def post_process(self) -> None:          # domain logic only
        self.parsed = combine_datasets(self.parsed)

    def eln_post_process(self, eln: dict) -> None:
        add_atom_types_from_formulae(eln)

READER = XPSReader
```

No extension handling, ELN or config plumbing, `/ENTRY[entry]` literals, `read()` override, or version code remains in the plugin.

---

## Suggested sequencing and effort (rough)

| Milestone | Steps | Rough effort |
|---|---|---|
| M1: bug fixes (safety net done) | 1.1–1.28 | 2–3 weeks (parallel per plugin) |
| M2: core framework | 2.1–2.5, 3.1–3.10 | 4–6 weeks |
| M3: config language | 4.1–4.3 | 2–3 weeks |
| M4: MFR-native plugins | 5.1–5.6, 5.11 | 3–4 weeks |
| M5: spm, microstructure, apm | 5.7–5.9 | 4–6 weeks |
| M6: em | 5.10 | 6–8 weeks, incremental per vendor |
| M7: optimisation + governance | 6.x, 7.x | 2–3 weeks, partly in parallel |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Output changes break NOMAD searches or apps | the pre-redesign baseline and `compare_baselines.py` (Phase 0); intentional changes listed per release |
| The core API does not fit em/apm (multi-file, sidecars, two-pass workflows) | xps metadata parsers already prove the sidecar model; em goes through adapters first (5.10.1) before rewriting |
| The config grammar grows into a programming language | only the six features in 4.1; anything more stays in `post_process` Python |
| Plugins pin old pynxtools for a long time | the compatibility shims (2.1, 2.3) keep the old local bases importable for one minor release with a `DeprecationWarning` |
| Strict "unsupported file" errors break existing NOMAD uploads that contain stray files | `strict=False` default in the NOMAD converter for one release, logging all rejection reasons |
