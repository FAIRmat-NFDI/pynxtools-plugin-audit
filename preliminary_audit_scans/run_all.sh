#!/usr/bin/env bash
# Scan every pynxtools repo in nomad-distro-dev/packages, one CSV per repo.
# Run from anywhere:   bash ~/nomad-distro-dev/audit_scans/run_all.sh [extra audit_scan options]
# e.g.                 bash run_all.sh --min-severity medium
# Output:              ~/nomad-distro-dev/audit_scans/results/<repo>.csv
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../nomad-distro-dev/audit_scans
DISTRO="$(dirname "$HERE")"                               # .../nomad-distro-dev
PY="$DISTRO/.venv/bin/python"                             # distro venv (has pint)
[ -x "$PY" ] || PY="python3"
OUT="$HERE/results"
mkdir -p "$OUT"

REPOS=(pynxtools pynxtools-xps pynxtools-ellips pynxtools-em pynxtools-igor pynxtools-mpes
       pynxtools-raman pynxtools-spm pynxtools-xas pynxtools-xrd readers-xrd pynxtools-microstructure)

for p in "${REPOS[@]}"; do
  if [ ! -d "$DISTRO/packages/$p" ]; then
    echo "skip $p (not in packages/)"
    continue
  fi
  "$PY" "$HERE/audit_scan.py" "$DISTRO/packages/$p" --out "$OUT/$p.csv" "$@"
  echo
done
echo "results in $OUT"
