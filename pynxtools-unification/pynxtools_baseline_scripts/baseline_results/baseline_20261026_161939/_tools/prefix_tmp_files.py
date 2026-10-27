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
