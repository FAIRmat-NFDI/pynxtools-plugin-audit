# pynxtools pre-redesign baseline: step-by-step guide

Goal: a frozen, reproducible record of what pynxtools and every plugin in
`nomad-distro/packages/` produce **today** (converted NeXus files, all terminal
output, test results) and what it costs (wall time, CPU time, peak RAM), so the
same procedure can be rerun after the architecture unification and compared
1:1.

Three files belong together. Keep them in the same folder:

| File | What it does |
|---|---|
| `run_baseline.sh` | Runs everything and writes `baseline_results/baseline_<timestamp>/` next to itself (steps 4 to 6). |
| `monitor_resources.py` | Runs alongside `run_baseline.sh` automatically and logs CPU, RAM, threads and disk I/O for **every process**, tagged with the plugin, step and conversion it belongs to. It can also wrap any other command. |
| `compare_baselines.py` | Compares two baseline folders after the redesign: results, NeXus file contents, log messages and resources. |

---

## What exists today (checked on 2026-10-22)

pynxtools' `convert` extra lists 10 FAIRmat plugins: **apm, ellips, em, igor,
mpes, raman, spm, xas, xps, xrd** (`pynxtools-<name>`). The script does not use
a fixed list. It runs every `packages/pynxtools*` folder in your distro, so
whatever is checked out there is what gets baselined.

**Scope of this baseline (2026-10-23):** every `packages/pynxtools*` folder
**except pynxtools-apm**, which was deliberately excluded (see step 5). The
pinned commits are listed in `baseline_commits.md`.

The `convert` extra list leaves out some plugins. **pynxtools-microstructure** (reader
`microstructure`, which depends on pynxtools-em) is one of them. It is not in
the `convert` extra or in the pynxtools plugin docs, but the script still picks
it up through the `packages/pynxtools*` pattern. To check what your run will
cover, compare `ls packages/` with `00_environment/readers.txt` after a dry run.

How each plugin tests conversions:

- Most plugins (ellips, igor, mpes, raman, spm, xas, xps, xrd) have
  `tests/test_reader.py`, which converts the files in `tests/data/<case>/`
  through `pynxtools.testing.nexus_conversion.ReaderTest`. That calls
  `pynxtools.dataconverter.convert.convert()`, validates the output and compares
  it against a reference `.nxs`.
- **em and apm currently mark their conversion test as skipped**, so their
  test suites convert nothing. The script converts their `tests/data/default/`
  example explicitly (see "extra conversions" below).
