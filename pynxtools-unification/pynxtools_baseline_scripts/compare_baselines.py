#!/usr/bin/env python3
"""
compare_baselines.py - compare two folders written by run_baseline.sh
(typically: before vs. after the pynxtools architecture unification).

Usage (run it with the distro venv's python, it needs h5py + numpy):
  python compare_baselines.py OLD_BASELINE NEW_BASELINE [--out DIR]
         [--time-tol 0.15] [--rss-tol 0.10] [--min-time-s 0.5] [--min-rss-mb 20]
         [--rtol 1e-9] [--atol 0] [--ignore REGEX ...] [--fail-on-resources]

What it compares
  1. Environment   machine, Python, git commits of every package, installed package versions
  2. Test suites   per package counts and per-test outcome changes (from junit.xml)
  3. Conversions   matched by package + test id + reader + NXDL:
                   status, new / missing conversions, warnings and errors
  4. File content  every pair of *_output.nxs: groups, fields, attributes, dtypes,
                   shapes and values (h5py). Volatile items (file_time, versions, ...)
                   are reported separately and never count as a difference.
                   Also: new/removed WARNING/ERROR messages in convert.log and
                   validate.log, and a normalised diff of the read.log annotator dump.
  5. Resources     wall time, CPU time, peak RAM per conversion and per test suite
                   (and per step from the resource monitor, if both runs have it),
                   flagged when the change is above the tolerance AND the minimum
                   absolute change.

Output (in --out, default ./compare_<old>__vs__<new>/)
  report.md                   human-readable report, start here
  tests_comparison.csv        one row per test id
  conversions_comparison.csv  one row per conversion (status, content, resources)
  suites_resources.csv        per package test-suite resources
  monitor_steps_comparison.csv  (only if both baselines have 00_monitor/)
  packages_diff.csv           installed package versions that differ
  content_diffs/<package>/<conversion>/   <conversion>_h5_diff.txt, _messages.diff, _read_log.diff

Exit code: 0 = no regressions, 1 = regressions found (resource changes only count
with --fail-on-resources), 2 = usage error.
"""

import argparse
import csv
import difflib
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

try:
    import h5py
    import numpy as np
except ImportError:
    h5py = None

DEFAULT_IGNORE = [
    # root attributes written by pynxtools that change on every run / version
    r"^/@(file_time|file_update_time|file_name|h5py_version|HDF5_Version|creator_version|NeXus_release|NeXus_repository)$",
    # any "version" attribute or *_version field (program / library versions)
    r"/@version$",
    r"(^|/)[^/]*_version$",
    # run-time profiling written by some readers (e.g. em, apm)
    r"(^|/)profiling(/|$)",
    r"_elapsed_time$",
]
VOLATILE_LINE = re.compile(
    r"(file_time|file_update_time|file_name|h5py_version|HDF5_Version|creator_version|NeXus_release|NeXus_repository|@version)"
)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)?")
LEVEL_MSG = re.compile(r"\b(WARNING|ERROR)\b:?\s*(.*)")
# paths that differ between runs or machines, and the placeholders written by sanitize_baseline.py,
# so a raw run and a sanitized (public) copy compare equal
BASELINE_DIR = re.compile(r"[^\s'\"`]*baseline_\d{8}_\d{6}")
HOME_DIR = re.compile(r"(/home/[^/\s'\"`]+|/Users/[^/\s'\"`]+|\$HOME)(?=/|\b|$)")


def normalise_paths(text):
    text = BASELINE_DIR.sub("<BASELINE>", text)
    text = HOME_DIR.sub("<HOME>", text)
    return text.replace("$USER", "<USER>").replace("$HOSTNAME", "<HOST>")


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def cfile(d, suffix, legacy=None):
    """File of a conversion folder: <folder>_<suffix> (e.g. pynxtools-xps-vms_regular_output.nxs).
    Falls back to the old unprefixed name for baselines made with an earlier script version."""
    p = os.path.join(d, f"{os.path.basename(d)}_{suffix}")
    if not os.path.exists(p) and legacy and os.path.exists(os.path.join(d, legacy)):
        return os.path.join(d, legacy)
    return p


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def read_csv(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="") as fh:
        if not rows:
            fh.write("no rows\n")
            return
        fields = fields or list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        w.writerows(rows)


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def rel_change(old, new):
    o, n = fnum(old), fnum(new)
    if o is None or n is None:
        return None
    if o == 0:
        return 0.0 if n == 0 else float("inf")
    return (n - o) / o


