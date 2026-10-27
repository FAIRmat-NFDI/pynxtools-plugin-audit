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
