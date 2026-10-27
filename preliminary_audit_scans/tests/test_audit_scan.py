"""Regression test: every planted bug in fixture_repo must be reported.

Run:  python tests/test_audit_scan.py      (or: pytest tests/)
Needs pint for the U08/U09/U10 checks.
"""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "audit_scan.py"
FIXTURE = HERE / "fixture_repo"

# rule -> (file suffix, line number or a marker text found on that line)
EXPECTED = {
    "U01": ("nested.json", 9),     # free text in @units
    "U05": ("reader.py", "# U06 + U05"),
    "U06": ("reader.py", "# U06 + U05"),
    "U07": ("config.json", 2),
    "U08": ("config.json", 3),     # 'c/s' fallback = speed_of_light/second
    "U09": ("reader.py", "# U09 + U10"),
    "U10": ("config.json", 5),     # wavelength in eV
    "U11": ("reader.py", "# U11"),
    "S01": ("reader.py", "# S01"),
    "S02": ("reader.py", "# S02"),
    "S03": ("reader.py", "# S03"),
    "S04": ("reader.py", "# S04"),
    "S05": ("reader.py", "# S05"),
    "S06": ("reader.py", "# S06 medium"),
    "A01": ("reader.py", "# A01 + N01"),
    "A04": ("reader.py", "# A04"),
    "N01": ("reader.py", "# A01 + N01"),
    "N07": ("reader.py", "# N07"),
    "K01": ("reader.py", "# K01"),
    "C04": ("config.json", 8),
    "C06": ("config.json", 6),
    "C07": ("config.json", 3),
    "E02": ("reader.py", "# E02"),
}


def resolve_line(suffix, where):
    if isinstance(where, int):
        return where
    src = next(FIXTURE.rglob(suffix)).read_text().splitlines()
    return next(i for i, l in enumerate(src, 1) if where in l)


def run(profile):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "f.csv"
        subprocess.run([sys.executable, str(SCRIPT), str(FIXTURE), "--profile", profile,
                        "--out", str(out)], check=True, capture_output=True)
        return list(csv.DictReader(open(out)))


def check(rows, expected):
    missing = []
    for rule, (suffix, where) in expected.items():
        line = resolve_line(suffix, where)
        if not any(r["rule"] == rule and r["file"].endswith(suffix)
                   and (line is None or int(r["line"]) == line) for r in rows):
            missing.append(f"{rule} @ {suffix}:{line}")
    return missing


def test_em_profile_reports_everything():
    assert check(run("pynxtools-em"), EXPECTED) == []


def test_charge_C_is_not_a_trap():
    rows = run("pynxtools-em")
    charge = resolve_line("reader.py", "fine: C is a charge here")
    temp = resolve_line("reader.py", "# U08 high + U10")
    u08 = {int(r["line"]): r["severity"] for r in rows if r["rule"] == "U08"}
    assert charge not in u08 and u08.get(temp) == "high"


def test_spm_profile_treats_raw_paths_as_lookups():
    rows = run("pynxtools-spm")
    assert not any(r["rule"] == "U01" and "/Bias/unit" in r["message"] for r in rows)
    assert any(r["rule"] == "U01" and "unit comes from raw_path" in r["message"] for r in rows)


if __name__ == "__main__":
    fails = check(run("pynxtools-em"), EXPECTED)
    test_charge_C_is_not_a_trap()
    test_spm_profile_treats_raw_paths_as_lookups()
    print("missing:", fails) if fails else print("all planted findings reported")
    sys.exit(1 if fails else 0)