- **pynxtools-microstructure also skips its conversion test** ("No example
  yet"), and it ships no test data, only notebooks in `examples/oasisb/`. Its
  test suite still runs, but it produces **no converted file** unless you add
  an example dataset to the extra-conversions TSV.
- pynxtools itself has its own test suite (`tests/`), which includes conversions
  with the built-in `example`, `json_map` and `multi` readers.

---

## Step 1: Freeze the code you are baselining

Run everything from the nomad-distro checkout (`~/nomad-distro-dev`).

**1a. Look before you change anything.**

```bash
cd ~/nomad-distro-dev
git status
git submodule status --recursive 2>&1 | tee git_submodule_status_recursive_$(date +%d%m%y).log
```

How to read a line such as
` 59f03be0d64… packages/pynxtools (v0.16.0-18-g59f03be0)`:

| Part | Meaning |
|---|---|
| first character | ` ` (space): on the commit the parent repo records. `+`: on a different commit. `-`: not initialised (empty folder). `U`: merge conflict. |
| hash | the exact commit that is checked out. This is what identifies the code. |
| `(v0.16.0-18-g59f03be0)` | `git describe`: the nearest tag is `v0.16.0`, the commit is **18 commits after it**, and it is `g` + the short hash. So this is **not** the release v0.16.0. |

To see a commit on GitHub, open
`https://github.com/FAIRmat-NFDI/<repo>/commit/<full hash>`. nomad-FAIR is on
GitLab instead:
`https://gitlab.mpcdf.mpg.de/nomad-lab/nomad-FAIR/-/commit/<hash>`. The links
for this baseline are collected in `baseline_commits.md`. A 404 means the
commit was never pushed (it is local only or on a fork). Push it or tag it
somewhere permanent first, because otherwise nobody can reproduce the
baseline.

**1b. Initialise only what is missing, at the right level.**

- Only `-` lines need action. Run the update **inside the package that owns
  the submodule**, so nothing else is touched. For example, mtex in
  microstructure:

  ```bash
  (cd packages/pynxtools-microstructure && git submodule update --init --recursive)
  ```

  This clones the submodule and checks out the commit its parent records. Your
  files, branches and other submodules stay as they are.
- `git submodule update --init --recursive` **at the distro root** also resets
  every `+` submodule to the distro's recorded commit (as a detached HEAD).
  When all lines start with a space, it does nothing. Otherwise, only use it if
  you really want to go back to what the distro pins.
- Run `git submodule status --recursive` again afterwards. Every line should
  start with a space. The script records it again in
  `00_environment/git_submodules.txt`.

Not everything in `packages/` is a submodule. A folder that is a plain clone
(as `pynxtools-apm` is here) doesn't appear in `submodule status`. The script
still records its commit in `git_state.tsv`, because it walks every
`packages/*` folder.

**1c. Tag the state (optional, local only).**

```bash
git tag baseline-pre-redesign                                   # the distro repo itself
git submodule foreach --recursive 'git tag baseline-pre-redesign'   # every submodule
```

A tag is just a name for the current commit, so you can come back later with
`git checkout baseline-pre-redesign`. Tags stay on your machine unless you
`git push origin <tag>`, and pushing to the shared FAIRmat repos should be
agreed with the team first. `git tag -d baseline-pre-redesign` removes a tag.
The commit hashes recorded by the script are enough to reproduce the baseline
on their own. The tags are a convenience.

If a package has uncommitted edits, either commit them or accept them
knowingly. The script saves a diff of each one to
`00_environment/uncommitted_changes/`.

## Step 2: Build and check the environment

### 2a. Sync once, with all extras

```bash
uv sync --all-packages --all-extras
```

`--all-packages` installs every workspace member in `packages/`, and
`--all-extras` adds their `[dev]` extras, which contain `pytest` and friends. A
test that fails only because a dev dependency is missing is noise, not a
baseline result.

### 2b. Known issue: nomad-utility-workflows breaks NOMAD imports (fixed in `pyproject.toml`)

Every PyPI release of `nomad-utility-workflows` (≤ 0.3.2) declares five
`nomad.plugin` entry points for modules that do not exist. NOMAD loads all
plugin entry points when `nomad.datamodel` is imported, so the import crashes.
This has two effects:

- pynxtools' `tests/nomad/test_metainfo_schema.py` fails to collect, and pytest
  then aborts the **whole** pynxtools suite. The script now passes
  `--continue-on-collection-errors`, but the NOMAD tests are still lost.
- The plugins' `ReaderTest` imports `nomad.client` inside
  `try/except ImportError` and **silently skips the NOMAD parsing step**. The
  baseline would then be missing exactly the pynxtools ↔ NOMAD integration.

The developer removed the entry points on `main` (PR #57, commit `bb975517`),
but that fix isn't released yet. For this baseline, `pyproject.toml` in the
distro was modified to install that commit. Add this line under
`[tool.uv.sources]`:

```toml
nomad-utility-workflows = { git = "https://github.com/FAIRmat-NFDI/nomad-utility-workflows", rev = "bb975517385568fab1a359539411ad4f341a66d0" }
```

Then run `uv sync --all-packages --all-extras` again.

This edit changes the distro's state, and the baseline records it in
`00_environment/distro_pyproject.toml`, `distro_uv.lock` and
`uncommitted_changes/nomad-distro.diff`. To keep it reproducible, commit it
(for example on a local branch `baseline-pre-redesign`), and **use the same
pin for the post-redesign run** unless a fixed release exists by then.

To find a broken plugin like this one, run:

```bash
.venv/bin/python - <<'EOF'
import importlib.metadata as md
for ep in md.entry_points(group="nomad.plugin"):
    try:
        ep.load()
    except Exception as e:
        print("FAIL", ep.name, "=", ep.value, f"[{ep.dist.name if ep.dist else '?'}]", type(e).__name__, e)
print("done")
EOF
```

When the environment is right, it prints only `done`.

### 2c. Don't use `uv run` from here on

`uv run <cmd>` **syncs the virtual environment before running** the command,
so it can install, upgrade or remove packages according to the current
`pyproject.toml` and `uv.lock`. One `uv run` between your checks and the
baseline run can change the environment you just checked. Call the venv's
programs directly instead:

| Instead of | Use |
|---|---|
| `uv run python …` | `.venv/bin/python …` |
| `uv run dataconverter get-readers` | `.venv/bin/dataconverter get-readers` |
| `uv run pytest` | `.venv/bin/python -m pytest` |

`run_baseline.sh` itself only uses `.venv/bin/python`, so it never changes
the environment. (If you really need `uv run`, `uv run --no-sync` skips the
sync.)

### 2d. Checks before the run

Run them in this order, and don't run any `uv sync` or `uv run` between them
and the run itself.

```bash
# 1. NOMAD imports cleanly (see 2b)
.venv/bin/python -c "from nomad.client import parse; import nomad.datamodel; print('NOMAD OK')"

# 2. every package is imported from packages/ (editable), not from a PyPI wheel
.venv/bin/python -c "
import importlib
for m in ['pynxtools','pynxtools_ellips','pynxtools_em','pynxtools_igor','pynxtools_microstructure','pynxtools_mpes','pynxtools_raman','pynxtools_spm','pynxtools_xas','pynxtools_xps','pynxtools_xrd','fairmat_readers_xrd']:
    try: print(m, importlib.import_module(m).__file__)
    except Exception as e: print(m, 'ERROR', e)"

# 3. every test suite can be collected
for p in packages/pynxtools*/; do echo "== $p"; (cd "$p" && ../../.venv/bin/python -m pytest --collect-only -q 2>&1 | tail -2); done

# 4. optional: readers visible to the dataconverter
.venv/bin/dataconverter get-readers
```

What to expect from each check:

1. Prints `NOMAD OK`.
2. Every path is under `~/nomad-distro-dev/packages/`. If a package comes from
   PyPI instead, add it under `[tool.uv.sources]` as `{ workspace = true }`
   (or `uv add packages/<name>`) and sync again.
3. Every suite ends with `N tests collected`, with no `error`. If one doesn't,
   `pytest --collect-only -q 2>&1 | grep -A40 "ERROR collecting"` inside that
   package shows the cause.

About a check based on `importlib.metadata` instead of `__file__`: with
editable installs, every package shows up **twice**. Once from `.venv`, with
the editable link, and once from a leftover `*.egg-info` in its source folder,
without the link. The second entry is not a PyPI wheel, as its identical
`.devN+g<hash>` version shows. The `__file__` check in step 2 is the one to
trust.

## Step 3: Prepare the machine

Resource numbers are only comparable if they come from the **same machine,
under similar load**:

- Use the machine you will also use after the redesign, and write down which
  one it is.
- Close heavy applications and don't run other jobs in parallel.
- Make sure there is enough disk space. All outputs and all pytest temp files
  are kept, which can be several GB if the em/apm/mpes data is large.
- On a laptop, keep it plugged in.

## Step 4: Dry run on one small plugin

Keep the three scripts **and all results in one folder**, so the distro tree
stays as it is. Put the scripts in their own folder (here
`pynxtools_baseline_scripts/` inside the distro) and **run them from the
distro root**:

```bash
cd ~/nomad-distro-dev
mkdir -p pynxtools_baseline_scripts
cp /path/to/{run_baseline.sh,monitor_resources.py,compare_baselines.py} pynxtools_baseline_scripts/
chmod +x pynxtools_baseline_scripts/*.sh pynxtools_baseline_scripts/*.py
PACKAGES="pynxtools-xrd" pynxtools_baseline_scripts/run_baseline.sh
```

Everything the run produces goes to
`pynxtools_baseline_scripts/baseline_results/baseline_<timestamp>/`.
Nothing is written into `packages/` (pytest's cache and `.pyc` files are
switched off, and pytest's temporary files go into the results folder).
Because the folder is inside the distro repo, the script adds
`/pynxtools_baseline_scripts/` to the distro's **`.git/info/exclude`**, which
works like `.gitignore` but is local and never committed. So `git status`
stays clean, and the run itself isn't recorded as an "uncommitted change". You
can keep the folder anywhere else as well, since the results always go next to
the script. Set `OUT_ROOT=/some/path` to put them somewhere different.

This takes about a minute. Open the new `baseline_<timestamp>/` folder and
check that `pynxtools-xrd/conversions/pynxtools-xrd-*/pynxtools-xrd-*_output.nxs`
exists and that `summary_conversions.csv` shows `OK`. Delete this trial folder
afterwards.

## Step 5: Full run

pynxtools-apm is excluded from this baseline, so pass the package list
explicitly, and run in the background so that closing the terminal doesn't
stop it:

```bash
cd ~/nomad-distro-dev
PACKAGES="$(cd packages && ls -d pynxtools* | grep -vx pynxtools-apm | tr '\n' ' ')" nohup pynxtools_baseline_scripts/run_baseline.sh > /dev/null 2>&1 &
sleep 5; tail -f "$(ls -td pynxtools_baseline_scripts/baseline_results/baseline_*/ | head -1)run.log"   # Ctrl+C stops only tail
```

You can use tmux instead: open `tmux`, run the same `PACKAGES=… ./run_baseline.sh`
line without `nohup` and `&` (still from the distro root), and detach with Ctrl+B then D. Use **the same
`PACKAGES` line** after the redesign, so both runs cover the same packages.

These are the useful settings (environment variables):

| Variable | Default | Use |
|---|---|---|
| `DISTRO_DIR` | current dir | path to nomad-distro checkout |
| `PYTHON` | `$DISTRO_DIR/.venv/bin/python` | interpreter of the distro venv |
| `OUT_ROOT` | `baseline_results/` next to the script | where `baseline_<timestamp>/` is created |
| `PACKAGES` | all `packages/pynxtools*` | restrict to some packages |
| `STEP_TIMEOUT` | 7200 | seconds before one pytest run or conversion is killed |
| `EXTRA_TSV` | built-in em/apm list | your own list of extra conversions |
| `PYTEST_ARGS` | empty | extra pytest flags |
| `SKIP_PYTEST`, `SKIP_REPLAY`, `SKIP_EXTRA` | 0 | skip a phase |
| `MONITOR` | 1 | `0` turns the resource monitor off |
| `MONITOR_INTERVAL` | 0.5 | monitor sampling interval in seconds |

For each package, the script does this:

1. **Runs the full pytest suite** with `-v -rA --durations=0`, a JUnit XML
   file, and `--basetemp` pointing into the baseline folder. Every file a test
   writes (including the `output.nxs` files from `ReaderTest`) is kept, and
   wall time and peak RAM are measured for the whole run. When the run ends,
   each of those files is renamed to `<package>-<test folder>_<file>`, and the
   old-to-new name mapping is saved in `<package>_tmp_files_renamed.tsv`.
2. **Records every `convert()` call** the tests make, using a small pytest
   plugin that wraps `pynxtools.dataconverter.convert.convert`. It logs the
   reader, NXDL, input files and options to `pytest/<package>_conversions.jsonl`.
3. **Replays each recorded conversion in its own fresh Python process**. Doing
   it this way gives every conversion its own `<package>-<case>_output.nxs`,
   `<package>-<case>_convert.log`, and
   per-conversion wall time, CPU time and **peak RAM**. Inside pytest, all
   conversions share one process, so peak RAM can't be separated there.
4. **Validates and annotates each output** with `pynx validate` and `pynx read`,
   or with the older `validate_nexus` / `read_nexus` if `pynx` doesn't exist.
   The annotator log (`*_read.log`) is a full text dump of the file's structure,
   which makes it the best thing to diff later.
5. **Runs extra conversions from a TSV file**, for cases that the test suites
   skip. The built-in list covers the em and apm `default` examples. To add more
   (for example datasets from a plugin's `examples/` folder), write a
   tab-separated file and pass it with `EXTRA_TSV=...`:

   ```
   # package	case	reader	nxdl	ignore_undocumented	input_globs (relative to package dir)
   pynxtools-em	default	em	NXem	1	tests/data/default/*
   pynxtools-xps	my_case	xps	NXxps	0	examples/foo/*.vms examples/foo/eln_data.yaml
   ```

6. **Monitors resources the whole time.** `monitor_resources.py` samples the
   complete process tree of the run every 0.5 s. Each process is tagged with
   the `BASELINE_PACKAGE`, `BASELINE_STEP` (`environment`, `pytest`,
   `convert`, `validate`, `read`) and `BASELINE_CASE` (conversion) it
   inherited, and the results go to `00_monitor/`:
   - `processes.csv`: raw time series, one row per process per sample (RSS,
     VMS, CPU time, CPU %, threads, disk read/write, command line).
   - `system.csv`: whole-machine CPU, RAM, swap and load, plus totals for the
     run. Use it to spot background load that would distort the numbers.
   - `summary_by_step.csv`: per package, step and conversion. Contains the
     duration, the **peak RAM of all its processes together**, the peak of the
     largest single process, CPU seconds, average cores used, max threads and
     disk I/O.
   - `summary_by_package.csv`, `summary_by_process.csv`.
   - `summary_by_test.csv`: per pytest test id, using start and end events
     from the pytest recorder (duration, peak RSS, CPU seconds).

   The monitor needs `psutil`. If the distro venv doesn't have it, the script
   runs the monitor through `uv run --no-project --with psutil`, so the venv
   you are baselining stays untouched. You can also use it on its own around
   any command:

   ```bash
   uv run --no-project --with psutil python monitor_resources.py --out mon/ -- <command>
   ```

Failures never stop the run. Each one is recorded and the script moves on.

## Step 6: Review and triage

Start with the two CSVs and `run.log`:

- `summary_tests.csv` has one row per package: tests, passed, failed, errors,
  skipped, wall time and peak RAM.
- `summary_conversions.csv` has one row per conversion: reader, NXDL, status
  (`OK`, `CONVERT_FAILED`, `VALIDATION_FAILED` or `NOT_REPLAYABLE`), wall time,
  CPU time, peak RAM, output size, the number of warnings and errors in the
  convert and validate logs, and a sha256 of the output.

Sort every failure into one of two buckets:

- **Environment problem** (a missing dependency, a NOMAD config issue, missing
  test data): fix the environment, **not the code**, and rerun only that
  package with `PACKAGES="pynxtools-xxx" ./run_baseline.sh`. Then replace that
  package's folder in the baseline and note it.
- **Genuine pre-existing failure**: keep it. It is part of the baseline. If the
  same thing fails after the redesign, that is not a regression.

Write both buckets down in a `NOTES.md` inside the baseline folder, along with
the machine, the date and anything unusual.

## Step 7: Measure the noise (recommended)

Timing and RAM vary from run to run. Run the full baseline **2 to 3 times**
and keep all the runs. The spread between them tells you how big a difference
has to be after the redesign before it counts as a real change. A ±10 % change
in wall time may be pure noise.

## Step 8: Archive

```bash
cd pynxtools_baseline_scripts/baseline_results
tar -czf baseline_<timestamp>.tar.gz baseline_<timestamp>/
```

Store the archive somewhere permanent, together with the git tag name from
step 1. `MANIFEST.sha256` lists a checksum for every file, so you can later
prove the baseline was not altered.

---

## Output layout

Every file carries the package and case it belongs to in its own name, so no
two files in a baseline share a name, even after you copy them out of their
folders. `<case>` is the test's parameter id (for example `vms_regular` from
`test_nexus_conversion[vms_regular]`) or, for extra conversions, `extra_<case>`
from the TSV. If the same case appears twice in a package, the second one gets
`-2`.

```
pynxtools_baseline_scripts/          # one folder for scripts + results (git-excluded)
├── run_baseline.sh, monitor_resources.py, compare_baselines.py
└── baseline_results/
    └── baseline_<timestamp>/        # one folder per run, content below

baseline_<timestamp>/
├── run.log                      # everything printed on screen
├── summary_tests.csv
├── summary_conversions.csv
├── MANIFEST.sha256
├── 00_monitor/                  # per-process resource time series + summaries (see step 5)
├── 00_environment/
│   ├── system.txt               # OS, CPU, RAM, disk, uv/git versions
│   ├── python.txt               # Python, h5py/HDF5, numpy versions
│   ├── installed_packages.txt   # name==version, with editable source paths
│   ├── readers.txt              # readers + supported NXDLs, entry points
│   ├── git_state.tsv            # commit/tag/branch/dirty of distro + every package (+ NeXus definitions)
│   ├── git_submodules.txt
│   ├── uncommitted_changes/     # diffs, only if something was dirty
│   ├── distro_pyproject.toml, distro_uv.lock
│   ├── env_vars.txt             # only selected, non-secret variables
│   └── cli_help.txt
├── _tools/                      # exact helper scripts + extra_conversions.tsv used
└── pynxtools-<plugin>/
    ├── pytest/
    │   ├── <package>_pytest.log             # full verbose pytest output
    │   ├── <package>_junit.xml              # per-test results and durations
    │   ├── <package>_pytest_resources.json  # wall, CPU, peak RAM of the whole suite
    │   ├── <package>_conversions.jsonl      # every convert() call the tests made
    │   ├── <package>_test_events.jsonl      # start/end time of every test (used by the monitor)
    │   ├── <package>_tmp_files_renamed.tsv  # original -> prefixed names of the tests' files
    │   └── tmp_files/<test folder>/<package>-<test folder>_output.nxs, ...
    └── conversions/
        └── <package>-<case>/                # e.g. pynxtools-xps-vms_regular
            ├── <package>-<case>_call.json               # reader, nxdl, inputs, options
            ├── <package>-<case>_output.nxs              # the converted NeXus file
            ├── <package>-<case>_convert.log             # full conversion output
            ├── <package>-<case>_convert_resources.json  # wall, CPU, peak RAM of this conversion
            ├── <package>-<case>_validate.log, <package>-<case>_validate_resources.json
            ├── <package>-<case>_read.log, <package>-<case>_read_resources.json  # annotator dump
            └── <package>-<case>_STATUS.txt
```

---

## After the redesign: comparing

1. Check out the redesigned code, rebuild the environment the same way (step 2)
   and use **the same machine**.
2. Run the **same scripts** (copies are archived in the baseline's `_tools/`).
   If the redesign renames CLIs or moves `convert()`, update only the tooling
   (for example `replay_convert.py`), never the inputs.
3. Compare, using the distro venv's Python because it needs h5py:

   ```bash
   cd pynxtools_baseline_scripts
   ../.venv/bin/python compare_baselines.py baseline_results/baseline_<before> baseline_results/baseline_<after> \
       --out baseline_results/compare_report
   ```

   Start with `compare_report/report.md`. It contains:
   - **Verdict and exit code:** `0` means no functional regressions, `1` means
     regressions were found, so the script can also be used in CI.
   - **Environment:** host, OS, CPU and Python, git commit of every package,
     and changed package versions (`packages_diff.csv`). You get a warning if
     the two runs were on different machines.
   - **Tests:** pass/fail/error/skip counts per package, and every test whose
     outcome changed (`tests_comparison.csv`).
   - **Conversions:** matched by package, test id, reader and NXDL. Shows
     status changes and conversions that are new or missing
     (`conversions_comparison.csv`).
   - **NeXus content:** every pair of `*_output.nxs` files is compared with
     h5py, covering groups, fields, attributes, dtypes, shapes and values
     (float tolerance `--rtol` / `--atol`). Volatile items (file times, version
     strings, `profiling/` timings) are listed separately and never count as a
     difference. Add your own with `--ignore REGEX`. The details go in
     `content_diffs/<package>/<conversion>/<conversion>_h5_diff.txt`, together
     with `<conversion>_messages.diff` (new or removed WARNING/ERROR messages)
     and `<conversion>_read_log.diff` (the annotator dump). Baselines made with
     the earlier, unprefixed file names can still be compared. The annotator diff also changes
     when the annotator's own output format changes, so the h5py comparison
     is the authoritative one.
   - **Resources:** wall time, CPU time and peak RAM per conversion and per test
     suite, plus per step from the monitor (`monitor_steps_comparison.csv`). A
     change is flagged only if it is above `--time-tol` / `--rss-tol` (default
     15 % / 10 %) **and** above `--min-time-s` / `--min-rss-mb`. Set the
     tolerances from the noise you measured in step 7. With
     `--fail-on-resources`, resource regressions also make the exit code `1`.

---

## Known limitations

- **Peak RAM** is the peak resident memory of the largest process in each
  measured step. Memory that is shared or released earlier is not added up.
- A conversion whose options can't be serialised (for example a Python object
  passed as a keyword) is marked `NOT_REPLAYABLE`. It is still covered by the
  pytest run and its `tmp_files`, just without its own resource numbers.
- Tests that need NOMAD (`test_nomad_examples.py`, NOMAD parsing inside
  `ReaderTest`) need `nomad-lab` installed and configured. In the distro venv
  that should already be the case.
- Jupyter notebooks in the plugins' `examples/` folders are not executed. Add
  any example datasets you care about to the extra-conversions TSV.
- The monitor samples every 0.5 s. A process shorter than that can be missed,
  but its totals are still in that step's `*_resources.json` file. Peak RAM in the
  monitor includes the small `measure.py` wrapper process (about 12 MB).
- The script is tested on Linux and should also work on macOS. It does not
  need GNU `time`, because it measures with Python's `resource` module.
