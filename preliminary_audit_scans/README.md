# audit_scan: static audit for pynxtools and its plugins

`audit_scan.py` reads the source of a pynxtools repo (Python, JSON and YAML
configs) and lists places worth a manual look: unit problems, hard-coded
values, silent fallbacks, data-changing operations, swallowed errors,
copy-pasted code and unsafe handling of uploaded files. A finding is a pointer
for review, not a proven bug. The scan is read-only: it never changes the
repos and sends nothing anywhere. Everything it writes goes to files you name.

## Where it lives

The folder sits **next to** `packages/`, never inside it. uv treats every
folder under `packages/` as a workspace member, so putting this folder there
breaks every `uv` command in the distro.

```
nomad-distro-dev/
├── .venv/                      distro environment (has pint)
├── packages/                   pynxtools, pynxtools-xps, ... (the repos scanned)
└── audit_scans/                this folder
    ├── audit_scan.py           the scanner
    ├── run_all.sh              scans all 12 repos in one go
    ├── profiles/               one .toml per repo + _base.toml
    ├── tests/                  regression test + fixture repo with planted bugs
    ├── results/                created by the runs: your CSVs
    └── README.md
```

To keep `git status` in nomad-distro-dev clean (local only, not committed):

```bash
echo "audit_scans/" >> ~/nomad-distro-dev/.git/info/exclude
```

## Run

All repos (writes `audit_scans/results/<repo>.csv`):

```bash
bash ~/nomad-distro-dev/audit_scans/run_all.sh
bash ~/nomad-distro-dev/audit_scans/run_all.sh --min-severity medium   # extra options are passed on
```

One repo, from inside `audit_scans/`:

```bash
cd ~/nomad-distro-dev/audit_scans
../.venv/bin/python audit_scan.py ../packages/pynxtools-xps --out results/pynxtools-xps.csv
```

Use the distro's `../.venv/bin/python` directly rather than `uv run`. It has
pint and doesn't depend on how uv resolves the workspace. Plain `python3` works
too if pint is installed. Python 3.11 or newer is needed, or 3.10 with
`pip install tomli`.

### Options

| option | effect |
|---|---|
| `--out FILE` | CSV path (default `audit_findings.csv` in the current folder) |
| `--min-severity info\|low\|medium\|high` | drop findings below this level |
| `--disable D05,A03` | skip rules, on top of what the profile disables |
| `--profile NAME` | force a profile instead of auto-detecting it |
| `--include-tests` | also scan the repo's `tests/` |
| `--inventory FILE.csv` | annotate a ledger; writes `FILE_with_findings.csv` next to it |
| `--unit-registry FILE` | pint definitions file to use for units |
| `--no-pint` | use the built-in unit table only |
| `--list-rules`, `--list-profiles` | print and exit |

`--distro FOLDER --out-dir DIR` scans every repo in a folder. Don't point it
at `packages/`: that also scans nomad and other non-pynxtools plugins with
only the base profile. `run_all.sh` is the safe way to scan everything.

### Checking a run

Each repo prints a header like:

```
== pynxtools-em  (profile: pynxtools-em; units: pint: .../packages/pynxtools/src/pynxtools/units/default_en.txt)
```

- `profile:` should name the repo. `_base` means no profile matched.
- `units:` should point at pynxtools' `default_en.txt`, so units are judged
  exactly as the dataconverter judges them. `built-in unit table` means pint
  wasn't found, and rules U08 to U10 are skipped.

## Results

Each CSV has one row per finding, sorted by severity:

`plugin, rule, severity, category, file, line, qualname, message, snippet, reviewed, notes`

`file` and `line` are relative to the repo root. `reviewed` and `notes` are
empty columns for your triage. A new run overwrites the CSV, so copy it or
rename it first if you've started annotating.

`python audit_scan.py --list-rules` prints every rule ID. In short: U = units,
N = numbers, A = data-changing operations, D = defaults and fallbacks,
E = error handling, T = time, K = consistency, C = config files,
S = security, M = misc.

## The other files

### `profiles/*.toml`: what is normal for each repo

The rules are the same for every repo. A profile tells the scanner what is
*normal* for one plugin, so that normal things aren't reported as suspicious.

- **`_base.toml`** applies to every repo. It sets which files are scanned
  (`src/`, minus NOMAD example uploads, apps and NORTH tools), which config
  values count as lookups (`@attrs:`, `@data:`, `@eln`, ...), the field-name to
  unit-dimension table used by U10 (`wavelength` must be a length, `temperature`
  a temperature, ...), and default duplicate-function exceptions.
- **`<repo>.toml`** is merged on top of the base. Its `[plugin] match` lists the
  `pyproject.toml` names it applies to, which is how the profile is
  auto-detected. Merging: tables combine, lists extend, single values override.

Sections you can edit:

| section | what it controls | example |
|---|---|---|
| `[scan]` | `include` / `exclude` / `force_include` globs | skip `examples/**` in em; scan the example `config_file.json` in mpes |
| `[rules]` | `disable = [...]` rules | C01 off where NeXus paths in Python are the design (em, core) |
| `[rules.severity]` | regrade a rule | `D05 = "info"` for vendor keyword switches |
| `[config]` | how config values are read | spm: values starting with `/` and `raw_path` keys are lookups |
| `[units]` | `expect`, `define`, `accept`, `accept_patterns` | raman: `raman_shift` must be 1/length |
| `[units.ambiguous]`, `[units.traps]` | extra suspicious unit strings | xps: VAMAS `d`, SPECS `nU` |
| `[numbers.constants]` | known constants reported by name | xrd: Cu Kα 1.5406 Å |
| `[duplicates]` | functions whose copies are an interface | xps: `_parse`, `matches_file` |
| `[functors]` | em-style `map_to_f8` checks | on for em and microstructure |

When a rule is noisy for one plugin, change its profile, not the script.

### `run_all.sh`

Runs `audit_scan.py` once per repo with the distro's Python, writing to
`results/`. It finds its own location, so you can call it from anywhere.
Repos missing from `packages/` are skipped. Edit `REPOS` to change the list.

### `tests/`

- **`fixture_repo/`** is a fake plugin with one deliberate bug per rule
  family, marked with comments (`# S02`, `# U09 + U10`, ...).
- **`test_audit_scan.py`** scans the fixture and fails if any planted bug is no
  longer reported. Run it after editing the script or `_base.toml`:

```bash
../.venv/bin/python tests/test_audit_scan.py      # or: pytest tests/
```

The fixture is never scanned as part of your audit.
