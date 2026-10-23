#!/usr/bin/env bash
# =============================================================================
# run_baseline.sh - pre-redesign baseline for pynxtools + all its plugins
#
# Runs, for pynxtools and every pynxtools plugin found in <nomad-distro>/packages/:
#   1. the package's own pytest suite (verbose log, JUnit XML, all pytest tmp
#      files kept, wall time + peak RAM of the whole run)
#   2. every NeXus conversion that the test suite performs, replayed one by
#      one in a fresh process, so each conversion gets its own output .nxs,
#      log, wall time and peak RAM; each output is then validated and annotated
#   3. extra conversions listed in a TSV (for cases the test suites skip)
# and records the environment (OS, Python, installed packages, git commits of
# nomad-distro and every package) so the run can be reproduced and compared.
#
# Nothing aborts on failure: every step's exit code is recorded and the run
# continues. Results end up in summary_tests.csv / summary_conversions.csv.
#
# Usage (from anywhere):
#   chmod +x run_baseline.sh
#   DISTRO_DIR=~/nomad-distro-dev ./run_baseline.sh
#
# Optional environment variables:
#   DISTRO_DIR       nomad-distro checkout with packages/        (default: $PWD)
#   PYTHON           python of the distro venv     (default: $DISTRO_DIR/.venv/bin/python)
#   OUT_ROOT         where baseline_<timestamp>/ is created
#                    (default: baseline_results/ next to this script, so scripts and
#                    results live in ONE folder; if that folder is inside the distro
#                    it is added to the distro's local .git/info/exclude, so
#                    `git status` stays clean)
#   PACKAGES         space-separated package dir names to run, e.g.
#                    "pynxtools pynxtools-xps"           (default: packages/pynxtools*)
#   EXTRA_TSV        TSV of extra conversions (see write_default_extra_tsv below)
#   STEP_TIMEOUT     seconds before one pytest run / conversion is killed (default 7200)
#   SKIP_PYTEST=1    skip step 1 (then step 2 has nothing to replay)
#   SKIP_REPLAY=1    skip step 2
#   SKIP_EXTRA=1     skip step 3
#   PYTEST_ARGS      extra arguments appended to every pytest call (e.g. "-x")
#   MONITOR=0        do not run monitor_resources.py alongside (default: run it
#                    if monitor_resources.py sits next to this script)
#   MONITOR_INTERVAL sampling interval of the monitor in seconds (default 0.5)
# =============================================================================

set -uo pipefail   # deliberately no "set -e": failures are recorded, not fatal

# ----------------------------------------------------------------------------
# 0. Configuration
# ----------------------------------------------------------------------------
DISTRO_DIR="$(cd "${DISTRO_DIR:-$PWD}" && pwd)"
PYTHON="${PYTHON:-$DISTRO_DIR/.venv/bin/python}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_ROOT="${OUT_ROOT:-$SCRIPT_DIR/baseline_results}"
mkdir -p "$OUT_ROOT" && OUT_ROOT="$(cd "$OUT_ROOT" && pwd)"
STEP_TIMEOUT="${STEP_TIMEOUT:-7200}"
PYTEST_ARGS="${PYTEST_ARGS:-}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$OUT_ROOT/baseline_${STAMP}"
TOOLS="$OUT/_tools"
ENVDIR="$OUT/00_environment"

if [[ ! -d "$DISTRO_DIR/packages" ]]; then
    echo "ERROR: $DISTRO_DIR/packages not found. Set DISTRO_DIR to your nomad-distro checkout." >&2
    exit 2
fi
if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: python not found at $PYTHON. Run 'uv sync' in the distro or set PYTHON=..." >&2
    exit 2
fi
PYBIN="$(dirname "$PYTHON")"
export PATH="$PYBIN:$PATH"          # dataconverter / pynx / validate_nexus from the venv
export PYTHONDONTWRITEBYTECODE=1    # keep package trees clean
export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg               # no plot windows from readers/tests

mkdir -p "$OUT" "$TOOLS" "$ENVDIR"

