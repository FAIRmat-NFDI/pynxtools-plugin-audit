# Skipped tests in the baseline

Some plugin tests report `SKIPPED` in the baseline. None of them are caused by the baseline scripts. They are skips that the plugin developers built in, at the commits recorded in `baseline_commits.md`. To list them for a run:

```bash
R=$(ls -td pynxtools_baseline_scripts/baseline_results/baseline_*/ | head -1)
grep -h "^SKIPPED" ${R}pynxtools-{em,microstructure,igor,spm}/pytest/*_pytest.log
```

## pynxtools-em (`340f154`)

| Test | Reason | Kind |
|---|---|---|
| `tests/test_reader.py:95` (conversion test) | "Working for the default example location of large test data should be clarified though" | Deliberate. The em test data are too large to ship in the repo. |

The baseline covers em through `extra_conversions.tsv` instead: the `tests/data/default` example and the three InGaN EDS files from Zenodo (see `DATA_SOURCES.md`).

## pynxtools-microstructure (`bf0ce65`)

| Test | Reason | Kind |
|---|---|---|
| `tests/test_reader.py:54` | "No example yet" | Deliberate. The plugin has no test data in the repo. |
| `tests/test_utils_versioning.py:26` | "No tags available yet..." | Deliberate. The repo has no release tags yet. |
| `tests/test_nomad_north_tools.py:14` | "No functional north tool yet" | Deliberate. The feature does not exist yet. |
| `tests/nomad/test_nomad_example_uploads.py:52` | "got empty parameter set for (mainfile)" | Automatic pytest skip. The example upload folder contains only a README, so there is nothing to parametrize. |

The baseline covers microstructure through `extra_conversions.tsv` instead, with the `001.*.mtex.h5` example from Markus Kühbach (see `DATA_SOURCES.md`).

## pynxtools-igor (`07ed951`)

Result of baseline_20261026_161939: **1 skip**.

| Test | Reason | Kind |
|---|---|---|
| `tests/nomad/test_nomad_example_uploads.py:52` (`test_parse_nomad_examples`) | "got empty parameter set for (mainfile)" | Automatic pytest skip, not an error. The test is parametrized over NOMAD example *mainfiles* (`*schema.archive.yaml/json`, `intra-entry.archive.json`, ...) found by `pynxtools.testing.nomad_example.get_file_parameter` in `src/pynxtools_igor/nomad/example_uploads/example/`. That folder holds only raw data (`.pxp`, `.ibw`), config JSONs and notebooks, so there is nothing to parametrize and pytest skips the test. The same thing happens in microstructure. |

The module-level "nomad-lab is not installed" skip in the same file (line 27) did **not** fire, which confirms NOMAD is importable in the baseline environment.

## pynxtools-spm (`a57cd20`)

Result of baseline_20261026_161939: **12 skips = 3 tests x 4 files**.

`tests/test_scan_region_convention.py` runs three convention tests on every reference `.nxs` file in `tests/data/` (19 files), through the fixture `image_file` (line 107):

| Line | Test | What it checks |
|---|---|---|
| 111 | `test_start_and_end_bracket_the_offset` | `scan_start`/`scan_end` = offset -/+ range/2 on x and y |
| 121 | `test_axes_are_upper_case_and_centred_on_the_offset` | 2D NXdata axes are `[Y, X]`, ascending and centred on the scan offset |
| 137 | `test_independent_scan_axes_runs_fast_to_slow` | `independent_scan_axes` lists the axes fastest first |

When a file has no 2D scan region, the fixture skips with "no 2D scan region: a bias sweep or a force ramp". This applies to 4 of the 19 files, and each of them skips all three tests (3 x 4 = 12):

- `nanonis/sts/v_gen_5_descrb_nx_dt/sts_5_described_nxdata.nxs` (STS bias sweep)
- `nanonis/sts/v_gen_5e_descrb_nx_dt/sts_5e_described_nxdata.nxs` (STS bias sweep)
- `nanonis/sts/v_gen_5e_dflt_conf/sts_5e_default_config.nxs` (STS bias sweep)
- `bruker/afm/txt_dflt_conf/afm_txt_default_config.nxs` (AFM force ramp, text export)

This is deliberate and expected: a scan-region convention cannot apply to a measurement without a 2D scan. The NOMAD "not installed" skips in `tests/nomad/` (lines 25, 26) did not fire.

## For the comparison after the redesign

A skip that turns into pass or fail, or the other way round, shows up in `compare_baselines.py` under `tests_comparison.csv`. The em and microstructure skips should go away once those plugins ship test data in their repos.
