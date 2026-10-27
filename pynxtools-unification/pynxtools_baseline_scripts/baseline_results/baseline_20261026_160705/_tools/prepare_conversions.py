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
        # optional 7th column: extra convert() kwargs, e.g. "skip_verify=1 append=0"
        extra_kwargs = {}
        for item in (cols[6].split() if len(cols) > 6 else []):
            if "=" in item:
                k, v = item.split("=", 1)
                extra_kwargs[k] = {"1": True, "true": True, "True": True,
                                   "0": False, "false": False, "False": False}.get(v, v)
        files, missing = [], []
        for p in patterns.split():
            expanded = os.path.join(pkg_dir, os.path.expandvars(os.path.expanduser(p)))
            hits = sorted(f for f in glob.glob(expanded, recursive=True) if os.path.isfile(f))
            files += hits
            if not hits:
                missing.append(f"{p} -> {expanded}")
        call = {"input_file": files, "reader": reader, "nxdl": nxdl,
                "ignore_undocumented": ignore_undoc.strip() in ("1", "true", "True"),
                **extra_kwargs}
        # every pattern must match something; otherwise the reader would silently
        # convert only the remaining files (e.g. just the YAMLs)
        for m in missing:
            print(f"[extra_conversions] {pkg_name}/{case}: NO FILE MATCHES {m}", file=sys.stderr)
        emit(f"extra_{case}", {"source": "extra_tsv", "test_id": f"extra::{case}",
                               "replayable": bool(files) and not missing,
                               "missing_inputs": missing, "call": call})
