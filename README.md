# pynxtools-plugin-audit

An independent, code-level audit of the [pynxtools](https://github.com/FAIRmat-NFDI/pynxtools) plugin ecosystem, maintained in FAIRmat.

pynxtools converts experimental data into [NeXus](https://www.nexusformat.org/) files. The core package provides the conversion machinery, and each technique (XPS, SPM, electron microscopy, Raman, ...) has its own plugin, `pynxtools-<technique>`, whose reader and parsers turn vendor files into NeXus. For each of these readers/parsers, this repository documents what actually happens to the data between the raw input file and the NeXus output. Findings are based on evidence from the source code, tests and upstream documentation, and are compared against the NeXus application definitions.

The repository has four parts:

- **Overview** (`overview_table.ods`, repository root): one row per plugin with its technique, NeXus application definition, links and known issues.
- **Parser documentation** (`docs/`): one folder per plugin, with a plugin README, one document per parser and, for some plugins, a findings sheet.
- **Preliminary audit** (`preliminary_audit/`): a static scanner and its CSV results, used as a first automated pass over a plugin's code.
- **Unification** (`pynxtools-unification/`): a cross-plugin findings report, a plan to unify all readers around `MultiFormatReader`, and a reproducible **pre-redesign baseline** (converted NeXus files plus computing resources) to compare against after the redesign.

Each part is described below.

---

## Why this exists

pynxtools parsers do a lot of implicit work: building axes, applying offsets, converting units, reshaping arrays, falling back to defaults when metadata is missing. Much of this behaviour is not documented anywhere except the code itself. This repo collects it in one place so that users, developers and reviewers can:

- understand exactly how a given input format is transformed into NeXus,
- spot undocumented assumptions and special cases,
- identify behaviour that may be inconsistent with the NeXus definitions or the source format spec,
- track open questions and report them upstream,
- check that unifying the plugin architecture does not change the converted data or make it more expensive to produce.

---

## Scope

Plugins covered:

| Plugin | Status | Audit docs | Findings sheet | In baseline |
|---|---|---|---|---|
| `pynxtools` (core `MultiFormatReader`) | Completed | [`docs/MultiFormatReader/`](docs/MultiFormatReader/) | — | Yes |
| `pynxtools-apm` | Completed | [`docs/apm/`](docs/apm/) | — | No (excluded) |
| `pynxtools-ellips` | Completed | [`docs/ellips/`](docs/ellips/) | — | Yes |
| `pynxtools-em` | Completed | [`docs/em/`](docs/em/) | [`pynxtools-em.ods`](docs/em/pynxtools-em.ods) | Yes |
| `pynxtools-igor` | Completed | [`docs/igor/`](docs/igor/) | — | Yes |
| `pynxtools-microstructure` | Completed | [`docs/microstructure/`](docs/microstructure/) | — | Yes |
| `pynxtools-mpes` | Completed | [`docs/mpes/`](docs/mpes/) | — | Yes |
| `pynxtools-raman` | Completed | [`docs/raman/`](docs/raman/) | — | Yes |
| `pynxtools-spm` | Completed | [`docs/spm/`](docs/spm/) | [`pynxtools-spm.ods`](docs/spm/pynxtools-spm.ods) | Yes |
| `pynxtools-xas` | Completed | [`docs/xas/`](docs/xas/) | — | Yes |
| `pynxtools-xps` | Completed | [`docs/xps/`](docs/xps/) | [`pynxtools-xps.ods`](docs/xps/pynxtools-xps.ods) | Yes |
| `pynxtools-xrd` | Completed | [`docs/xrd/`](docs/xrd/) | — | Yes |

The per-plugin documents are based on static reading of the source; each plugin's `README.md` says which parts, if any, were confirmed by running the parser. A side-by-side comparison of the XPS, SPM and EM reader architectures is in [`docs/pynxtools_xps_spm_em_architectures.md`](docs/pynxtools_xps_spm_em_architectures.md).

---

## General `overview_table.ods`

This workbook gives a general overview of the goal of this repo, general documentation and basic information for each `pynxtools` plugin. The **About** sheet describes the task; the **pynxtools_plugins_general** sheet lists every plugin (click a plugin name to open its detail sheet) with these columns:

| Plugin | State | Field / technique | NeXus application definition(s) | GitHub | Docs | Reader code | Known issues | Remarks |
|---|---|---|---|---|---|---|---|---|

PDF exports are in [`overview_table.pdf`](overview_table.pdf) and [`overview_table_about.pdf`](overview_table_about.pdf).

---

## Plugin findings table

Inside `docs/`, the plugin findings sheet, for example [`docs/xps/pynxtools-xps.ods`](docs/xps/pynxtools-xps.ods) (PDF export: [`pynxtools-xps.pdf`](docs/xps/pynxtools-xps.pdf)), aggregates all findings across parsers for that specific plugin (in this case for `pynxtools-xps`) with these columns:

| Parser | Input format | Vendor site | GitHub | Docs | Metadata map | Standard behaviour | Special behaviour | Formula / transformation | Notes – issues to check |
|---|---|---|---|---|---|---|---|---|---|

Sheets exist so far for `pynxtools-xps`, `pynxtools-spm` and `pynxtools-em`.

---

## Repository structure

```
.
├── .gitignore                                                           # Ignores logs/ (local pytest logs, not in git)
├── README.md
├── CONTRIBUTING.md                                                      # How to add a finding and the expected evidence format
├── TEMPLATE.md                                                          # Per-parser documentation template
├── overview_table.ods                                                   # Master overview across all plugins (sheets: About, pynxtools_plugins_general)
├── overview_table.pdf                                                   # PDF export of the plugin overview sheet
├── overview_table_about.pdf                                             # PDF export of the About sheet (task description)
├── preliminary_audit/
│   ├── preliminary_audit_scripts/
│   │   └── audit_scan_xps.py                                            # Static scanner (audit_scan.py), as run on pynxtools-xps
│   └── preliminary_results/
│       └── audit_xps.csv                                                # Scanner findings for pynxtools-xps
├── pynxtools-unification/                                               # Cross-plugin review and unification strategy
│   ├── FINDINGS.md                                                      # Architecture review, per-plugin findings, bug list
│   ├── IMPLEMENTATION_PLAN.md                                           # Phased plan to unify all readers around MultiFormatReader
│   └── pynxtools_baseline_scripts/
│       ├── BASELINE_GUIDE.md                                            # Step-by-step guide to building and comparing a baseline
│       ├── SKIPPED_TESTS.md                                             # Which plugin tests are skipped upstream, and why
│       ├── baseline_commits_links.md                                    # Pinned commit of every package
│       ├── git_submodule_status_recursive_nomad_distro_dev_231026.log   # Raw source of the pinned commits
│       ├── run_baseline.sh                                              # Orchestrates the whole baseline run
│       ├── monitor_resources.py                                         # Per-process CPU / RAM / I/O monitoring during the run
│       ├── compare_baselines.py                                         # Compares two baselines (results, NeXus content, logs, resources)
│       ├── sanitize_baseline.py                                         # Makes a shareable copy of a baseline without personal names/paths
│       ├── extra_conversions.tsv                                        # Conversions added on top of the plugins' own tests
│       ├── test_data/
│       │   ├── DATA_SOURCES.md                                          # Origin, license and citation of the extra test data
│       │   ├── em/                                                      # InGaN nanowire EDS .edaxh5 files (Zenodo 11208725)
│       │   └── microstructure/                                          # Example *.crc.mtex.h5 file
│       └── baseline_results/                                            # One folder per run (see "Baseline" below)
│           ├── baseline_20261026_155259/
│           ├── baseline_20261026_160705/
│           └── baseline_20261026_161939/
│               ├── run.log, summary_tests.csv, summary_conversions.csv, MANIFEST.sha256
│               ├── 00_environment/  00_monitor/  _tools/
│               └── pynxtools/  pynxtools-ellips/  pynxtools-em/  ...  pynxtools-xrd/
│                   ├── pytest/
│                   └── conversions/
└── docs/
    ├── pynxtools_xps_spm_em_architectures.md                            # Architecture comparison: XPS, SPM, EM
    ├── MultiFormatReader/                                               # Core pynxtools MultiFormatReader
    │   ├── multi_format_reader.md
    │   └── multi_reader_description.md                                  # Line-by-line walkthrough of multi/reader.py
    ├── apm/
    │   ├── README.md                                                    # Plugin overview (same in every plugin folder)
    │   ├── apm_oasis_config.md
    │   ├── apm_oasis_eln.md
    │   ├── ifes_ranging.md
    │   └── ifes_reconstruction.md
    ├── ellips/
    │   ├── README.md
    │   └── ellips_plugin_woollam_parser.md
    ├── em/
    │   ├── README.md
    │   ├── pynxtools-em.ods, pynxtools-em.pdf                           # Plugin findings sheet + PDF export
    │   ├── hdf5_vendor_parsers.md
    │   ├── image_parsers.md
    │   ├── nxs_nion.md
    │   ├── oasis_eln_config_parsers.md
    │   └── rsciio_parsers.md
    ├── igor/
    │   ├── README.md
    │   └── igor-reader.md
    ├── microstructure/
    │   ├── README.md
    │   ├── nxs_mtex.md
    │   └── oasis_config.md
    ├── mpes/
    │   ├── README.md
    │   └── mpes-reader.md
    ├── raman/
    │   ├── README.md
    │   ├── rod.md
    │   └── witec.md
    ├── spm/
    │   ├── README.md
    │   ├── pynxtools-spm.ods, pynxtools-spm.pdf
    │   ├── bruker_flt.md
    │   ├── bruker_spm.md
    │   ├── bruker_txt.md
    │   ├── nanonis_dat.md
    │   ├── nanonis_sxm.md
    │   └── omicron_sm4.md
    ├── xas/
    │   ├── README.md
    │   ├── esrf_fluo.md
    │   ├── esrf_trans.md
    │   ├── myspot_trans.md
    │   ├── oscars_xdi.md
    │   └── specs_xy.md
    ├── xps/
    │   ├── README.md
    │   ├── pynxtools-xps.ods, pynxtools-xps.pdf
    │   ├── kratos.md
    │   ├── phi.md
    │   ├── scienta.md
    │   ├── specs_sle.md
    │   ├── specs_xml.md
    │   ├── specs_xy.md
    │   └── vms.md
    └── xrd/
        ├── README.md
        ├── bruker_raw_parser.md
        └── ikz.md
```

---

## Document template

Every parser has its own Markdown document in `docs/<plugin>/`, and every plugin folder has a `README.md` that lists its parsers and summarises the plugin. The parser documents record four kinds of findings:

| Category | Description |
|---|---|
| **Standard behaviour** | How the parser maps its input format to NeXus fields. |
| **Formulas / transformations** | Energy-axis construction, offsets, scaling, reshaping/transposing, unit conversions and any other math applied to the data, with file and line references. |
| **Special behaviour** | Format-specific quirks, fallbacks and implicit assumptions (e.g. index fallbacks when an axis is missing). |
| **Behaviour to investigate** | Unclear, undocumented or possibly inconsistent logic, flagged for verification or an upstream issue. |

So that documents can be compared across plugins, they all follow the same section order, defined in [`TEMPLATE.md`](TEMPLATE.md):

1. **Source files reviewed**: file paths, inherited code that was not read, and the branch/commit audited (line numbers refer to that commit)
2. **At a glance**: input format, parser class, reader, raw-data storage, output, config and target NeXus definition
3. **Formula / transformation**: each calculation, with code references
4. **Standard behaviour**
5. **Special behaviour**
6. **Behaviour to investigate**: each item with a status, `open` / `confirmed` / `refuted` / `reported upstream`
7. **Scanner findings**: results of the preliminary audit for this parser (or "No scanner run was performed")

For a plugin that is one reader with no separate parsers, see [`docs/mpes/mpes-reader.md`](docs/mpes/mpes-reader.md).

---

## Preliminary audit

Before a plugin's parsers are documented by hand, its code gets a first automated pass: a static scanner flags places where data may be changed, defaulted or hard-coded without notice. The resulting list tells the reviewer where to look first, and each relevant hit is then checked manually and, if it holds, written up in the parser document (section 7, *Scanner findings*). The scanner script is in [`preliminary_audit/preliminary_audit_scripts/`](preliminary_audit/preliminary_audit_scripts/) and its CSV results are in [`preliminary_audit/preliminary_results/`](preliminary_audit/preliminary_results/).

### The `audit_scan.py` scanner

`audit_scan.py` is a rule-based static analysis tool for Python packages, with a focus on pynxtools plugins and their data-processing and configuration logic. It uses Python's Abstract Syntax Tree (AST) and tokenization to inspect Python source files, and dedicated parsers and pattern-based checks to analyse JSON and YAML configuration files.

Its rule set covers unit-string validation and canonicalization, hard-coded physical constants and numeric values, default parameters and silent fallbacks, data transformations and reductions, array reversals and truncation, exception handling, datetime and timezone operations, duplicate dictionary and JSON keys, inconsistent key naming, duplicated or divergent function implementations, hard-coded configuration values, syntax and parsing errors, and TODO/FIXME markers.

Findings are collected with rule identifiers, severity levels, file paths, line numbers, qualified function or class names where applicable, diagnostic messages, and source snippets, then written to a CSV report for manual inspection. The command-line interface supports configurable severity filtering, selective rule suppression, optional scanning of tests and NOMAD example directories, and integration with an existing CSV inventory to aggregate findings by code unit.

The scanner is intended as a review aid for identifying potentially error-prone or inconsistent implementation patterns; its findings are heuristic indicators rather than definitive evidence of defects.

The version in this repository is [`preliminary_audit/preliminary_audit_scripts/audit_scan_xps.py`](preliminary_audit/preliminary_audit_scripts/audit_scan_xps.py). Run it from the plugin root (next to `pyproject.toml`):

```bash
python audit_scan_xps.py --min-severity low
```

Its results are in [`preliminary_audit/preliminary_results/`](preliminary_audit/preliminary_results/) in `.csv` format (currently `audit_xps.csv` for `pynxtools-xps`).

---

## Unification and baseline

The [`pynxtools-unification/`](pynxtools-unification/) folder prepares the move of every plugin reader onto a common `MultiFormatReader` architecture:

- [`FINDINGS.md`](pynxtools-unification/FINDINGS.md): architecture review of the core (`BaseReader`, `MultiFormatReader`), an overview matrix, per-plugin findings, cross-cutting issues (duplicated code, file-format checking, hard-coding, ELN handling, resource usage, packaging) and a bug list by severity.
- [`IMPLEMENTATION_PLAN.md`](pynxtools-unification/IMPLEMENTATION_PLAN.md): a phased plan (safety net, quick bug fixes, core parser framework, `MultiFormatReader` v2, one config language, plugin migrations). Phase 0 is the baseline below.

### Baseline

[`pynxtools_baseline_scripts/`](pynxtools-unification/pynxtools_baseline_scripts/) freezes what pynxtools and its plugins produce **before** the redesign (converted NeXus files, all terminal output, test results) and what it costs (wall time, CPU time, peak RAM), so the same procedure can be rerun afterwards and compared 1:1. Everything is described in [`BASELINE_GUIDE.md`](pynxtools-unification/pynxtools_baseline_scripts/BASELINE_GUIDE.md).

- **Setup.** The scripts run from the root of a `nomad-distro-dev` checkout, where pynxtools and the plugins live under `packages/`. The pinned commits are in [`baseline_commits_links.md`](pynxtools-unification/pynxtools_baseline_scripts/baseline_commits_links.md).
- **Scope.** Every `packages/pynxtools*` folder except `pynxtools-apm`, which is excluded: pynxtools, ellips, em, igor, microstructure, mpes, raman, spm, xas, xps, xrd.
- **What a run does.** `run_baseline.sh` runs each package's pytest suite while recording every `convert()` call, replays each conversion in a fresh process to measure time and RAM, then validates and reads back every output. `monitor_resources.py` logs CPU, RAM, threads and disk I/O for every process alongside.
- **Extra conversions.** The em and microstructure conversion tests are skipped upstream (see [`SKIPPED_TESTS.md`](pynxtools-unification/pynxtools_baseline_scripts/SKIPPED_TESTS.md)), so [`extra_conversions.tsv`](pynxtools-unification/pynxtools_baseline_scripts/extra_conversions.tsv) adds em's `tests/data/default` example, three InGaN EDS files and a microstructure `*.mtex.h5` example. Their sources and licenses are in [`test_data/DATA_SOURCES.md`](pynxtools-unification/pynxtools_baseline_scripts/test_data/DATA_SOURCES.md).
- **Results.** Each run writes `baseline_results/baseline_<timestamp>/` with `summary_tests.csv`, `summary_conversions.csv`, `run.log`, `MANIFEST.sha256`, `00_environment/` (system, packages, git state), `00_monitor/` (resource time series and summaries), `_tools/` (the exact scripts used) and one `pynxtools-<plugin>/` folder with `pytest/` and `conversions/`. Every file name carries its package and case, e.g. `pynxtools-xps-vms_regular_output.nxs`, so no two files share a name.
- **Current runs.** Three runs from 2026-10-26 are committed (`baseline_20261026_155259`, `_160705`, `_161939`), each with 65 recorded conversions: 61 `OK` and 4 `CONVERT_FAILED`, all four from pynxtools core tests that call `convert()` with invalid inputs.
- **After the redesign.** Run the same scripts on the same machine, then compare with `compare_baselines.py <before> <after> --out <report>`. It reports test outcome changes, conversion status changes, NeXus content differences (h5py, with float tolerances and volatile items ignored), new or removed warnings, and resource regressions; its exit code is `1` when functional regressions are found.
- **Sharing.** `sanitize_baseline.py` makes a public copy of a baseline with personal names, logins and home paths removed, including inside HDF5 files, and verifies that none are left.

---

## Contributing

Contributions are welcome: corrections, additional evidence, new parsers, or confirmation/refutation of items marked *behaviour to investigate*. Please see [`CONTRIBUTING.md`](CONTRIBUTING.md). In short:

- Reference the exact plugin version or commit you inspected.
- Link to the specific file and line(s) in the upstream repository.
- Distinguish clearly between what the code **does** and what you **infer** it intends.
- Where possible, back claims with a test, a minimal example file, or a reproducible command.

---

## Reporting upstream

When a finding appears to be a bug or a documentation gap, open an issue in the relevant upstream repository and link it from the corresponding entry here, updating its status to `reported upstream`.

---

## Contact person in FAIRmat for this audit repository

Keila Moral Figueroa
