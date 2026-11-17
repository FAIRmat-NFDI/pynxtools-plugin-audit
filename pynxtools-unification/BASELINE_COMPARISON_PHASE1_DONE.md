# Baseline after Phase 1: `baseline_20261117_120246_phase1_done`

**Date:** 2026-11-17
**Status:** reference baseline for Phase 2 onwards. It replaces the pre-redesign baseline `baseline_20261026_161939` (Phase 0) as the point that later changes are compared against.

## What it is

A full run of `run_baseline.sh` on `nomad-distro-dev` (Ubuntu 24.04.3, Python 3.12.3) after all Phase 1 bug-fix PRs were merged. It covers 11 packages; pynxtools-apm is excluded and pynxtools-microstructure is unchanged, as in Phase 0.

| Package | Branch | Commit | Last change |
|---|---|---|---|
| pynxtools | develop | `f9f12a06` | B13 processing order (#870) |
| pynxtools-ellips | develop | `dc620d7` | B16 (#50) |
| pynxtools-em | develop | `ae9e1f5` | B36 xmltodict>=0.13 (#189) |
| pynxtools-igor | develop | `e805c23` | B31 (#23) |
| pynxtools-microstructure | develop | `bf0ce65` | unchanged since Phase 0 (out of scope) |
| pynxtools-mpes | develop | `118ce65` | unchanged since Phase 0 |
| pynxtools-raman | develop | `754cf0d` | B29 (#71) |
| pynxtools-spm | develop | `2dc3316` | B27 (#126) |
| pynxtools-xas | develop | `bc65bad` | B12 (#11) |
| pynxtools-xps | develop | `3bfdcbe` | B29 (#220) |
| pynxtools-xrd | develop | `1051681` | B21 (#39) |
| fairmat-readers-xrd | PyPI | `0.0.10` | dependency, from the distro lock file |

## Not included

- **B22** (xps #216) and **B37** (spm #137): still in review when this baseline was taken. Each will show up later as a small, known diff.
- **readers-xrd ≥ 0.1.0** (B34, and the Quantity wavelengths in 0.2.0): the distro lock file still pins 0.0.10. Upgrade it separately (`uv lock --upgrade-package fairmat-readers-xrd`) and compare xrd on its own.
- Phase 1 bugs that were skipped, postponed or dropped (B2, B4, B7, B11, B18, B19, B24, and B3 for apm/microstructure); see FINDINGS §6.

## Results

| Package | Tests | Pass | Fail | Skip |
|---|---|---|---|---|
| pynxtools | 770 | 770 | 0 | 0 |
| pynxtools-ellips | 21 | 21 | 0 | 0 |
| pynxtools-em | 13 | 12 | 0 | 1 |
| pynxtools-igor | 14 | 13 | 0 | 1 |
| pynxtools-microstructure | 6 | 2 | 0 | 4 |
| pynxtools-mpes | 10 | 10 | 0 | 0 |
| pynxtools-raman | 141 | 141 | 0 | 0 |
| pynxtools-spm | 374 | 362 | 0 | 12 |
| pynxtools-xas | 9 | 9 | 0 | 0 |
| pynxtools-xps | 248 | 248 | 0 | 0 |
| pynxtools-xrd | 8 | 8 | 0 | 0 |

Conversions: 65 in total, 61 OK. The 4 that fail are pynxtools' own negative tests (`test_find_nxdl[does-not-exist]`, `[exists-in-applications]`, `[exists-in-contributed]` and `test_cli[input-file]`). They are meant to fail, and they failed the same way in Phase 0.

## Comparison with Phase 0 (`baseline_20261026_161939`)

Verdict of `compare_baselines.py`: 0 test regressions, 0 conversion regressions, 0 new errors, and **18 content diffs, all intended**:

| Conversions | Change | Bug, PR |
|---|---|---|
| 11 × raman (ROD) | `start_time` `2011-09-07T00:00:00+00:00` → `2011-09-07` (no invented time or zone); the ROD reader test also lists the unused `datetime_initiated` key | B29, raman #71 |
| 2 × spm Bruker AFM (`spm_v_9_4_dflt_conf_up` / `_down`) | `lockin_amplifier/reference_frequency/@units` Hz → kHz | B28, spm #128 |
| 2 × xps VAMAS (regular, irregular) | count rate no longer rounded (`data/data` max abs diff 0.005) | B21, xps #204 |
| 2 × xps VAMAS (irregular, with data analysis) | `start_time` `0001-01-01T00:00:00` → the date set in the test ELN | B29, xps #220 |
| 1 × xps SPECS SLE | all-ones transmission function groups removed | B26, xps #222 |
| 1 × xrd XRDML | `omega/step` and `two_theta/step` unrounded (4 decimals); `kbeta/@units` `''` → `angstrom` | B21 xrd #39, B23 xrd #38 |

Everything else differs only in volatile items: `@file_time`, `@file_update_time`, em/microstructure profiling times and the kernel version.

Fixes with no visible diff: the time zone fix (B25) changes nothing here, because the test files either carry a zone or were converted on a machine in the same zone. Many other fixes (B1, B8, B12, B13, B31, …) only matter for inputs that the test data does not contain. Each of them has its own regression test in its plugin.

## Known noise

- **em InGaN EDS map:** `atom_types` can change order between runs (`Ga, N, In` vs `In, Ga, N`). It looks like a Python set and is not caused by Phase 1. Expect it in every comparison until it is fixed in em.
- **Run times:** wall and CPU times came out about 50–80% higher on all conversions, including untouched ones. That is machine load, not the fixes and the current comparison was done under higher computing load. Repeat the run before trusting a resource comparison.

## How to compare against it

```bash
cd ~/nomad-distro-dev
NEW=$(ls -td pynxtools_baseline_scripts/baseline_results/baseline_* | head -1)
uv run --no-sync python pynxtools_baseline_scripts/compare_baselines.py \
    pynxtools_baseline_scripts/baseline_results/baseline_20261117_120246_phase1_done "$NEW" \
    --packages pynxtools,pynxtools-xps   # comma-separated, only the packages that were run
```

The report is written to `compare_<old>__vs__<new>/report.md` in the distro root. `content_diffs/*/*/*_h5_diff.txt` shows the actual HDF5 differences. Archive: `baseline_20261117_120246_phase1_done.tar.gz` (kept locally, not in git).