# Keep the distro clean: if the baseline folder sits inside the distro repo,
# hide its top-level folder via .git/info/exclude (local only, never committed).
case "$OUT_ROOT/" in
    "$DISTRO_DIR"/*)
        top="${OUT_ROOT#"$DISTRO_DIR"/}"; top="${top%%/*}"
        excl="$(git -C "$DISTRO_DIR" rev-parse --git-path info/exclude 2>/dev/null)"
        if [[ -n "$excl" ]]; then
            [[ "$excl" = /* ]] || excl="$DISTRO_DIR/$excl"
            mkdir -p "$(dirname "$excl")"
            grep -qxF "/$top/" "$excl" 2>/dev/null || echo "/$top/" >> "$excl"
        fi
        ;;
esac
exec > >(tee -a "$OUT/run.log") 2>&1   # everything printed below also lands in run.log

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# ----------------------------------------------------------------------------
# Helper python tools (written into the output folder so the run is
# self-documenting: anyone can see exactly what was executed)
# ----------------------------------------------------------------------------

# measure.py: run a command, record exit code, wall time, CPU time, peak RSS.
cat > "$TOOLS/measure.py" <<'PY'
"""Usage: measure.py RESULT.json TIMEOUT_S -- cmd args...  (stdout/stderr pass through)"""
import datetime, json, resource, subprocess, sys, time

out, timeout = sys.argv[1], float(sys.argv[2])
cmd = sys.argv[sys.argv.index("--") + 1:]
started = datetime.datetime.now().isoformat(timespec="seconds")
t0 = time.perf_counter()
timed_out = False
try:
    rc = subprocess.run(cmd, timeout=timeout).returncode
except subprocess.TimeoutExpired:
    rc, timed_out = 124, True
    print(f"[measure] TIMEOUT after {timeout:.0f} s: {cmd}", file=sys.stderr)
except FileNotFoundError as exc:
    rc = 127
    print(f"[measure] {exc}", file=sys.stderr)
wall = time.perf_counter() - t0
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
# ru_maxrss: kilobytes on Linux, bytes on macOS. Peak of the largest child process.
rss_bytes = ru.ru_maxrss if sys.platform == "darwin" else ru.ru_maxrss * 1024
with open(out, "w") as fh:
    json.dump(
        {
            "cmd": cmd,
            "started": started,
            "exit_code": rc,
            "timed_out": timed_out,
            "wall_s": round(wall, 3),
            "user_cpu_s": round(ru.ru_utime, 3),
            "sys_cpu_s": round(ru.ru_stime, 3),
            "peak_rss_mb": round(rss_bytes / 2**20, 1),
        },
        fh,
        indent=2,
    )
sys.exit(rc)
PY

# baseline_recorder.py: pytest plugin that records every call to
# pynxtools.dataconverter.convert.convert() made by a test suite.
cat > "$TOOLS/baseline_recorder.py" <<'PY'
"""pytest plugin (-p baseline_recorder): append each convert() call to $BASELINE_RECORD_FILE."""
import functools, inspect, json, os, pathlib, sys, time

_ORIG = None


def _jsonable(obj, flags):
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, (pathlib.PurePath,)):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [_jsonable(o, flags) for o in obj]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v, flags) for k, v in obj.items()}
    flags["replayable"] = False
    return {"__repr__": repr(obj)}


def _wrap(orig):
    sig = inspect.signature(orig)
    var_kw = next((n for n, p in sig.parameters.items() if p.kind == p.VAR_KEYWORD), None)

    @functools.wraps(orig)
    def wrapper(*args, **kwargs):
        try:
            call = dict(sig.bind_partial(*args, **kwargs).arguments)
            if var_kw:
                call.update(call.pop(var_kw, {}) or {})
        except TypeError:
            call = {"__args__": list(args), **kwargs}
        status, t0 = "ok", time.perf_counter()
        try:
            return orig(*args, **kwargs)
        except BaseException as exc:  # recorded, then re-raised unchanged
            status = f"raised {type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            flags = {"replayable": True}
            rec = {
                "test_id": os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0],
                "cwd": os.getcwd(),
                "status_in_test": status,
                "seconds_in_test": round(time.perf_counter() - t0, 3),
                "call": _jsonable(call, flags),
            }
            rec["replayable"] = flags["replayable"] and "__args__" not in call
            path = os.environ.get("BASELINE_RECORD_FILE")
            if path:
                with open(path, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")

    wrapper.__baseline_wrapped__ = True
    return wrapper


def _patch_everywhere():
    global _ORIG
    try:
        import pynxtools.dataconverter.convert as mod
    except Exception as exc:
        print(f"[baseline_recorder] cannot import pynxtools: {exc}", file=sys.stderr)
        return
    if _ORIG is None:
        _ORIG = mod.convert
        mod.convert = _wrap(_ORIG)
    # modules that already did "from ...convert import convert"
    for m in list(sys.modules.values()):
        try:
            if getattr(m, "convert", None) is _ORIG:
                setattr(m, "convert", mod.convert)
        except Exception:
            pass


def pytest_configure(config):
    _patch_everywhere()


def _event(kind, nodeid):
    path = os.environ.get("BASELINE_EVENTS_FILE")
    if path:
        with open(path, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "event": kind, "nodeid": nodeid, "pid": os.getpid()}) + "\n")


def pytest_runtest_logstart(nodeid, location):
    _event("start", nodeid)


def pytest_runtest_logfinish(nodeid, location):
    _event("finish", nodeid)


def pytest_collection_finish(session):
    _patch_everywhere()
PY

# prepare_conversions.py: turn recorded calls + extra TSV rows into one folder
# per conversion. Folder AND every file in it carry "<package>-<case>" in their
# name (e.g. pynxtools-xps-vms_regular_output.nxs), so no two files share a name.
cat > "$TOOLS/prepare_conversions.py" <<'PY'
"""Usage: prepare_conversions.py PKG_NAME PKG_DIR RECORDS.jsonl EXTRA.tsv OUT_DIR  -> prints created dirs"""
import glob, json, os, re, sys

pkg_name, pkg_dir, records, extra_tsv, out_dir = sys.argv[1:6]
os.makedirs(out_dir, exist_ok=True)
slug = lambda s: re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_.")[:90] or "conversion"
used = set()


def case_name(test_id):
    """tests/test_reader.py::test_nexus_conversion[vms_regular] -> vms_regular"""
    func = test_id.split("::")[-1] or "test"
    return func[func.index("[") + 1:func.rindex("]")] if "[" in func and func.endswith("]") else func


def emit(case, rec):
    base = f"{pkg_name}-{slug(case)}"
    name, i = base, 1
    while name in used:  # same case twice in one package -> -2, -3, ...
        i += 1
        name = f"{base}-{i}"
    used.add(name)
    rec["conversion_name"] = name
    d = os.path.join(out_dir, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{name}_call.json"), "w") as fh:
        json.dump(rec, fh, indent=2)
    print(d)


if os.path.isfile(records):
    seen = set()
    for line in open(records):
        rec = json.loads(line)
        rec["source"] = "pytest"
        key = json.dumps({k: v for k, v in rec["call"].items() if k != "output"}, sort_keys=True)
        rec["duplicate_of_earlier_call"] = key in seen
        seen.add(key)
        emit(case_name(rec["test_id"]), rec)

if extra_tsv and os.path.isfile(extra_tsv):
    for line in open(extra_tsv):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 6 or cols[0] != pkg_name:
            continue
        _, case, reader, nxdl, ignore_undoc, patterns = cols[:6]
        files = sorted(
            f for p in patterns.split() for f in glob.glob(os.path.join(pkg_dir, p)) if os.path.isfile(f)
        )
        call = {"input_file": files, "reader": reader, "nxdl": nxdl,
                "ignore_undocumented": ignore_undoc.strip() in ("1", "true", "True")}
        emit(f"extra_{case}", {"source": "extra_tsv", "test_id": f"extra::{case}",
                               "replayable": bool(files), "call": call})
PY

# replay_convert.py: run one recorded conversion in a fresh process.
cat > "$TOOLS/replay_convert.py" <<'PY'
"""Usage: replay_convert.py CALL.json OUTPUT.nxs"""
import json, logging, os, sys

rec = json.load(open(sys.argv[1]))
call = dict(rec["call"])
call["output"] = os.path.abspath(sys.argv[2])
if rec.get("cwd") and os.path.isdir(rec["cwd"]):
    os.chdir(rec["cwd"])  # relative input paths resolve as they did in the test
if isinstance(call.get("input_file"), list):
    call["input_file"] = tuple(call["input_file"])
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
print("Replaying conversion from test:", rec.get("test_id"))
print(json.dumps(call, indent=2, default=str), flush=True)
from pynxtools.dataconverter.convert import convert
convert(**call)
print("Conversion finished:", call["output"])
PY

# prefix_tmp_files.py: rename every file pytest wrote (ReaderTest always calls
# its output "output.nxs") to "<package>-<test folder>_<file>", so names are unique.
cat > "$TOOLS/prefix_tmp_files.py" <<'PY'
"""Usage: prefix_tmp_files.py PKG TMP_DIR  -> prints old<TAB>new for every renamed file"""
import os, sys

pkg, tmp = sys.argv[1], sys.argv[2]
print("old_path\tnew_path")
for dp, _, files in os.walk(tmp):
    rel = os.path.relpath(dp, tmp)
    if rel == ".":
        continue
    prefix = f"{pkg}-" + rel.replace(os.sep, "-")   # e.g. pynxtools-xps-test_nexus_conversion_vms0
    for f in files:
        if f.startswith(prefix):
            continue
        new = f"{prefix}_{f}"
        os.rename(os.path.join(dp, f), os.path.join(dp, new))
        print(f"{os.path.join(rel, f)}\t{os.path.join(rel, new)}")
PY

# summarize.py: build summary CSVs + checksum manifest.
cat > "$TOOLS/summarize.py" <<'PY'
"""Usage: summarize.py BASELINE_DIR"""
import csv, glob, hashlib, json, os, re, sys
import xml.etree.ElementTree as ET

root = sys.argv[1]
load = lambda p: json.load(open(p)) if os.path.isfile(p) else {}
f_ = lambda d, suffix: os.path.join(d, f"{os.path.basename(d)}_{suffix}")  # <pkg>-<case>_<suffix>

def count(path, pattern):
    if not os.path.isfile(path):
        return ""
    return sum(1 for l in open(path, errors="replace") if re.search(pattern, l))

# ---- test suites
rows = []
for pkg in sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d, "pytest"))):
    pdir = os.path.join(root, pkg, "pytest")
    res = load(os.path.join(pdir, f"{pkg}_pytest_resources.json"))
    t = dict(tests=0, failures=0, errors=0, skipped=0)
    junit = os.path.join(pdir, f"{pkg}_junit.xml")
    if os.path.isfile(junit):
        try:
            for ts in ET.parse(junit).getroot().iter("testsuite"):
                for k in t:
                    t[k] += int(ts.get(k, 0))
        except ET.ParseError:
            pass
    rows.append({
        "package": pkg, "tests": t["tests"],
        "passed": t["tests"] - t["failures"] - t["errors"] - t["skipped"],
        "failed": t["failures"], "errors": t["errors"], "skipped": t["skipped"],
        "pytest_exit_code": res.get("exit_code", ""), "wall_s": res.get("wall_s", ""),
        "peak_rss_mb": res.get("peak_rss_mb", ""),
        "conversions_recorded": count(os.path.join(pdir, f"{pkg}_conversions.jsonl"), r"."),
    })
with open(os.path.join(root, "summary_tests.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["package"])
    w.writeheader(); w.writerows(rows)

# ---- individual conversions
crow = []
for d in sorted(glob.glob(os.path.join(root, "*", "conversions", "*"))):
    rec = load(f_(d, "call.json"))
    call = rec.get("call", {})
    res = load(f_(d, "convert_resources.json"))
    nxs = f_(d, "output.nxs")
    sha = ""
    if os.path.isfile(nxs):
        h = hashlib.sha256()
        with open(nxs, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        sha = h.hexdigest()
    status = open(f_(d, "STATUS.txt")).read().strip() if os.path.isfile(f_(d, "STATUS.txt")) else ""
    inputs = call.get("input_file") or []
    crow.append({
        "package": d.split(os.sep)[-3], "conversion": os.path.basename(d),
        "source": rec.get("source", ""), "test_id": rec.get("test_id", ""),
        "duplicate_of_earlier_call": rec.get("duplicate_of_earlier_call", ""),
        "reader": call.get("reader", ""), "nxdl": call.get("nxdl", ""),
        "n_input_files": len(inputs) if isinstance(inputs, list) else 1,
        "output_file": os.path.basename(nxs) if os.path.isfile(nxs) else "",
        "status": status, "convert_exit_code": res.get("exit_code", ""),
        "wall_s": res.get("wall_s", ""), "user_cpu_s": res.get("user_cpu_s", ""),
        "peak_rss_mb": res.get("peak_rss_mb", ""),
        "output_mb": round(os.path.getsize(nxs) / 2**20, 3) if os.path.isfile(nxs) else "",
        "convert_warnings": count(f_(d, "convert.log"), r"\bWARNING\b"),
        "convert_errors": count(f_(d, "convert.log"), r"\bERROR\b"),
        "validate_exit_code": load(f_(d, "validate_resources.json")).get("exit_code", ""),
        "validate_warnings": count(f_(d, "validate.log"), r"\bWARNING\b"),
        "validate_errors": count(f_(d, "validate.log"), r"\bERROR\b"),
        "read_exit_code": load(f_(d, "read_resources.json")).get("exit_code", ""),
        "output_sha256": sha,
    })
with open(os.path.join(root, "summary_conversions.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(crow[0]) if crow else ["package"])
    w.writeheader(); w.writerows(crow)

# ---- checksum manifest of every file in the baseline
with open(os.path.join(root, "MANIFEST.sha256"), "w") as man:
    for dp, _, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(dp, f)
            if f == "MANIFEST.sha256" or f == "run.log":
                continue
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            man.write(f"{h.hexdigest()}  {os.path.relpath(p, root)}\n")

# ---- console overview
print(f"\n{'package':28} {'tests':>6} {'pass':>6} {'fail':>6} {'err':>5} {'skip':>6} {'wall_s':>9} {'RSS_MB':>8}")
for r in rows:
    print(f"{r['package']:28} {r['tests']:>6} {r['passed']:>6} {r['failed']:>6} {r['errors']:>5} "
          f"{r['skipped']:>6} {r['wall_s']!s:>9} {r['peak_rss_mb']!s:>8}")
ok = sum(1 for r in crow if r["status"] == "OK")
print(f"\nconversions: {len(crow)} total, {ok} OK, {len(crow) - ok} not OK "
      f"(see summary_conversions.csv)")
PY

# Default extra conversions. Format (tab separated):
#   package  case  reader  nxdl  ignore_undocumented(0/1)  input globs (relative to package dir)
# pynxtools-em and pynxtools-apm currently mark their conversion test as skipped,
# so their bundled default example is converted here explicitly.
write_default_extra_tsv() {
    printf '%s\n' \
        "# package	case	reader	nxdl	ignore_undocumented	input_globs" \
        "pynxtools-em	default	em	NXem	1	tests/data/default/*" \
        "pynxtools-apm	default	apm	NXapm	1	tests/data/default/*" \
        > "$1"
}
if [[ -n "${EXTRA_TSV:-}" ]]; then
    cp "$EXTRA_TSV" "$TOOLS/extra_conversions.tsv"
else
    write_default_extra_tsv "$TOOLS/extra_conversions.tsv"
fi
cp "$0" "$TOOLS/run_baseline.sh" 2>/dev/null || true

# ----------------------------------------------------------------------------
# Resource monitor: samples every process of this run and tags it with
# BASELINE_PACKAGE / BASELINE_STEP / BASELINE_CASE (set per step below)
# ----------------------------------------------------------------------------
MONITOR_SCRIPT="${MONITOR_SCRIPT:-$SCRIPT_DIR/monitor_resources.py}"
MON_PID=""
stop_monitor() {
    if [[ -n "$MON_PID" ]] && kill -0 "$MON_PID" 2>/dev/null; then
        kill -TERM "$MON_PID" 2>/dev/null
        wait "$MON_PID" 2>/dev/null
    fi
    MON_PID=""
}
trap stop_monitor EXIT
trap 'stop_monitor; exit 130' INT TERM
if [[ "${MONITOR:-1}" == "1" && -f "$MONITOR_SCRIPT" ]]; then
    cp "$MONITOR_SCRIPT" "$TOOLS/monitor_resources.py"
    if "$PYTHON" -c "import psutil" 2>/dev/null; then
        MON_CMD=("$PYTHON")
    elif command -v uv >/dev/null 2>&1; then
        MON_CMD=(uv run --no-project --with psutil python)   # leaves the distro venv untouched
    else
        MON_CMD=()
    fi
    if [[ ${#MON_CMD[@]} -gt 0 ]]; then
        BASELINE_STEP=monitor "${MON_CMD[@]}" "$TOOLS/monitor_resources.py" \
            --out "$OUT/00_monitor" --root-pid $$ --interval "${MONITOR_INTERVAL:-0.5}" \
            --events-glob "$OUT/*/pytest/*_test_events.jsonl" &
        MON_PID=$!
    else
        echo "WARNING: monitor skipped (no psutil in $PYTHON and no uv to provide it)"
    fi
fi

# ----------------------------------------------------------------------------
# 1. Discover packages
# ----------------------------------------------------------------------------
if [[ -n "${PACKAGES:-}" ]]; then
    read -r -a PKGS <<< "$PACKAGES"
else
    PKGS=()
    for d in "$DISTRO_DIR"/packages/pynxtools*; do
        [[ -d "$d" ]] && PKGS+=("$(basename "$d")")
    done
fi
log "Baseline output: $OUT"
log "Distro: $DISTRO_DIR | Python: $PYTHON"
log "Packages (${#PKGS[@]}): ${PKGS[*]}"

# ----------------------------------------------------------------------------
# 2. Record the environment
# ----------------------------------------------------------------------------
log "Recording environment in $ENVDIR"
export BASELINE_PACKAGE="-" BASELINE_STEP="environment" BASELINE_CASE="-"
{
    echo "date:       $(date -Iseconds 2>/dev/null || date)"
    echo "host:       $(hostname)"
    echo "user:       $(id -un)"
    echo "uname:      $(uname -a)"
    [[ -f /etc/os-release ]] && grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
    command -v sw_vers >/dev/null && sw_vers
    echo "cpus:       $(getconf _NPROCESSORS_ONLN 2>/dev/null)"
    command -v lscpu >/dev/null && lscpu | grep -E 'Model name|^CPU\(s\)|Thread|MHz'
    command -v free  >/dev/null && free -m
    command -v sysctl >/dev/null && sysctl -n hw.memsize hw.model 2>/dev/null
    echo; echo "disk where the baseline is written:"; df -h "$OUT"
    echo; echo "uv: $(uv --version 2>/dev/null || echo 'not found')"
    echo "git: $(git --version)"
    command -v h5dump >/dev/null && echo "hdf5 tools: $(h5dump --version 2>&1 | head -1)"
} > "$ENVDIR/system.txt" 2>&1

"$PYTHON" - > "$ENVDIR/python.txt" 2>&1 <<'PY'
import sys, platform
print("executable:", sys.executable)
print("version:   ", sys.version.replace("\n", " "))
print("platform:  ", platform.platform())
try:
    import h5py, numpy
    print("h5py", h5py.__version__, "| HDF5", h5py.version.hdf5_version, "| numpy", numpy.__version__)
except Exception as exc:
    print("h5py/numpy:", exc)
PY

# installed packages (works in uv venvs that have no pip), incl. editable source paths
"$PYTHON" - > "$ENVDIR/installed_packages.txt" 2>&1 <<'PY'
import importlib.metadata as md, json
rows = []
for dist in md.distributions():
    name = dist.metadata["Name"]
    src = ""
    try:
        du = dist.read_text("direct_url.json")
        if du:
            d = json.loads(du)
            src = d.get("url", "") + (" (editable)" if d.get("dir_info", {}).get("editable") else "")
            if "vcs_info" in d:
                src += f" @ {d['vcs_info'].get('commit_id', '')}"
    except Exception:
        pass
    rows.append(f"{name}=={dist.version}" + (f"    # {src}" if src else ""))
print("\n".join(sorted(set(rows), key=str.lower)))
PY

# readers and NXDLs visible to the dataconverter
"$PYTHON" - > "$ENVDIR/readers.txt" 2>&1 <<'PY'
import importlib.metadata as md
from pynxtools.dataconverter.convert import get_names_of_all_readers, get_reader
for name in sorted(get_names_of_all_readers()):
    try:
        print(f"{name:20} {getattr(get_reader(name), 'supported_nxdls', '?')}")
    except Exception as exc:
        print(f"{name:20} ERROR {exc}")
print("\nentry points (group pynxtools.reader):")
eps = md.entry_points()
for ep in (eps.select(group="pynxtools.reader") if hasattr(eps, "select") else eps.get("pynxtools.reader", [])):
    print(f"  {ep.name} = {ep.value}  [{ep.dist.name if ep.dist else ''}]")
PY

# git state of the distro and of every package (plus diffs of uncommitted changes)
git_state() {  # $1 = label, $2 = repo dir
    local dir="$2"
    git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || { printf '%s\t%s\tNOT-A-GIT-REPO\n' "$1" "$dir"; return; }
    local dirty; dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" \
        "$(git -C "$dir" rev-parse HEAD)" \
        "$(git -C "$dir" describe --tags --always --dirty 2>/dev/null)" \
        "$(git -C "$dir" rev-parse --abbrev-ref HEAD)" \
        "$dirty" \
        "$(git -C "$dir" log -1 --format=%cI)" \
        "$(git -C "$dir" remote get-url origin 2>/dev/null)"
    if [[ "$dirty" != "0" ]]; then
        mkdir -p "$ENVDIR/uncommitted_changes"
        { git -C "$dir" status --porcelain; echo; git -C "$dir" diff HEAD; } \
            > "$ENVDIR/uncommitted_changes/$1.diff" 2>&1
    fi
}
{
    printf 'repo\tcommit\tdescribe\tbranch\tn_uncommitted_files\tcommit_date\tremote\n'
    git_state nomad-distro "$DISTRO_DIR"
    for d in "$DISTRO_DIR"/packages/*/; do git_state "$(basename "$d")" "$d"; done
    defs="$DISTRO_DIR/packages/pynxtools/src/pynxtools/definitions"
    [[ -e "$defs/.git" ]] && git_state nexus-definitions "$defs"
} > "$ENVDIR/git_state.tsv"
git -C "$DISTRO_DIR" submodule status --recursive > "$ENVDIR/git_submodules.txt" 2>&1
for f in pyproject.toml uv.lock nomad.yaml; do
    [[ -f "$DISTRO_DIR/$f" ]] && cp "$DISTRO_DIR/$f" "$ENVDIR/distro_$f"
