# pynxtools-plugin-audit

An independent, code-level audit of the [pynxtools](https://github.com/FAIRmat-NFDI/pynxtools) plugin ecosystem.

For each plugin's readers/parsers, this repository documents what actually happens to the data between the raw input file and the NeXus output. Findings are based on evidence from the source code, tests and upstream documentation, and are compared against the NeXus application definitions.

---

## Why this exists

pynxtools parsers do a lot of implicit work: building axes, applying offsets, converting units, reshaping arrays, falling back to defaults when metadata is missing. Much of this behaviour is not documented anywhere except the code itself. This repo collects it in one place so that users, developers and reviewers can:

- understand exactly how a given input format is transformed into NeXus,
- spot undocumented assumptions and special cases,
- identify behaviour that may be inconsistent with the NeXus definitions or the source format spec,
- track open questions and report them upstream.

---

## What you'll find here

| Category | Description |
|---|---|
| **Standard behaviour** | How each parser maps its input format to NeXus fields. |
| **Formulas / transformations** | Energy-axis construction, offsets, scaling, reshaping/transposing, unit conversions and any other math applied to the data, with file and line references. |
| **Special behaviour** | Format-specific quirks, fallbacks and implicit assumptions (e.g. index fallbacks when an axis is missing). |
| **Behaviour to investigate** | Unclear, undocumented or possibly inconsistent logic, flagged for verification or an upstream issue. |
| **Units** | Which units are assumed, read from the file, or converted, and where. |

---

## Scope

Plugins covered or planned:

| Plugin | Status |
|---|---|
| `pynxtools-xps` | In progress |
| `pynxtools-apm` | Planned |
| `pynxtools-camels` | Planned |
| `pynxtools-ellips` | Planned |
| `pynxtools-em` | Planned |
| `pynxtools-em-insitu` | Planned |
| `pynxtools-focus` | Planned |
| `pynxtools-igor` | Planned |
| `pynxtools-mpes` | Planned |
| `pynxtools-microstructure` | Planned |
| `pynxtools-raman` | Planned |
| `pynxtools-spm` | Planned |
| `pynxtools-stm` | Planned |
| `pynxtools-xrd` | Planned |

The audit starts with `pynxtools-xps`, covering these parsers:

- Scienta Omicron
- SPECS
- PHI Electronics
- VAMAS (ISO)
- Kratos

---

## Repository structure

```
.
├── README.md
├── CONTRIBUTING.md        # How to add a finding and the expected evidence format
├── TEMPLATE.md            # Per-parser documentation template
├── overview-table.csv      # Master overview across all plugins
├── audit_scan.py          #
├── results/               # Results from audit_scan.py in .csv format for each pynxtools plugin
│   ├── audit_xps.csv
│   ├── audit_mpes.csv
│   └── ...
└── docs/
    ├── xps/
    │   ├── README.md      # Plugin overview
    │   ├── xps.md         # Plugin table overview
    │   ├── scienta-omicron.md
    │   ├── specs.md
    │   ├── phi.md
    │   ├── vamas.md
    │   └── kratos.md
    ├── mpes/
    └── ...
```

---

## Document template

Each parser document follows the same structure (see [`TEMPLATE.md`](TEMPLATE.md)):

1. **Input format**: description and link to the upstream spec
2. **Code locations**: repository, file paths, version/commit audited
3. **Standard behaviour**
4. **Special behaviour**
5. **Formulas / transformations**: with code references
6. **Units**
7. **Behaviour to investigate**: status: `open` / `confirmed` / `reported upstream`
8. **Evidence**: code snippets, tests, docs

---

## `audit_scan.py` 

A rule-based static analysis tool for Python packages, with a focus on pynxtools plugins and their data-processing and configuration logic. It uses Python's Abstract Syntax Tree (AST) and tokenization to inspect Python source files, and dedicated parsers and pattern-based checks to analyse JSON and YAML configuration files.

Its rule set covers unit-string validation and canonicalization, hard-coded physical constants and numeric values, default parameters and silent fallbacks, data transformations and reductions, array reversals and truncation, exception handling, datetime and timezone operations, duplicate dictionary and JSON keys, inconsistent key naming, duplicated or divergent function implementations, hard-coded configuration values, syntax and parsing errors, and TODO/FIXME markers. 

Findings are collected with rule identifiers, severity levels, file paths, line numbers, qualified function or class names where applicable, diagnostic messages, and source snippets, then written to a CSV report for manual inspection. The command-line interface supports configurable severity filtering, selective rule suppression, optional scanning of tests and NOMAD example directories, and integration with an existing CSV inventory to aggregate findings by code unit.

The scanner is intended as a review aid for identifying potentially error-prone or inconsistent implementation patterns; its findings are heuristic indicators rather than definitive evidence of defects.

The results from this file are found in the `results/` folder in `.csv` format.

---

## General `overview-table.csv`

This table gives a general overview of the goal of this repo, general documentation and basic information for each `pynxtools` plugin with these columns:

| Plugin | State | Field | (Relevant) NeXus Application Definition | (GitHub) URL | Documentation | Reader | Known Issues |
|---|---|---|---|---|---|---|---|


---

## Plugin findings table

Inside docs, the general plugin findings table, for example, [`docs/xps/xps.csv`](docs/xps/xps.csv),  aggregates all findings across parsers for that specific plugin (in this case for `pynxtools-xps`) with these columns:

| Parser | Input format | URL | Documentation | Standard behaviour | Special behaviour | Formula / transformation | Metadata maps| Notes |
|---|---|---|---|---|---|---|---|---|

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

## License

TBD (e.g. CC BY 4.0 for documentation).