def flag_resource(old, new, tol, min_abs):
    """'+' worse, '-' better, '' within noise / not comparable."""
    o, n = fnum(old), fnum(new)
    if o is None or n is None:
        return ""
    if abs(n - o) < min_abs:
        return ""
    r = rel_change(o, n)
    if r is None or abs(r) <= tol:
        return ""
    return "+" if n > o else "-"


def pct(r):
    if r is None:
        return ""
    if r == float("inf"):
        return "inf"
    return f"{r * 100:+.1f}%"


def normalise_line(line, root):
    line = re.sub(r"[^\s'\"`]*/(conversions|tmp_files)/[^\s'\"`]*", "<PATH>", line)
    line = line.replace(root, "<BASELINE>")
    line = normalise_paths(line)
    line = TIMESTAMP.sub("<TIME>", line)
    return line.rstrip()


def messages(path, root):
    """Multiset of normalised WARNING/ERROR messages of a log file."""
    c = Counter()
    if not os.path.isfile(path):
        return c
    for line in open(path, errors="replace"):
        m = LEVEL_MSG.search(line)
        if m:
            c[f"{m.group(1)}: {normalise_line(m.group(2), root)}"] += 1
    return c


# ----------------------------------------------------------------------------
# 1. environment
# ----------------------------------------------------------------------------
def parse_packages(base):
    out = {}
    path = os.path.join(base, "00_environment", "installed_packages.txt")
    if os.path.isfile(path):
        for line in open(path):
            m = re.match(r"([^=\s]+)==(\S+)", line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    return out


def parse_git(base):
    rows = read_csv_tsv(os.path.join(base, "00_environment", "git_state.tsv"))
    return {r.get("repo"): r for r in rows}


def read_csv_tsv(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def first_line_with(path, key):
    if not os.path.isfile(path):
        return ""
    for line in open(path, errors="replace"):
        if line.strip().startswith(key):
            return line.split(":", 1)[-1].strip()
    return ""


# ----------------------------------------------------------------------------
# 2. tests
# ----------------------------------------------------------------------------
def junit_outcomes(base):
    res = {}
    for path in glob.glob(os.path.join(base, "*", "pytest", "*junit.xml")):
        pkg = path.split(os.sep)[-3]
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for tc in root.iter("testcase"):
            tid = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            outcome = "passed"
            for child in tc:
                if child.tag in ("failure", "error", "skipped"):
                    outcome = {"failure": "failed"}.get(child.tag, child.tag)
            res[(pkg, tid)] = {"outcome": outcome, "time": tc.get("time", "")}
    return res


# ----------------------------------------------------------------------------
# 3. conversions
# ----------------------------------------------------------------------------
def conversions(base):
    """{match key: info} with an occurrence counter for repeated identical keys."""
    summary = {(r["package"], r["conversion"]): r for r in read_csv(os.path.join(base, "summary_conversions.csv"))}
    seen = Counter()
    out = {}
    for d in sorted(glob.glob(os.path.join(base, "*", "conversions", "*"))):
        pkg, name = d.split(os.sep)[-3], os.path.basename(d)
        rec = load_json(cfile(d, "call.json", "call.json"))
        call = rec.get("call", {})
        k = (pkg, rec.get("test_id", name), call.get("reader", ""), call.get("nxdl", ""))
        seen[k] += 1
        key = k + (seen[k],)
        status_file = cfile(d, "STATUS.txt", "STATUS")
        out[key] = {
            "dir": d, "name": name,
            "status": open(status_file).read().strip() if os.path.isfile(status_file) else "",
            "summary": summary.get((pkg, name), {}),
        }
    return out


# ----------------------------------------------------------------------------
# 4. HDF5 content
# ----------------------------------------------------------------------------
def h5_items(path):
    """{path: ("group"|"dataset", h5obj)} plus {path/@attr: value}"""
    nodes, attrs = {}, {}
    f = h5py.File(path, "r")

    def add_attrs(p, obj):
        for k, v in obj.attrs.items():
            attrs[f"{p.rstrip('/')}/@{k}" if p != "/" else f"/@{k}"] = v

    add_attrs("/", f)

    def visit(name, obj):
        p = "/" + name
        nodes[p] = ("dataset" if isinstance(obj, h5py.Dataset) else "group", obj)
        add_attrs(p, obj)

    f.visititems(visit)
    return f, nodes, attrs


def to_comparable(v):
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str):
        return normalise_paths(v)
    if isinstance(v, np.ndarray) and v.dtype.kind in "OSU":
        return np.array([to_comparable(x) for x in v.ravel()], dtype=object).reshape(v.shape)
    return v


def values_equal(a, b, rtol, atol):
    a, b = to_comparable(a), to_comparable(b)
    try:
        aa, bb = np.asarray(a), np.asarray(b)
        if aa.shape != bb.shape:
            return False, f"shape {aa.shape} -> {bb.shape}"
        if aa.dtype.kind in "fc" or bb.dtype.kind in "fc":
            if aa.dtype.kind in "biufc" and bb.dtype.kind in "biufc":
                ok = np.allclose(aa, bb, rtol=rtol, atol=atol, equal_nan=True)
                if not ok:
                    diff = np.nanmax(np.abs(aa.astype(float) - bb.astype(float))) if aa.size else 0
                    return False, f"max abs diff {diff:.6g}"
                return True, ""
        if aa.dtype.names or bb.dtype.names:  # compound
            return (aa.tobytes() == bb.tobytes()), "compound values differ"
        ok = bool(np.array_equal(aa, bb))
        if not ok:
            sa, sb = repr(a), repr(b)
            return False, f"{sa[:120]} -> {sb[:120]}"
        return True, ""
    except Exception as exc:  # unusual types: fall back to repr
        return repr(a) == repr(b), f"compare error: {exc}"


def compare_h5(old, new, ignore, rtol, atol):
    """returns (real_diffs, volatile_diffs) as lists of strings"""
    real, volatile = [], []
    is_volatile = lambda p: any(r.search(p) for r in ignore)
    fo, no, ao = h5_items(old)
    fn, nn, an = h5_items(new)
    try:
        for p in sorted(set(no) | set(nn)):
            tgt = volatile if is_volatile(p) else real
            if p not in nn:
                tgt.append(f"REMOVED {no[p][0]} {p}")
                continue
            if p not in no:
                tgt.append(f"ADDED   {nn[p][0]} {p}")
                continue
            ko, ob = no[p]
            kn, nb = nn[p]
            if ko != kn:
                tgt.append(f"KIND    {p}: {ko} -> {kn}")
                continue
            if ko == "dataset":
                if ob.dtype.kind != nb.dtype.kind:
                    tgt.append(f"DTYPE   {p}: {ob.dtype} -> {nb.dtype}")
                if ob.shape != nb.shape:
                    tgt.append(f"SHAPE   {p}: {ob.shape} -> {nb.shape}")
                    continue
                ok, why = values_equal(ob[()], nb[()], rtol, atol)
                if not ok:
                    tgt.append(f"VALUE   {p}: {why}")
        for p in sorted(set(ao) | set(an)):
            tgt = volatile if is_volatile(p) else real
            if p not in an:
                tgt.append(f"REMOVED attr {p}")
            elif p not in ao:
                tgt.append(f"ADDED   attr {p}")
            else:
                ok, why = values_equal(ao[p], an[p], rtol, atol)
                if not ok:
                    tgt.append(f"VALUE   attr {p}: {why}")
    finally:
        fo.close()
        fn.close()
    return real, volatile


def read_log_diff(old_path, new_path, old_root, new_root):
    def lines(p, root):
        if not os.path.isfile(p):
            return []
        return [normalise_line(l, root) for l in open(p, errors="replace") if not VOLATILE_LINE.search(l)]

    return list(difflib.unified_diff(lines(old_path, old_root), lines(new_path, new_root),
                                     "old/read.log", "new/read.log", n=1, lineterm=""))


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--out")
    ap.add_argument("--time-tol", type=float, default=0.15, help="relative wall/CPU change tolerated (0.15 = 15%%)")
    ap.add_argument("--rss-tol", type=float, default=0.10, help="relative peak-RAM change tolerated")
    ap.add_argument("--min-time-s", type=float, default=0.5, help="ignore time changes smaller than this")
    ap.add_argument("--min-rss-mb", type=float, default=20, help="ignore RAM changes smaller than this")
    ap.add_argument("--rtol", type=float, default=1e-9, help="relative tolerance for float values")
    ap.add_argument("--atol", type=float, default=0.0, help="absolute tolerance for float values")
    ap.add_argument("--ignore", action="append", default=[], help="extra regex of HDF5 paths to treat as volatile")
    ap.add_argument("--fail-on-resources", action="store_true")
    a = ap.parse_args()

    old, new = os.path.abspath(a.old), os.path.abspath(a.new)
    for d in (old, new):
        if not os.path.isfile(os.path.join(d, "summary_conversions.csv")):
            print(f"{d} does not look like a run_baseline.sh output folder", file=sys.stderr)
            return 2
    out = os.path.abspath(a.out or f"compare_{os.path.basename(old)}__vs__{os.path.basename(new)}")
    os.makedirs(out, exist_ok=True)
    ignore = [re.compile(r) for r in DEFAULT_IGNORE + a.ignore]
    if h5py is None:
        print("WARNING: h5py/numpy not importable, NeXus content will not be compared", file=sys.stderr)

    rep = []  # markdown lines
    regressions = Counter()
    resource_flags = Counter()

    # ---- 1. environment --------------------------------------------------------
    rep += [f"# Baseline comparison", "", f"- old: `{old}`", f"- new: `{new}`", ""]
    rep += ["## 1. Environment", "", "| item | old | new |", "|---|---|---|"]
    so, sn = (os.path.join(b, "00_environment", "system.txt") for b in (old, new))
    po, pn = (os.path.join(b, "00_environment", "python.txt") for b in (old, new))
    # the machine is identified by CPU model, CPU count and RAM, not by host name: host and user
    # are no longer recorded, and sanitized copies show $HOSTNAME
    machine_keys = ("CPU model", "CPUs", "RAM total (MB)")
    for label, fo_, fn_, key in [("host", so, sn, "host"), ("OS", so, sn, "PRETTY_NAME"),
                                 ("CPU model", so, sn, "Model name"), ("CPUs", so, sn, "cpus"),
                                 ("RAM total (MB)", so, sn, "Mem"), ("Python", po, pn, "version")]:
        vo, vn = first_line_with(fo_, key), first_line_with(fn_, key)
        if key == "Mem":
            vo, vn = (v.split()[0] if v else "" for v in (vo, vn))
        rep.append(f"| {label} | {vo or '–'} | {vn or '–'} |" + (" ⚠️ differs" if vo != vn and label in machine_keys else ""))
    if any(first_line_with(so, k) != first_line_with(sn, k) for k in ("Model name", "cpus")):
        rep += ["", "> ⚠️ Different machines: resource numbers are not directly comparable."]
    go, gn = parse_git(old), parse_git(new)
    rep += ["", "**Git state**", "", "| repo | old | new |", "|---|---|---|"]
    for repo in sorted(set(go) | set(gn)):
        o, n = go.get(repo, {}), gn.get(repo, {})
        mark = lambda r: (r.get("describe") or r.get("commit", "")[:10] or "–") + \
            (f" ({r.get('n_uncommitted_files')} uncommitted)" if r.get("n_uncommitted_files", "0") not in ("0", "") else "")
        rep.append(f"| {repo} | {mark(o)} | {mark(n)} |")
    pko, pkn = parse_packages(old), parse_packages(new)
    pkg_rows = [{"package": k, "old": pko.get(k, ""), "new": pkn.get(k, "")}
                for k in sorted(set(pko) | set(pkn)) if pko.get(k) != pkn.get(k)]
    write_csv(os.path.join(out, "packages_diff.csv"), pkg_rows, ["package", "old", "new"])
    rep += ["", f"Installed packages with a different version (or added/removed): **{len(pkg_rows)}** "
                f"(see `packages_diff.csv`)", ""]

    # ---- 2. tests --------------------------------------------------------------
    jo, jn = junit_outcomes(old), junit_outcomes(new)
    test_rows, transitions = [], Counter()
    for k in sorted(set(jo) | set(jn)):
        o, n = jo.get(k, {}).get("outcome", "missing"), jn.get(k, {}).get("outcome", "missing")
        change = "" if o == n else f"{o} -> {n}"
        if change:
            transitions[change] += 1
            if o == "passed" and n in ("failed", "error", "missing"):
                regressions["tests"] += 1
        test_rows.append({"package": k[0], "test_id": k[1], "old": o, "new": n, "change": change,
                          "old_time_s": jo.get(k, {}).get("time", ""), "new_time_s": jn.get(k, {}).get("time", "")})
    write_csv(os.path.join(out, "tests_comparison.csv"), test_rows)
    sto = {r["package"]: r for r in read_csv(os.path.join(old, "summary_tests.csv"))}
    stn = {r["package"]: r for r in read_csv(os.path.join(new, "summary_tests.csv"))}
    rep += ["## 2. Test suites", "", "| package | old pass/fail/err/skip | new pass/fail/err/skip |", "|---|---|---|"]
    fmt = lambda r: "/".join(r.get(k, "–") for k in ("passed", "failed", "errors", "skipped")) if r else "missing"
    for p in sorted(set(sto) | set(stn)):
        rep.append(f"| {p} | {fmt(sto.get(p))} | {fmt(stn.get(p))} |")
    rep += ["", "Outcome changes: " + (", ".join(f"{v}× {k}" for k, v in transitions.most_common()) or "none"), ""]
    bad = [r for r in test_rows if r["old"] == "passed" and r["new"] in ("failed", "error", "missing")]
    if bad:
        rep += ["Tests that passed before and don't now:", ""] + [f"- `{r['package']}` {r['test_id']} ({r['new']})" for r in bad[:50]]
        rep += ["- …"] if len(bad) > 50 else []
        rep.append("")

    # ---- 3/4/5. conversions ------------------------------------------------------
    co, cn = conversions(old), conversions(new)
    conv_rows = []
    for key in sorted(set(co) | set(cn), key=lambda k: tuple(map(str, k))):
        pkg, test_id, reader, nxdl, occ = key
        o, n = co.get(key), cn.get(key)
        row = {"package": pkg, "test_id": test_id, "reader": reader, "nxdl": nxdl, "occurrence": occ,
               "old_dir": o["name"] if o else "", "new_dir": n["name"] if n else "",
               "old_status": o["status"] if o else "MISSING", "new_status": n["status"] if n else "MISSING"}
        if o and o["status"] == "OK" and (not n or n["status"] != "OK"):
            regressions["conversions"] += 1
        row["status_change"] = "" if row["old_status"] == row["new_status"] else f"{row['old_status']} -> {row['new_status']}"
        so_, sn_ = (o or {}).get("summary", {}), (n or {}).get("summary", {})
        # resources
        for metric, tol, mn in (("wall_s", a.time_tol, a.min_time_s), ("user_cpu_s", a.time_tol, a.min_time_s),
                                ("peak_rss_mb", a.rss_tol, a.min_rss_mb), ("output_mb", a.rss_tol, 0.01)):
            row[f"old_{metric}"], row[f"new_{metric}"] = so_.get(metric, ""), sn_.get(metric, "")
            row[f"{metric}_change"] = pct(rel_change(so_.get(metric), sn_.get(metric)))
            fl = flag_resource(so_.get(metric), sn_.get(metric), tol, mn)
            row[f"{metric}_flag"] = {"+": "WORSE", "-": "better"}.get(fl, "")
            if fl == "+" and metric != "output_mb":
                resource_flags[metric] += 1
        # content
        row.update(h5_real_diffs="", h5_volatile_diffs="", new_messages="", removed_messages="", read_log_changed_lines="")
        onxs = cfile(o["dir"], "output.nxs", "output.nxs") if o else ""
        nnxs = cfile(n["dir"], "output.nxs", "output.nxs") if n else ""
        if o and n and os.path.isfile(onxs) and os.path.isfile(nnxs):
            ddir = os.path.join(out, "content_diffs", pkg, n["name"])
            os.makedirs(ddir, exist_ok=True)
            if h5py is not None:
                try:
                    real, vol = compare_h5(onxs, nnxs,
                                           ignore, a.rtol, a.atol)
                except Exception as exc:
                    real, vol = [f"could not compare: {exc}"], []
                row["h5_real_diffs"], row["h5_volatile_diffs"] = len(real), len(vol)
                if real:
                    regressions["content"] += 1
                with open(os.path.join(ddir, f"{n['name']}_h5_diff.txt"), "w") as fh:
                    fh.write("# real differences\n" + "\n".join(real) + "\n\n# volatile (ignored)\n" + "\n".join(vol) + "\n")
            mo = messages(cfile(o["dir"], "convert.log", "convert.log"), old) + messages(cfile(o["dir"], "validate.log", "validate.log"), old)
            mn_ = messages(cfile(n["dir"], "convert.log", "convert.log"), new) + messages(cfile(n["dir"], "validate.log", "validate.log"), new)
            added, removed = mn_ - mo, mo - mn_
            row["new_messages"], row["removed_messages"] = sum(added.values()), sum(removed.values())
            if any(m.startswith("ERROR") for m in added):
                regressions["new_errors"] += 1
            with open(os.path.join(ddir, f"{n['name']}_messages.diff"), "w") as fh:
                fh.write("# messages only in NEW (convert.log + validate.log)\n")
                fh.writelines(f"+ {m}  (x{c})\n" for m, c in sorted(added.items()))
                fh.write("\n# messages only in OLD\n")
                fh.writelines(f"- {m}  (x{c})\n" for m, c in sorted(removed.items()))
            diff = read_log_diff(cfile(o["dir"], "read.log", "read.log"), cfile(n["dir"], "read.log", "read.log"), old, new)
            row["read_log_changed_lines"] = sum(1 for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---")))
            with open(os.path.join(ddir, f"{n['name']}_read_log.diff"), "w") as fh:
                fh.write("\n".join(diff) + "\n")
        conv_rows.append(row)
    write_csv(os.path.join(out, "conversions_comparison.csv"), conv_rows)

    n_both_ok = sum(1 for r in conv_rows if r["old_status"] == "OK" and r["new_status"] == "OK")
    n_identical = sum(1 for r in conv_rows if r["h5_real_diffs"] == 0)
    rep += ["## 3. Conversions", "",
            f"- matched conversions: {len(conv_rows)} (old {len(co)}, new {len(cn)})",
            f"- OK in both: {n_both_ok}",
            f"- OK before, not OK / missing now: **{regressions['conversions']}**",
            f"- status changes: " + (", ".join(f"{v}× {k}" for k, v in Counter(r['status_change'] for r in conv_rows if r['status_change']).most_common()) or "none"),
            "", "## 4. File content", "",
            f"- identical NeXus content (ignoring volatile items): **{n_identical}** of {sum(1 for r in conv_rows if r['h5_real_diffs'] != '')} compared",
            f"- with real content differences: **{regressions['content']}**",
            f"- with new ERROR messages in convert/validate logs: **{regressions['new_errors']}**", ""]
    diffs = [r for r in conv_rows if r["h5_real_diffs"] not in ("", 0)]
    if diffs:
        rep += ["| package | conversion | real diffs | volatile | new msgs | details |", "|---|---|---|---|---|---|"]
        for r in diffs[:100]:
            rep.append(f"| {r['package']} | {r['test_id']} | {r['h5_real_diffs']} | {r['h5_volatile_diffs']} | "
                       f"{r['new_messages']} | `content_diffs/{r['package']}/{r['new_dir']}/` |")
        rep.append("")
    rep += ["Note: `read_log_changed_lines` in the CSV also changes when the annotator's output format changes, "
            "so treat the HDF5 comparison as the authoritative content check.", ""]

    # resources: conversions
    rep += ["## 5. Resources", "",
            f"Tolerances: time ±{a.time_tol:.0%} (and ≥{a.min_time_s} s), RAM ±{a.rss_tol:.0%} (and ≥{a.min_rss_mb} MB).", "",
            "**Per conversion** (flagged WORSE above tolerance)", "",
            "| package | conversion | wall old→new | CPU old→new | peak RAM MB old→new |", "|---|---|---|---|---|"]
    flagged = [r for r in conv_rows if "WORSE" in (r.get("wall_s_flag"), r.get("user_cpu_s_flag"), r.get("peak_rss_mb_flag"))]
    for r in flagged[:100]:
        f = lambda m: f"{r[f'old_{m}']}→{r[f'new_{m}']} ({r[f'{m}_change']}){' ⚠️' if r[f'{m}_flag'] == 'WORSE' else ''}"
        rep.append(f"| {r['package']} | {r['test_id']} | {f('wall_s')} | {f('user_cpu_s')} | {f('peak_rss_mb')} |")
    if not flagged:
        rep.append("| – | no conversion above tolerance | | | |")
    tot = lambda rows, k: sum(fnum(r.get(k)) or 0 for r in rows)
    both = [r for r in conv_rows if r["old_status"] == "OK" and r["new_status"] == "OK"]
    rep += ["", f"Totals over conversions OK in both runs: wall {tot(both, 'old_wall_s'):.1f} s → {tot(both, 'new_wall_s'):.1f} s, "
                f"CPU {tot(both, 'old_user_cpu_s'):.1f} s → {tot(both, 'new_user_cpu_s'):.1f} s, "
                f"max peak RAM {max([fnum(r['old_peak_rss_mb']) or 0 for r in both] or [0]):.0f} MB → "
                f"{max([fnum(r['new_peak_rss_mb']) or 0 for r in both] or [0]):.0f} MB", ""]

    # resources: test suites
    suite_rows = []
    rep += ["**Per test suite**", "", "| package | wall s old→new | peak RAM MB old→new |", "|---|---|---|"]
    for p in sorted(set(sto) | set(stn)):
        o, n = sto.get(p, {}), stn.get(p, {})
        r = {"package": p}
        for m, tol, mn in (("wall_s", a.time_tol, a.min_time_s), ("peak_rss_mb", a.rss_tol, a.min_rss_mb)):
            r[f"old_{m}"], r[f"new_{m}"] = o.get(m, ""), n.get(m, "")
            r[f"{m}_change"] = pct(rel_change(o.get(m), n.get(m)))
            r[f"{m}_flag"] = {"+": "WORSE", "-": "better"}.get(flag_resource(o.get(m), n.get(m), tol, mn), "")
        suite_rows.append(r)
        rep.append(f"| {p} | {r['old_wall_s']}→{r['new_wall_s']} ({r['wall_s_change']}) | "
                   f"{r['old_peak_rss_mb']}→{r['new_peak_rss_mb']} ({r['peak_rss_mb_change']}) |")
    write_csv(os.path.join(out, "suites_resources.csv"), suite_rows)
    rep.append("")

    # resources: monitor
    mo_rows = read_csv(os.path.join(old, "00_monitor", "summary_by_step.csv"))
    mn_rows = read_csv(os.path.join(new, "00_monitor", "summary_by_step.csv"))
    if mo_rows and mn_rows:
        key = lambda r: (r.get("package"), r.get("step"), re.sub(r"^\d+_", "", r.get("case", "")))
        mo_d, mn_d = {key(r): r for r in mo_rows}, {key(r): r for r in mn_rows}
        mrows = []
        for k in sorted(set(mo_d) | set(mn_d), key=lambda k: tuple(map(str, k))):
            o, n = mo_d.get(k, {}), mn_d.get(k, {})
            r = {"package": k[0], "step": k[1], "case": k[2]}
            for m in ("duration_s", "peak_group_rss_mb", "peak_single_process_rss_mb", "cpu_s", "n_processes", "max_threads"):
                r[f"old_{m}"], r[f"new_{m}"] = o.get(m, ""), n.get(m, "")
                r[f"{m}_change"] = pct(rel_change(o.get(m), n.get(m)))
            mrows.append(r)
        write_csv(os.path.join(out, "monitor_steps_comparison.csv"), mrows)
        rep += ["**Per step from the resource monitor**: see `monitor_steps_comparison.csv` "
                "(group RAM = all processes of a step together).", ""]

    # ---- verdict ----------------------------------------------------------------
    n_reg = sum(regressions.values())
    rep[1:1] = ["", f"**Verdict:** {'❌ ' + str(n_reg) + ' regression(s)' if n_reg else '✅ no functional regressions'}"
                    f" — tests {regressions['tests']}, conversions {regressions['conversions']}, "
                    f"content {regressions['content']}, new errors {regressions['new_errors']}; "
                    f"resource flags: {dict(resource_flags) or 'none'}"]
    with open(os.path.join(out, "report.md"), "w") as fh:
        fh.write("\n".join(rep) + "\n")
    print(rep[2])
    print(f"Report: {os.path.join(out, 'report.md')}")
    if n_reg or (a.fail_on_resources and resource_flags):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