done
# selected env vars only (never dump the full environment: it may hold secrets)
env | grep -E '^(NOMAD_[A-Z_]*(MODE|CONFIG)|UV_[A-Z_]*|VIRTUAL_ENV|PYTHON[A-Z_]*|OMP_NUM_THREADS|MKL_NUM_THREADS|HDF5_[A-Z_]*)=' \
    > "$ENVDIR/env_vars.txt" 2>/dev/null || true

# CLI entry point names changed over time (pynx vs. dataconverter/validate_nexus/read_nexus)
if command -v pynx >/dev/null 2>&1; then
    VALIDATE=(pynx validate); READ=(pynx read)
else
    VALIDATE=(validate_nexus); READ=(read_nexus -f)
fi
{ "${VALIDATE[@]}" --help; echo; dataconverter --help; } > "$ENVDIR/cli_help.txt" 2>&1

# ----------------------------------------------------------------------------
# 3. Per package: test suite, then individual conversions
# ----------------------------------------------------------------------------
for pkg in "${PKGS[@]}"; do
    PKG_DIR="$DISTRO_DIR/packages/$pkg"
    POUT="$OUT/$pkg"
    mkdir -p "$POUT/pytest" "$POUT/conversions"
    if [[ ! -d "$PKG_DIR" ]]; then
        log "[$pkg] SKIPPED: $PKG_DIR does not exist"; echo "missing package dir" > "$POUT/SKIPPED"; continue
    fi

    # --- 3a. full test suite --------------------------------------------------
    if [[ "${SKIP_PYTEST:-0}" != "1" ]]; then
        log "[$pkg] pytest (log: $pkg/pytest/${pkg}_pytest.log)"
        TEST_TARGET=(); [[ -d "$PKG_DIR/tests" ]] && TEST_TARGET=(tests)
        # shellcheck disable=SC2086
        ( cd "$PKG_DIR" && \
          BASELINE_PACKAGE="$pkg" BASELINE_STEP=pytest BASELINE_CASE="-" \
          BASELINE_RECORD_FILE="$POUT/pytest/${pkg}_conversions.jsonl" \
          BASELINE_EVENTS_FILE="$POUT/pytest/${pkg}_test_events.jsonl" \
          PYTHONPATH="$TOOLS${PYTHONPATH:+:$PYTHONPATH}" \
          "$PYTHON" "$TOOLS/measure.py" "$POUT/pytest/${pkg}_pytest_resources.json" "$STEP_TIMEOUT" -- \
            "$PYTHON" -m pytest "${TEST_TARGET[@]}" \
              -p baseline_recorder -p no:cacheprovider --continue-on-collection-errors \
              -v -rA --durations=0 --color=no \
              --basetemp="$POUT/pytest/tmp_files" \
              --junitxml="$POUT/pytest/${pkg}_junit.xml" \
              $PYTEST_ARGS \
        ) > "$POUT/pytest/${pkg}_pytest.log" 2>&1
        rc=$?
        log "[$pkg] pytest exit code $rc ($(tail -1 "$POUT/pytest/${pkg}_pytest.log"))"
    fi

    # --- 3b/3c. one fresh process per conversion ------------------------------
    RECORDS="$POUT/pytest/${pkg}_conversions.jsonl"
    [[ "${SKIP_REPLAY:-0}" == "1" ]] && RECORDS=/dev/null
    EXTRA="$TOOLS/extra_conversions.tsv"
    [[ "${SKIP_EXTRA:-0}" == "1" ]] && EXTRA=""
    mapfile -t CONV_DIRS < <("$PYTHON" "$TOOLS/prepare_conversions.py" \
        "$pkg" "$PKG_DIR" "$RECORDS" "$EXTRA" "$POUT/conversions")
    log "[$pkg] ${#CONV_DIRS[@]} conversion(s) to run"

    for cdir in "${CONV_DIRS[@]}"; do
        name="$(basename "$cdir")"          # <package>-<case>, also the prefix of every file
        F="$cdir/$name"
        export BASELINE_PACKAGE="$pkg" BASELINE_CASE="$name" BASELINE_STEP=convert
        if ! "$PYTHON" -c "import json,sys; sys.exit(0 if json.load(open('${F}_call.json'))['replayable'] else 1)"; then
            echo "NOT_REPLAYABLE" > "${F}_STATUS.txt"; log "[$pkg] $name: not replayable (see ${name}_call.json)"; continue
        fi
        ( cd "$cdir" && "$PYTHON" "$TOOLS/measure.py" "${F}_convert_resources.json" "$STEP_TIMEOUT" -- \
            "$PYTHON" "$TOOLS/replay_convert.py" "${F}_call.json" "${F}_output.nxs" ) > "${F}_convert.log" 2>&1
        crc=$?
        if [[ $crc -ne 0 || ! -s "${F}_output.nxs" ]]; then
            echo "CONVERT_FAILED" > "${F}_STATUS.txt"
        else
            BASELINE_STEP=validate "$PYTHON" "$TOOLS/measure.py" "${F}_validate_resources.json" "$STEP_TIMEOUT" -- \
                "${VALIDATE[@]}" "${F}_output.nxs" > "${F}_validate.log" 2>&1
            vrc=$?
            BASELINE_STEP=read "$PYTHON" "$TOOLS/measure.py" "${F}_read_resources.json" "$STEP_TIMEOUT" -- \
                "${READ[@]}" "${F}_output.nxs" > "${F}_read.log" 2>&1
            if [[ $vrc -eq 0 ]]; then echo "OK" > "${F}_STATUS.txt"; else echo "VALIDATION_FAILED" > "${F}_STATUS.txt"; fi
        fi
        log "[$pkg] $name: $(cat "${F}_STATUS.txt") ($("$PYTHON" -c "import json;r=json.load(open('${F}_convert_resources.json'));print(f\"{r['wall_s']} s, {r['peak_rss_mb']} MB\")" 2>/dev/null))"
    done

    # --- 3d. give the files the tests wrote a unique, package-prefixed name -----
    # (done after the replays, which may read inputs from these folders)
    if [[ -d "$POUT/pytest/tmp_files" ]]; then
        "$PYTHON" "$TOOLS/prefix_tmp_files.py" "$pkg" "$POUT/pytest/tmp_files" > "$POUT/pytest/${pkg}_tmp_files_renamed.tsv"
    fi
done

# ----------------------------------------------------------------------------
# 4. Summaries
# ----------------------------------------------------------------------------
export BASELINE_PACKAGE="-" BASELINE_STEP="summary" BASELINE_CASE="-"
if [[ -n "$MON_PID" ]]; then
    log "Stopping resource monitor (results in 00_monitor/)"
    stop_monitor
fi
log "Writing summary_tests.csv, summary_conversions.csv and MANIFEST.sha256"
"$PYTHON" "$TOOLS/summarize.py" "$OUT"
log "Done. Baseline is in: $OUT"
log "Archive it with:  tar -czf $(basename "$OUT").tar.gz -C $OUT_ROOT $(basename "$OUT")"
