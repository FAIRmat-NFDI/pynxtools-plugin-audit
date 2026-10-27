#!/usr/bin/env python3
"""
audit_scan.py - static scanner that flags suspicious behaviour in pynxtools and
its plugins: hard-coded values, unit problems, silent fallbacks, data-changing
operations, swallowed exceptions, copy-pasted logic and unsafe file handling.

It does NOT prove a bug. Every finding is a pointer for manual review.

Each repository is scanned with a *profile*: profiles/_base.toml plus the
plugin's own profiles/<name>.toml (auto-detected from pyproject.toml).
Profiles say which files to scan, how the plugin's config files encode lookups,
which units/constants are normal for the technique, and which rules are noise.

Usage (Python >= 3.11, or 3.9/3.10 with `pip install tomli`):
    python audit_scan.py path/to/pynxtools-xps            # one repo
    python audit_scan.py --distro path/to/packages        # every repo in a folder
    python audit_scan.py REPO --profile pynxtools-em      # force a profile
    python audit_scan.py REPO --min-severity medium --disable D05,A03
    python audit_scan.py REPO --inventory inventory.csv   # annotate a ledger
    python audit_scan.py --list-rules | --list-profiles

Units are checked with pint. The registry is, in order: --unit-registry FILE,
pynxtools' own units/default_en.txt (found next to the scanned repo or in the
--distro folder), `pynxtools.units.ureg` if importable, plain pint, and finally
a built-in table when pint is not installed (--no-pint forces the table).

Outputs:
    single repo : audit_findings.csv (or --out)
    --distro    : <out-dir>/<plugin>.csv, all_findings.csv, summary.md
"""
from __future__ import annotations

import argparse
import ast
import csv
import difflib
import hashlib
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None

HERE = Path(__file__).resolve().parent
SEV = {"info": 0, "low": 1, "medium": 2, "high": 3}
SEV_NAMES = {v: k for k, v in SEV.items()}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "build", "dist",
             "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache"}

RULES = {
    # units
    "U01": "unit string not parseable (pint / unit table)",
    "U02": "ambiguous unit string",
    "U03": "non-canonical unit alias",
    "U04": "non-SI unit (check NeXus type / pint)",
    "U05": "unit string with whitespace or empty",
    "U06": "unit label hard-coded in code (not derived from data)",
    "U07": "unit hard-coded in config",
    "U08": "unit silently misread by pint (parses, but not what was meant)",
    "U09": "mapping converts between units of different dimensionality",
    "U10": "unit dimensionality does not match the field name",
    "U11": "source value assumed to be in a unit (functor without source unit)",
    # numbers
    "N01": "scale factor / physical constant in arithmetic",
    "N02": "magic number in arithmetic",
    "N03": "numeric default parameter",
    "N04": "rounding to fixed decimals",
    "N05": "truncating cast / split",
    "N06": "silent truncation to shorter length",
    "N07": "dtype narrowing (precision / range loss)",
    # data-changing operations
    "A01": "axis flip / reverse",
    "A02": "numerical transform (interpolation, filter, cumulative ...)",
    "A03": "reduction (sum / mean / std ...)",
    "A04": "axis reorder (transpose / swapaxes / rot90 ...)",
    # defaults & fallbacks
    "D01": ".get() with literal default",
    "D02": "option default read from kwargs",
    "D03": "'or <literal>' fallback",
    "D04": "constant array created (possible fabricated data)",
    "D05": "hard-coded string comparison (case-sensitive)",
    # errors
    "E01": "bare except",
    "E02": "exception swallowed",
    "E03": "assert used for validation",
    "E04": "unimplemented stub",
    "E05": "TODO / FIXME / TBD marker",
    # time
    "T01": "timezone assumption",
    "T02": "sentinel date",
    "T03": "strptime / naive datetime",
    # consistency
    "K01": "duplicate dict key (last one silently wins)",
    "K02": "keys differing only by case/underscore/space",
    "K03": "diverged copies of a function",
    "K04": "identical copies of a function",
    # config / paths
    "C01": "NeXus path literal in Python code",
    "C02": "hard-coded string value in config",
    "C03": "hard-coded number in config",
    "C04": "duplicate key in JSON object",
    "C05": "config file does not parse",
    "C06": "config keys left empty (placeholders)",
    "C07": "literal fallback in a lookup list",
    # security (parsers read user uploads)
    "S01": "eval / exec",
    "S02": "unsafe deserialisation (pickle, allow_pickle)",
    "S03": "unsafe YAML loader",
    "S04": "shell command execution",
    "S05": "archive extraction without path checks",
    "S06": "XML parsing of untrusted files (entity expansion / XXE)",
    "S07": "insecure network / temp-file call",
    # misc
    "M01": "print() call",
}

# ------------------------------------------------------------ profiles ------
def deep_merge(a: dict, b: dict) -> dict:
    """Merge b into a copy of a: dicts recurse, lists extend, scalars override."""
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        elif k in out and isinstance(out[k], list) and isinstance(v, list):
            if k == "expect":  # plugin expectations are more specific: try them first
                out[k] = v + [x for x in out[k] if x not in v]
            else:
                out[k] = out[k] + [x for x in v if x not in out[k]]
        else:
            out[k] = v
    return out


def load_toml(path: Path) -> dict:
    if tomllib is None:
        sys.exit("profiles need Python >= 3.11 or `pip install tomli`")
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def project_name(root: Path) -> str:
    pp = root / "pyproject.toml"
    if pp.is_file() and tomllib is not None:
        try:
            return load_toml(pp).get("project", {}).get("name", root.name)
        except Exception:
            pass
    return root.name


def find_profile(root: Path, profiles_dir: Path, explicit: str | None):
    """Return (merged profile dict, profile name)."""
    base = load_toml(profiles_dir / "_base.toml") if (profiles_dir / "_base.toml").is_file() else {}
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            p = profiles_dir / f"{explicit}.toml"
        if not p.is_file():
            sys.exit(f"profile not found: {explicit}")
        return deep_merge(base, load_toml(p)), p.stem
    names = {project_name(root).lower().replace("_", "-"), root.name.lower().replace("_", "-")}
    for p in sorted(profiles_dir.glob("*.toml")):
        if p.stem.startswith("_"):
            continue
        prof = load_toml(p)
        match = {m.lower() for m in prof.get("plugin", {}).get("match", [])} | {p.stem}
        if names & match:
            return deep_merge(base, prof), p.stem
    return base, "_base"


def glob_to_re(pattern: str) -> re.Pattern:
    i, out = 0, ""
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


# ----------------------------------------------------------------- units ----
SI_PREFIXES = {"", "y", "z", "a", "f", "p", "n", "u", "µ", "μ", "m",
               "c", "d", "k", "M", "G", "T", "P"}
PREFIXABLE = {"eV", "V", "A", "W", "m", "s", "Hz", "Pa", "J", "K", "N", "T", "F", "S", "g"}
CANON_ATOMS = {"eV", "J", "K", "V", "A", "W", "m", "s", "Hz", "Pa", "min", "h",
               "degree", "radian", "rad", "counts", "count", "counts_per_second",
               "angstrom", "dimensionless", "percent", "%", "degC", "N", "T", "S",
               "F", "ohm", "1", "Da", "pixel", "sr"}
AMBIGUOUS = {"C": "coulomb or Celsius?", "nU": "nano-units; voltage or current?",
             "d": "VAMAS 'd' (unspecified)", "u": "atomic mass unit or micro?",
             "a.u.": "arbitrary units", "au": "arbitrary / atomic units",
             "arb": "arbitrary units", "arb.": "arbitrary units",
             "norm": "normalised (dimensionless?)", "unitless": "dimensionless?",
             "units": "placeholder", "unit": "placeholder"}
ALIASES = {"deg": "degree", "degrees": "degree", "°": "degree",
           "cps": "counts_per_second", "c/s": "counts_per_second",
           "counts/s": "counts_per_second", "counts per second": "counts_per_second",
           "µm": "um", "μm": "um", "Å": "angstrom", "Å": "angstrom",
           "sec": "s", "secs": "s", "seconds": "s", "hr": "h", "hrs": "h",
           "volt": "V", "volts": "V", "ev": "eV", "EV": "eV", "Ev": "eV",
           "kelvin": "K", "kev": "keV", "KeV": "keV", "mev": "meV", "S-1": "1/s",
           "s-1": "1/s", "s^-1": "1/s", "Hertz": "Hz", "hz": "Hz", "ua": "uA"}
NON_SI = {"mbar", "bar", "torr", "Torr", "atm", "psi", "mmHg", "inch", "in", "mil",
          "fahrenheit", "degF"}
# pint parses these, but almost never into what the author meant
TRAPS = {"au": "arbitrary units meant? use 'a.u.'-free NX_ANY / dimensionless or a real unit",
         "nU": "SPECS/Scienta 'nU' (nano-units) meant?",
         "c/s": "counts per second meant? use counts_per_second",
         "EV": "eV meant?",
         "u": "micro prefix without a base unit?",
         "C": "degree Celsius meant? use degC",
         "F": "Fahrenheit meant? use degF",
         "G": "giga prefix without a base unit?",
         "t": "time meant?",
         "ct": "count meant?",
         "cts": "counts meant?",
         "mil": "a thousandth of an inch, really?",
         "Pa s": "product Pa*s, check intent"}
# these traps depend on the field: fine for a charge, wrong for a temperature
CONTEXT_TRAPS = {"C", "F", "G", "t", "u", "mil", "Pa s"}
# pint accepts these long names; not worth an alias finding
PINT_LONG_NAMES = {"volt", "volts", "kelvin", "seconds", "degrees", "deg", "\u00b0",
                   "\u00c5", "\u00b5m"}
SUSPICIOUS_RESOLVED = ("speed_of_light", "enzyme", "atto", "exa", "zepto", "yocto",
                       "planck", "unified_atomic", "carat", "tonne", "metric_ton",
                       "gauss", "farad", "bohr")


def _atom_ok(atom: str) -> bool:
    atom = re.sub(r"\^?[-+]?\d+$", "", atom.strip())
    if atom == "" or re.fullmatch(r"[-+]?\d+(\.\d+)?", atom):
        return True
    if atom in CANON_ATOMS:
        return True
    for base in PREFIXABLE:
        if atom.endswith(base) and atom[: -len(base)] in SI_PREFIXES:
            return True
    return False


def field_from_key(key: str, parent: str | None = None) -> str:
    """'/ENTRY[entry]/beam/wavelength/@units' -> 'wavelength'."""
    k = re.sub(r"/?@units?$", "", key.strip())
    if not k and parent:
        k = parent
    seg = k.rstrip("/").split("/")[-1] if k else ""
    m = re.fullmatch(r"([A-Za-z_0-9]+)\[([^\]]+)\]", seg)
    if m:
        seg = m[2] if "*" not in m[2] else m[1]
    return seg.lower()


class UnitChecker:
    def __init__(self, profile: dict, registry_file: str | None, search_roots: list[Path],
                 use_pint: bool, harvested: list[str]):
        u = profile.get("units", {})
        self.ambiguous = {**AMBIGUOUS, **u.get("ambiguous", {})}
        self.traps = {**TRAPS, **u.get("traps", {})}
        self.accept = set(u.get("accept", []))
        self.accept_re = [re.compile(p) for p in u.get("accept_patterns", [])]
        self.expect = [(re.compile(p, re.I), d) for p, d in u.get("expect", [])]
        self.ureg, self.source = None, "built-in unit table (pint not used)"
        self._cache: dict[str, tuple] = {}
        if not use_pint:
            return
        try:
            import pint
        except ModuleNotFoundError:
            self.source = "built-in unit table (pint not installed)"
            return
        cand = [Path(registry_file)] if registry_file else []
        for r in search_roots:
            cand += [r / "pynxtools/src/pynxtools/units/default_en.txt",
                     r / "src/pynxtools/units/default_en.txt",
                     r.parent / "pynxtools/src/pynxtools/units/default_en.txt"]
        for c in cand:
            if c.is_file():
                try:
                    self.ureg, self.source = pint.UnitRegistry(str(c)), f"pint: {c}"
                    break
                except Exception as e:  # pragma: no cover
                    print(f"warning: could not load {c}: {e}", file=sys.stderr)
        if self.ureg is None:
            try:
                from pynxtools.units import ureg  # type: ignore
                self.ureg, self.source = ureg, "pint: pynxtools.units.ureg"
            except Exception:
                self.ureg, self.source = pint.UnitRegistry(), "pint: default registry"
        for d in list(u.get("define", [])) + harvested:
            try:
                self.ureg.define(d)
            except Exception:
                pass

    def parse(self, s: str):
        """Return (quantity or None, error or None)."""
        if s in self._cache:
            return self._cache[s]
        try:
            q = self.ureg.Quantity(1, s)
            res = (q, None)
        except Exception as e:
            res = (None, type(e).__name__)
        self._cache[s] = res
        return res

    def classify(self, u: str, key: str | None = None, parent: str | None = None):
        """Return list of (rule, severity, message) for a unit string."""
        out = []
        if u == "":
            return [("U05", "low", "empty unit string")]
        if u != u.strip():
            out.append(("U05", "medium", f"unit has surrounding whitespace: {u!r}"))
            u = u.strip()
        if u in self.accept or any(r.fullmatch(u) for r in self.accept_re):
            return out
        if self.ureg is None:
            return out + self._classify_table(u)
        q, err = self.parse(u)
        fld = field_from_key(key, parent) if key is not None else ""
        dim = self.check_dim(q, u, fld) if q is not None else None  # None: no expectation
        if u in self.traps and q is not None:
            if dim == [] and u in CONTEXT_TRAPS:
                pass  # the field name confirms the dimensionality (e.g. C for a charge)
            else:
                sev = "medium" if (u in CONTEXT_TRAPS and not dim) else "high"
                out.append(("U08", sev, f"pint reads {u!r} as {q.units}: {self.traps[u]}"))
        elif u in self.ambiguous:
            out.append(("U02", "medium", f"ambiguous unit {u!r}: {self.ambiguous[u]}"))
        if q is None:
            if u not in self.ambiguous:
                out.append(("U01", "medium", f"pint cannot parse unit {u!r} ({err})"))
            return out
        resolved = str(q.units)
        if (u not in self.traps and len(u) <= 4
                and any(t in resolved for t in SUSPICIOUS_RESOLVED)):
            out.append(("U08", "high", f"pint reads {u!r} as {resolved!r}; is that intended?"))
        if u in ALIASES and u not in PINT_LONG_NAMES and u not in self.traps:
            out.append(("U03", "low", f"non-canonical alias {u!r}; prefer {ALIASES[u]!r}"))
        elif u in NON_SI:
            out.append(("U04", "low", f"non-SI unit {u!r}"))
        if dim:
            out += dim
        return out

    def check_dim(self, q, u, fld):
        """[] = matches expectation, [finding] = mismatch, None = no expectation."""
        if not fld:
            return None
        for rx, dim in self.expect:
            if rx.search(fld):
                try:
                    ok = q.check(dim)
                except Exception:
                    return None
                if not ok:
                    return [("U10", "medium", f"field {fld!r} looks like {dim} but unit "
                                              f"{u!r} is {q.dimensionality}")]
                return []
        return None

    def dims_differ(self, a: str, b: str):
        if self.ureg is None:
            return None
        qa, _ = self.parse(a)
        qb, _ = self.parse(b)
        if qa is None or qb is None:
            return None
        return qa.dimensionality != qb.dimensionality

    def _classify_table(self, u):
        if u in self.ambiguous:
            return [("U02", "medium", f"ambiguous unit {u!r}: {self.ambiguous[u]}")]
        if u in ALIASES:
            return [("U03", "low", f"non-canonical alias {u!r}; prefer {ALIASES[u]!r}")]
        if u in NON_SI:
            return [("U04", "low", f"non-SI unit {u!r}")]
        atoms = [a for a in re.split(r"[/*· ]", u) if a not in ("", "(", ")")]
        if not atoms or not all(_atom_ok(a.strip("()")) for a in atoms):
            return [("U01", "medium", f"unrecognised unit string {u!r}")]
        return []


# ------------------------------------------------------------- numbers -----
SCALE_VALUES = [1e3, 1e6, 1e9, 1e12, 1e-3, 1e-6, 1e-9, 1e-12, 60.0, 3600.0, 86400.0, 100.0]
PHYS_VALUES = {  # approximate, 1 % tolerance
    1.602176634e-19: "elementary charge / eV->J",
    6.62607015e-34: "Planck constant (J s)",
    1.054571817e-34: "reduced Planck constant (J s)",
    9.1093837015e-31: "electron mass (kg)",
    299792458.0: "speed of light",
    12398.419843: "hc in eV*Angstrom",
    1239.84198: "hc in eV*nm",
    8.617333262e-5: "Boltzmann (eV/K)",
    273.15: "Celsius -> Kelvin",
    1.0e-10: "Angstrom -> m",
    57.29577951: "180/pi (rad -> degree)",
    0.01745329252: "pi/180 (degree -> rad)",
    3.14159265: "pi (use math.pi / np.pi)",
}
IGNORE_NUMBERS = {0, 1, -1, 2, 0.5}

TRANSFORMS = {"interp1d", "interp", "interpn", "resample", "savgol_filter",
              "gaussian_filter", "gaussian_filter1d", "convolve", "cumsum",
              "cumulative_trapezoid", "cumtrapz", "trapz", "trapezoid", "gradient",
              "diff", "polyfit", "polyval", "curve_fit", "minimize", "least_squares",
              "fft", "smooth"}
REDUCTIONS = {"sum", "mean", "std", "median", "nanmean", "nansum", "nanstd",
              "average", "var"}
REORDERS = {"transpose", "swapaxes", "moveaxis", "rollaxis", "rot90", "permute_dims"}
NARROW_RE = re.compile(r"(float16|float32|half|single|u?int(8|16|32)|\bint\b|^'int'$|^\"int\"$|np\.int_\b|uint)")
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK|TBD|WORKAROUND|NOT IMPLEMENTED)\b", re.I)
LOGGER_NAMES = ("logger", "_logger", "logging", "log", "warnings", "print")
DEFINE_RE = re.compile(r"""\.define\(\s*(["'])(.+?)\1\s*\)""")


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    qualname: str
    message: str
    snippet: str = ""

    @property
    def category(self) -> str:
        return RULES.get(self.rule, "")


class Collector:
    def __init__(self, disabled: set[str], overrides: dict[str, str]):
        self.items: list[Finding] = []
        self._seen: set[tuple] = set()
        self.disabled = disabled
        self.overrides = overrides

    def add(self, rule, severity, file, line, qualname, message, snippet=""):
        if rule in self.disabled:
            return
        severity = self.overrides.get(rule, severity)
        key = (rule, file, line, message)
        if key in self._seen:
            return
        self._seen.add(key)
        self.items.append(Finding(rule, severity, file, int(line or 0), qualname,
                                  message, snippet.strip()[:160]))


# --------------------------------------------------------- python scanning --
def usrc(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return "<?>"


def is_num(node) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


def str_const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def is_units_key(node) -> bool:
    s = str_const(node)
    if s is not None:
        return s.endswith("@units") or s in ("unit", "units")
    if isinstance(node, ast.JoinedStr) and node.values:
        last = str_const(node.values[-1])
        return last is not None and last.endswith("@units")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        last = str_const(node.right)
        return last is not None and last.endswith("@units")
    return False


def key_text(node) -> str | None:
    """Best-effort text of a template key (for field-name heuristics)."""
    s = str_const(node)
    if s is not None:
        return s
    if isinstance(node, ast.JoinedStr):
        return "".join(str_const(v) or "{}" for v in node.values)
    return None


class PyScanner(ast.NodeVisitor):
    def __init__(self, rel, lines, col, store, units: UnitChecker, prof: dict):
        self.rel, self.lines, self.col, self.store = rel, lines, col, store
        self.units, self.prof = units, prof
        self.prefix = ""
        self.cur = ""
        self.ranges: list[tuple[int, int, str]] = []
        self.imports: dict[str, str] = {}
        num = prof.get("numbers", {})
        self.ignore_numbers = IGNORE_NUMBERS | set(num.get("ignore", []))
        self.phys = {**PHYS_VALUES, **{float(k): v for k, v in num.get("constants", {}).items()}}
        self.scales = SCALE_VALUES + [float(x) for x in num.get("scales", [])]
        fn = prof.get("functors", {})
        self.functors = fn.get("enabled", False)
        self.functor_keys = re.compile(fn.get("keys", r"^map(_to_\w+)?$"))
        self.unit_ns = set(fn.get("unit_namespaces", ["ureg"]))
        self.lookup_prefixes = tuple(prof.get("config", {}).get("lookup_prefixes", ["@"]))

    # helpers
    def q(self):
        return self.cur or "<module>"

    def snip(self, node):
        ln = getattr(node, "lineno", 0)
        return self.lines[ln - 1] if 0 < ln <= len(self.lines) else ""

    def add(self, rule, sev, node, msg):
        self.col.add(rule, sev, self.rel, getattr(node, "lineno", 0), self.q(),
                     msg, self.snip(node))

    def unit_value(self, value, node, via, key=None, sev_empty=None):
        if value.startswith(self.lookup_prefixes) and value != "":
            return
        for rule, sev, msg in self.units.classify(value, key):
            if value == "" and sev_empty:
                sev = sev_empty
            self.add(rule, sev, node, f"{msg} ({via})")

    def resolve(self, name: str) -> str:
        head, _, rest = name.partition(".")
        full = self.imports.get(head, head)
        return f"{full}.{rest}" if rest else full

    def number_hint(self, v):
        av = abs(float(v))
        if av in self.scales:
            return "N01", "medium", f"possible unit/scale factor {v!r}"
        for p, label in self.phys.items():
            if p != 0 and abs(av - p) / abs(p) < 0.01:
                return "N01", "medium", f"looks like a physical constant ({label}): {v!r}"
        return "N02", "low", f"hard-coded number {v!r} in arithmetic"

    def record_key(self, s, node):
        if (isinstance(s, str) and len(s) >= 4 and re.fullmatch(r"[A-Za-z0-9_ \-]+", s)):
            self.store["keys"][re.sub(r"[\s_\-]", "", s).lower()].append(
                (s, self.rel, getattr(node, "lineno", 0)))

    # imports
    def visit_Import(self, node):
        for a in node.names:
            self.imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]

    def visit_ImportFrom(self, node):
        for a in node.names:
            self.imports[a.asname or a.name] = f"{node.module or ''}.{a.name}"

    # scopes
    def visit_ClassDef(self, node):
        q = self.prefix + node.name
        self.ranges.append((node.lineno, node.end_lineno, q))
        old = (self.prefix, self.cur)
        self.cur, self.prefix = q, q + "."
        self.generic_visit(node)
        self.prefix, self.cur = old

    def visit_FunctionDef(self, node):
        q = self.prefix + node.name
        self.ranges.append((node.lineno, node.end_lineno, q))
        for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
            if is_num(d) and d.value not in self.ignore_numbers:
                self.col.add("N03", "info", self.rel, d.lineno, q,
                             f"numeric default parameter {d.value!r} in {node.name}()",
                             self.snip(d))
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(
                body[0].value.value, str):
            body = body[1:]
        decorators = " ".join(usrc(d) for d in node.decorator_list)
        if body and all(isinstance(s, ast.Pass) or (
                isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                and s.value.value is Ellipsis) for s in body):
            sev = "info" if ("abstract" in decorators or "overload" in decorators) else "medium"
            self.col.add("E04", sev, self.rel, node.lineno, q,
                         f"{node.name}() has an empty body (pass / ...)", self.snip(node))
        elif (len(body) == 1 and isinstance(body[0], ast.Raise) and body[0].exc is not None
              and "NotImplementedError" in usrc(body[0].exc)):
            self.col.add("E04", "info", self.rel, node.lineno, q,
                         f"{node.name}() raises NotImplementedError", self.snip(node))
        if len(body) >= 1:  # for K03 / K04
            src = "\n".join(usrc(s) for s in body)
            if src.count("\n") >= 2 and not (node.name.startswith("__") and node.name.endswith("__")):
                self.store["funcs"][node.name].append(
                    (self.rel, q, node.lineno, hashlib.md5(src.encode()).hexdigest(), src))
        old = (self.prefix, self.cur)
        self.cur, self.prefix = q, q + ".<locals>."
        self.generic_visit(node)
        self.prefix, self.cur = old

    visit_AsyncFunctionDef = visit_FunctionDef

    # statements
    def visit_Expr(self, node):
        v = node.value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):  # docstring
            if TODO_RE.search(v.value):
                self.add("E05", "low", node, "TODO/TBD marker in docstring")
            return
        self.generic_visit(node)

    def visit_Assert(self, node):
        self.add("E03", "low", node, "assert is stripped under python -O; "
                                      "do not rely on it for validation")
        self.generic_visit(node)

    def _targets_of(self, node):
        return node.targets if isinstance(node, ast.Assign) else [node.target]

    def visit_Assign(self, node):
        self._assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self._assign(node)
        self.generic_visit(node)

    def _assign(self, node):
        value = node.value
        for t in self._targets_of(node):
            if isinstance(t, ast.Name) and re.search(r"unit", t.id, re.I) and isinstance(value, ast.Dict):
                for k, v in zip(value.keys, value.values):
                    s = str_const(v)
                    if s is not None:
                        self.unit_value(s, v, f"value in {t.id}", key=str_const(k) if k else None,
                                        sev_empty="info")
            if isinstance(t, ast.Subscript) and is_units_key(t.slice):
                s = str_const(value)
                if s is not None and not s.startswith(self.lookup_prefixes):
                    self.add("U06", "medium", node,
                             f"unit label {s!r} is hard-coded, not read from the file")
                    self.unit_value(s, node, "assigned to a @units key", key=key_text(t.slice))

    def visit_Try(self, node):
        for h in node.handlers:
            tname = usrc(h.type) if h.type is not None else None
            body = h.body
            swallowed = all(
                isinstance(s, (ast.Pass, ast.Continue, ast.Break))
                or (isinstance(s, ast.Return) and (s.value is None or isinstance(s.value, ast.Constant)))
                or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
                    and usrc(s.value.func).split(".")[0] in LOGGER_NAMES)
                for s in body)
            if h.type is None:
                self.add("E01", "medium", h, "bare 'except:' hides every error type")
            elif swallowed:
                broad = tname in ("Exception", "BaseException")
                self.add("E02", "medium" if broad else "low", h,
                         f"except {tname}: error is swallowed and execution continues")
            if h.type is None and swallowed:
                self.add("E02", "medium", h, "exception swallowed in bare except")
        self.generic_visit(node)

    visit_TryStar = visit_Try

    # expressions
    def visit_BinOp(self, node):
        if isinstance(node.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow)):
            for side in (node.left, node.right):
                if is_num(side) and side.value not in self.ignore_numbers:
                    rule, sev, msg = self.number_hint(side.value)
                    self.add(rule, sev, node, msg)
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        if isinstance(node.op, ast.Or) and node.values:
            last = node.values[-1]
            if isinstance(last, ast.Constant) and last.value not in (None, "", 0, False) \
                    and not isinstance(last.value, bool):
                self.add("D03", "low", node, f"'... or {last.value!r}' silently replaces "
                                              "a falsy value (incl. 0 / empty)")
        self.generic_visit(node)

    def visit_Compare(self, node):
        for op, comp in zip(node.ops, node.comparators):
            consts = []
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant):
                consts = [comp.value]
            elif isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, (ast.List, ast.Tuple, ast.Set)):
                consts = [e.value for e in comp.elts if isinstance(e, ast.Constant)]
            for c in consts:
                if isinstance(c, str) and len(c) >= 3 and re.search(r"[A-Za-z]", c) \
                        and not isinstance(node.left, ast.Constant) \
                        and "__main__" not in c:
                    self.add("D05", "low", node,
                             f"exact, case-sensitive match against {c!r}; other spellings fall through")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if usrc(node).endswith("timezone.utc"):
            self.add("T01", "medium", node, "UTC timezone assumed/attached here")
        if node.attr == "T" and not isinstance(node.ctx, ast.Store):
            self.add("A04", "low", node, f"{usrc(node)[:40]}: transposed; check axis "
                                         "order matches @axes / AXISNAME_indices")
        self.generic_visit(node)

    def visit_Constant(self, node):
        v = node.value
        if isinstance(v, str) and ("ENTRY[" in v or v.startswith("/ENTRY")):
            self.add("C01", "info", node, f"NeXus path literal {v[:60]!r} in code "
                                          "(mapping outside the config files)")

    def _unit_attr(self, node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in self.unit_ns:
            return node.attr
        return None

    def _functor_list(self, key, value):
        if not isinstance(value, (ast.List, ast.Tuple)):
            return
        for el in value.elts:
            if not isinstance(el, ast.Tuple):
                continue
            parts = el.elts
            trg = str_const(parts[0]) if parts else None
            us = [(i, self._unit_attr(p)) for i, p in enumerate(parts) if self._unit_attr(p)]
            for _, uname in us:
                q, err = self.units.parse(uname) if self.units.ureg is not None else (True, None)
                if q is None:
                    self.add("U01", "medium", el, f"functor unit ureg.{uname} not parseable ({err})")
            if len(parts) == 4 and len(us) == 2 and us[0][0] == 1 and us[1][0] == 3:
                differ = self.units.dims_differ(us[0][1], us[1][1])
                if differ:
                    self.add("U09", "high", el, f"{key}: '{trg}' maps ureg.{us[1][1]} -> "
                             f"ureg.{us[0][1]}: different dimensionality")
            if len(parts) == 3 and len(us) == 1 and us[0][0] == 1:
                self.add("U11", "info", el, f"{key}: '{trg}' assumes the source value is in "
                         f"ureg.{us[0][1]} (no source unit given)")
            if trg and us and self.units.ureg is not None:
                q, _ = self.units.parse(us[0][1])
                if q is not None:
                    for rule, sev, msg in self.units.check_dim(q, us[0][1], field_from_key(trg)) or []:
                        self.add(rule, sev, el, f"{msg} (functor {key})")

    def visit_Dict(self, node):
        seen = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant):
                key = (type(k.value), k.value)
                if key in seen:
                    line0, v0 = seen[key]
                    if usrc(v0) == usrc(v):
                        self.add("K01", "low", k, f"duplicate dict key {k.value!r} (first at line "
                                 f"{line0}) with the same value: redundant, harmless")
                    else:
                        self.add("K01", "high", k, f"duplicate dict key {k.value!r} (first at line "
                                 f"{line0}): {usrc(v0)[:40]} is silently replaced by {usrc(v)[:40]}")
                else:
                    seen[key] = (k.lineno, v)
                if isinstance(k.value, str):
                    self.record_key(k.value, k)
                    if self.functors and self.functor_keys.search(k.value):
                        self._functor_list(k.value, v)
            if k is not None and is_units_key(k):
                s = str_const(v)
                if s is not None:
                    self.unit_value(s, v, "dict entry for a unit key", key=key_text(k))
        self.generic_visit(node)

    def visit_Subscript(self, node):
        sl = node.slice
        if isinstance(sl, ast.Slice) and isinstance(sl.step, ast.UnaryOp) \
                and isinstance(sl.step.op, ast.USub) and is_num(sl.step.operand) \
                and sl.step.operand.value == 1:
            self.add("A01", "medium", node, "reversed with [::-1]: check the paired axis/signal")
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            self.record_key(sl.value, node)
        if (isinstance(sl, ast.Constant) and sl.value == 0 and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "split"
                and node.value.args and isinstance(node.value.args[0], ast.Constant)
                and node.value.args[0].value == "."):
            self.add("N05", "low", node, "split('.')[0] drops the fractional part")
        self.generic_visit(node)

    def _kw(self, node, name):
        return next((k.value for k in node.keywords if k.arg == name), None)

    def visit_Call(self, node):
        name = usrc(node.func)
        full = self.resolve(name)
        last = name.split(".")[-1]
        root_mod = full.split(".")[0]

        # rounding
        if last in ("round", "around"):
            nd = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg in ("ndigits", "decimals")), None)
            if isinstance(nd, ast.Constant) and isinstance(nd.value, int):
                sev = "medium" if nd.value <= 3 else "low"
                self.add("N04", sev, node, f"rounded to {nd.value} decimals: "
                                           "loses precision for fine steps / small values")
        # flips / reorders
        if last in ("flip", "flipud", "fliplr") or (last == "reverse" and not node.args):
            self.add("A01", "medium", node, f"{name}(): axis reversed; "
                                           "verify the paired signal is reordered too")
        if last in REORDERS:
            self.add("A04", "medium" if last == "rot90" else "low", node,
                     f"{name}(): axes reordered; check @axes / AXISNAME_indices and image origin")
        # defaults
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                self.record_key(a0.value, node)
            if len(node.args) == 2 and isinstance(node.args[1], ast.Constant) \
                    and node.args[1].value is not None:
                dflt = node.args[1].value
                target = usrc(node.func.value)
                if re.search(r"kwargs|options|params|settings", target):
                    self.add("D02", "medium", node, f"option default {dflt!r} for "
                             f"{usrc(a0)} read from {target}: check docs match this default")
                else:
                    sev = "info" if dflt in ("", 0, False) else "low"
                    self.add("D01", sev, node, f".get({usrc(a0)}, {dflt!r}): silent fallback value")
        if name == "getattr" and len(node.args) == 3 and isinstance(node.args[2], ast.Constant) \
                and node.args[2].value is not None:
            self.add("D01", "low", node, f"getattr default {node.args[2].value!r}")
        # fabricated arrays
        if last in ("ones", "ones_like", "full", "full_like"):
            self.add("D04", "medium", node, f"{name}(): constant array; if it stands in for "
                                           "missing data it fabricates values")
        elif last in ("zeros", "zeros_like"):
            self.add("D04", "low", node, f"{name}(): zero-filled array")
        # numerical processing
        if last in TRANSFORMS:
            self.add("A02", "low", node, f"{name}(): data-changing operation; "
                                         "is the processing recorded in the output?")
        elif last in REDUCTIONS:
            self.add("A03", "info", node, f"{name}(): reduction; check mean vs sum "
                                          "and the naming in the NeXus output")
        # casts / truncations
        if name == "int" and node.args and isinstance(node.args[0], ast.Call) \
                and usrc(node.args[0].func) == "float":
            self.add("N05", "low", node, "int(float(x)) truncates toward zero")
        if name == "min" and len(node.args) == 2 and all(
                isinstance(a, ast.Call) and usrc(a.func) == "len" for a in node.args):
            self.add("N06", "low", node, "min(len(a), len(b)): arrays of different "
                                         "length are silently truncated")
        if last == "astype" and node.args and NARROW_RE.search(usrc(node.args[0])):
            self.add("N07", "low", node, f"astype({usrc(node.args[0])}): narrows precision "
                                         "or range; int truncates toward zero")
        # time handling
        if last == "datetime" and len(node.args) >= 3 and all(
                is_num(a) for a in node.args[:3]) and [a.value for a in node.args[:3]] == [1, 1, 1]:
            self.add("T02", "medium", node, "sentinel date 0001-01-01 used as fallback")
        if last in ("timezone", "tzoffset", "tzutc") or any(k.arg == "tzinfo" for k in node.keywords):
            self.add("T01", "medium", node, f"timezone constructed/attached via {name}()")
        if last in ("utcnow", "utcfromtimestamp", "fromtimestamp", "strptime", "now"):
            self.add("T03", "info", node, f"{name}(): naive or format-dependent time handling")
        # units passed as keywords
        for k in node.keywords:
            if k.arg in ("unit", "units") and isinstance(k.value, ast.Constant) \
                    and isinstance(k.value.value, str):
                self.unit_value(k.value.value, node, f"keyword {k.arg}=")
        # security
        if name in ("eval", "exec"):
            self.add("S01", "high", node, f"{name}() executes arbitrary code; "
                                          "use ast.literal_eval / a parser")
        if root_mod in ("pickle", "cPickle", "dill", "joblib", "cloudpickle", "_pickle") \
                and last in ("load", "loads"):
            self.add("S02", "high", node, f"{full}(): unpickling untrusted data runs code")
        if last == "load" and root_mod == "numpy":
            ap = self._kw(node, "allow_pickle")
            if isinstance(ap, ast.Constant) and ap.value is True:
                self.add("S02", "high", node, "np.load(allow_pickle=True) on uploaded files runs code")
        if root_mod == "yaml" and last in ("load", "load_all", "unsafe_load", "full_load"):
            loader = self._kw(node, "Loader") or (node.args[1] if len(node.args) > 1 else None)
            lname = usrc(loader) if loader is not None else ""
            if last == "unsafe_load" or (last in ("load", "load_all") and
                                         (not lname or re.search(r"(Unsafe|Full)?Loader$", lname)
                                          and "Safe" not in lname)):
                self.add("S03", "high", node, f"{full}() with loader {lname or 'default'}: "
                                              "use yaml.safe_load")
            elif last == "full_load":
                self.add("S03", "medium", node, "yaml.full_load can build arbitrary objects; "
                                                "use yaml.safe_load")
        if full.startswith("subprocess.") and isinstance(self._kw(node, "shell"), ast.Constant) \
                and self._kw(node, "shell").value is True:
            self.add("S04", "medium", node, f"{full}(shell=True): command injection risk")
        if full in ("os.system", "os.popen"):
            self.add("S04", "medium", node, f"{full}(): runs a shell command")
        if last == "extractall" and self._kw(node, "filter") is None:
            self.add("S05", "medium", node, f"{name}(): archive members can escape the "
                                            "target dir (path traversal); check names / use filter='data'")
        if (re.search(r"(etree|ElementTree|minidom|xmltodict|sax|pulldom)", full)
                and last in ("parse", "fromstring", "XML", "iterparse", "parseString",
                             "XMLParser", "fromstringlist")
                and not full.startswith("defusedxml")):
            if full.startswith("lxml"):
                rent = self._kw(node, "resolve_entities")
                if not (isinstance(rent, ast.Constant) and rent.value is False):
                    self.add("S06", "medium", node, f"{full}(): lxml resolves entities by default "
                                                    "(XXE); use resolve_entities=False or defusedxml")
            else:
                self.add("S06", "low", node, f"{full}(): stdlib XML parser on uploaded file; "
                                             "entity-expansion DoS; consider defusedxml")
        if full == "tempfile.mktemp":
            self.add("S07", "low", node, "tempfile.mktemp is race-prone; use mkstemp")
        vf = self._kw(node, "verify")
        if root_mod in ("requests", "httpx") and isinstance(vf, ast.Constant) and vf.value is False:
            self.add("S07", "medium", node, f"{full}(verify=False): TLS check disabled")
        if name == "print":
            self.add("M01", "info", node, "print() in library code")
        self.generic_visit(node)


def scan_comments(rel, text, ranges, col):
    try:
        toks = tokenize.generate_tokens(io.StringIO(text).readline)
        for tok in toks:
            if tok.type == tokenize.COMMENT and TODO_RE.search(tok.string):
                ln = tok.start[0]
                inner = [r for r in ranges if r[0] <= ln <= r[1]]
                qn = min(inner, key=lambda r: r[1] - r[0])[2] if inner else "<module>"
                col.add("E05", "low", rel, ln, qn, tok.string.strip()[:100], tok.line)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass


# ----------------------------------------------------------- config files ---
JSON_LINE = re.compile(r'^\s*"(?P<key>(?:[^"\\]|\\.)*)"\s*:\s*(?P<val>.*?)\s*,?\s*$')
YAML_LINE = re.compile(r'^\s*-?\s*(?P<key>[A-Za-z0-9_@/\[\]\. \-]+?)\s*:\s+(?P<val>[^#]+?)\s*(#.*)?$')
STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _parse_fallback(v: str):
    """MultiFormatReader fallback syntax "['@attrs:a', '@eln', 'eV']" -> list."""
    try:
        val = ast.literal_eval(v)
    except (ValueError, SyntaxError):
        return None
    return val if isinstance(val, list) else None


def scan_json(rel, text, col, units: UnitChecker, prof: dict):
    cfg = prof.get("config", {})
    lookups = tuple(cfg.get("lookup_prefixes", ["@"]))
    lookup_keys = set(cfg.get("lookup_keys", []))
    dups: list[str] = []

    def hook(pairs):
        c = Counter(k for k, _ in pairs)
        dups.extend(k for k, n in c.items() if n > 1)
        return dict(pairs)

    try:
        json.loads(text, object_pairs_hook=hook)
    except json.JSONDecodeError as e:
        col.add("C05", "medium", rel, e.lineno, "<config>", f"JSON parse error: {e.msg}")
        return
    lines = text.splitlines()
    for key in set(dups):
        hits = [i for i, l in enumerate(lines, 1) if f'"{key}"' in l and ":" in l]
        for i in hits[1:]:
            col.add("C04", "high", rel, i, "<config>",
                    f"duplicate JSON key {key[:80]!r}: the last occurrence wins", lines[i - 1])
    stack: list[str] = []
    empties: list[int] = []
    for i, line in enumerate(lines, 1):
        m = JSON_LINE.match(line)
        parent = next((s for s in reversed(stack) if s != "<item>"), None)
        stripped = STRING_RE.sub('""', line)
        first = True
        for ch in stripped:
            if ch in "{[":
                stack.append(m["key"] if (m and first) else "<item>")
                first = False
            elif ch in "}]" and stack:
                stack.pop()
        if not m:
            continue
        key, raw = m["key"], m["val"]
        if raw.startswith(("{", "[")):
            continue
        try:
            v = json.loads(raw)
        except ValueError:
            continue
        unit_key = key.endswith("@units") or key in ("unit", "units")
        if isinstance(v, str):
            if v == "":
                if cfg.get("placeholder_empty", True):
                    empties.append(i)
                    continue
            fb = _parse_fallback(v) if (cfg.get("fallback_lists", True) and v.startswith("[")) else None
            if fb is not None:
                for lit in fb:
                    if isinstance(lit, str) and lit.startswith(lookups):
                        continue
                    col.add("C07", "low", rel, i, "<config>",
                            f"literal fallback {lit!r} is written when every lookup in "
                            f"{key[-50:]!r} fails", line)
                    if unit_key and isinstance(lit, str):
                        for rule, sev, msg in units.classify(lit, key, parent):
                            col.add(rule, sev, rel, i, "<config>", msg + " (config fallback)", line)
                continue
            if v.startswith(lookups) or key in lookup_keys:
                continue  # lookup into parsed data / ELN: mapping, not hard-coded
            if unit_key:
                col.add("U07", "low", rel, i, "<config>",
                        f"unit {v!r} is fixed for every file (key {key[-50:]!r})", line)
                for rule, sev, msg in units.classify(v, key, parent):
                    col.add(rule, sev, rel, i, "<config>", msg + " (config)", line)
            else:
                col.add("C02", "info", rel, i, "<config>",
                        f"hard-coded value {v[:50]!r} for {key[-60:]!r}", line)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            col.add("C03", "low", rel, i, "<config>",
                    f"hard-coded number {v!r} for {key[-60:]!r}", line)
    if empties:
        col.add("C06", "info", rel, empties[0], "<config>",
                f"{len(empties)} keys mapped to '' (placeholders, written as nothing); "
                f"lines {', '.join(map(str, empties[:8]))}{' ...' if len(empties) > 8 else ''}")


def scan_yaml(rel, text, col, units: UnitChecker, prof: dict):
    lookups = tuple(prof.get("config", {}).get("lookup_prefixes", ["@"]))
    for i, line in enumerate(text.splitlines(), 1):
        m = YAML_LINE.match(line)
        if m and m["key"].strip() in ("unit", "units"):
            val = m["val"].strip().strip("'\"")
            if val.startswith(lookups + ("{", "[")):
                continue
            for rule, sev, msg in units.classify(val):
                col.add(rule, sev, rel, i, "<config>", msg + " (yaml)", line)


# ------------------------------------------------------------ cross-file ----
def cross_file(store, col, prof):
    for norm, uses in store["keys"].items():
        variants = defaultdict(list)
        for s, f, ln in uses:
            variants[s].append((f, ln))
        if len(variants) < 2:
            continue
        ordered = sorted(variants.items(), key=lambda kv: -len(kv[1]))
        desc = "; ".join(f"{s!r} x{len(l)} (e.g. {l[0][0]}:{l[0][1]})" for s, l in ordered[:5])
        minor = ordered[-1][1][0]
        col.add("K02", "low", minor[0], minor[1], "<keys>",
                f"same key spelled differently: {desc}")
    dup = prof.get("duplicates", {})
    ignore = set(dup.get("ignore_functions", []))
    threshold = float(dup.get("similarity", 0.6))
    for fname, defs in store["funcs"].items():
        if len(defs) < 2 or fname in ignore:
            continue
        hashes = {d[3] for d in defs}
        first = defs[0]
        locs = ", ".join(f"{d[0]}:{d[2]}" for d in defs[:6])
        if len(hashes) == 1:
            col.add("K04", "info", first[0], first[2], first[1],
                    f"{fname}() duplicated verbatim in: {locs}")
        else:
            best = max(difflib.SequenceMatcher(None, first[4], d[4]).ratio()
                       for d in defs[1:])
            if best >= threshold:
                col.add("K03", "low", first[0], first[2], first[1],
                        f"{fname}() exists in similar but different copies "
                        f"(similarity up to {best:.2f}): {locs}. Compare behaviour")


# -------------------------------------------------------------- driver ------
def iter_files(root: Path, prof: dict, include_tests: bool):
    scan = prof.get("scan", {})
    inc = [glob_to_re(g) for g in scan.get("include", ["**/*.py", "**/*.json", "**/*.yaml", "**/*.yml"])]
    if include_tests:
        inc += [glob_to_re(g) for g in scan.get("tests", ["tests/**/*.py"])]
    exc = [glob_to_re(g) for g in scan.get("exclude", [])]
    force = [glob_to_re(g) for g in scan.get("force_include", [])]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            f = Path(dirpath) / fn
            rel = f.relative_to(root).as_posix()
            if f.suffix not in (".py", ".json", ".yaml", ".yml"):
                continue
            if any(r.match(rel) for r in force) or (
                    any(r.match(rel) for r in inc) and not any(r.match(rel) for r in exc)):
                yield f, rel


@dataclass
class RepoResult:
    name: str
    profile: str
    root: Path
    items: list = field(default_factory=list)
    n_files: Counter = field(default_factory=Counter)
    unit_source: str = ""


def scan_repo(root: Path, args, profiles_dir: Path, search_roots: list[Path]) -> RepoResult:
    prof, pname = find_profile(root, profiles_dir, args.profile)
    rules = prof.get("rules", {})
    disabled = set(rules.get("disable", [])) | {r.strip() for r in args.disable.split(",") if r.strip()}
    col = Collector(disabled, dict(rules.get("severity", {})))
    store = {"keys": defaultdict(list), "funcs": defaultdict(list)}
    files = list(iter_files(root, prof, args.include_tests))
    texts = {rel: f.read_text(errors="ignore") for f, rel in files}
    harvested = [m[2] for rel, t in texts.items() if rel.endswith(".py")
                 for m in DEFINE_RE.finditer(t)] if prof.get("units", {}).get("harvest_defines", True) else []
    units = UnitChecker(prof, args.unit_registry, search_roots + [root], not args.no_pint, harvested)
    res = RepoResult(project_name(root), pname, root, unit_source=units.source)
    for f, rel in files:
        text = texts[rel]
        res.n_files[f.suffix] += 1
        if f.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError as e:
                col.add("C05", "medium", rel, e.lineno or 1, "<module>", f"syntax error: {e.msg}")
                continue
            sc = PyScanner(rel, text.splitlines(), col, store, units, prof)
            sc.visit(tree)
            scan_comments(rel, text, sc.ranges, col)
        elif f.suffix == ".json":
            scan_json(rel, text, col, units, prof)
        else:
            scan_yaml(rel, text, col, units, prof)
    cross_file(store, col, prof)
    items = [x for x in col.items if SEV[x.severity] >= SEV[args.min_severity]]
    items.sort(key=lambda x: (-SEV[x.severity], x.file, x.line))
    res.items = items
    return res


HEADER = ["plugin", "rule", "severity", "category", "file", "line", "qualname",
          "message", "snippet", "reviewed", "notes"]


def write_csv(path: Path, results: list[RepoResult]):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for r in results:
            for x in r.items:
                w.writerow([r.name, x.rule, x.severity, x.category, x.file, x.line, x.qualname,
                            x.message, x.snippet, "", ""])


def print_report(r: RepoResult):
    print(f"== {r.name}  (profile: {r.profile}; units: {r.unit_source})")
    print(f"scanned: {dict(r.n_files)}   findings: {len(r.items)}")
    by_sev = Counter(x.severity for x in r.items)
    print("by severity:", {s: by_sev.get(s, 0) for s in ("high", "medium", "low", "info")})
    print("by rule:")
    for rule, n in Counter(x.rule for x in r.items).most_common():
        print(f"  {rule}  {n:4d}  {RULES.get(rule, '')}")
    print("files with most medium/high findings:")
    hot = Counter(x.file for x in r.items if SEV[x.severity] >= 2)
    for f, n in hot.most_common(10):
        print(f"  {n:4d}  {f}")


def write_summary(path: Path, results: list[RepoResult]):
    rules = sorted({x.rule for r in results for x in r.items})
    lines = ["# audit_scan summary", "",
             "| plugin | profile | files | high | medium | low | info |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        s = Counter(x.severity for x in r.items)
        lines.append(f"| {r.name} | {r.profile} | {sum(r.n_files.values())} | {s['high']} | "
                     f"{s['medium']} | {s['low']} | {s['info']} |")
    lines += ["", "## Findings per rule", "",
              "| rule | " + " | ".join(r.name.replace("pynxtools-", "") for r in results) + " |",
              "|---|" + "---|" * len(results)]
    for rule in rules:
        cnt = [sum(1 for x in r.items if x.rule == rule) for r in results]
        lines.append(f"| {rule} {RULES.get(rule, '')} | " + " | ".join(str(c or "") for c in cnt) + " |")
    lines += ["", "## High-severity findings", ""]
    for r in results:
        for x in r.items:
            if x.severity == "high":
                lines.append(f"- **{r.name}** `{x.file}:{x.line}` {x.rule}: {x.message}")
    path.write_text("\n".join(lines) + "\n")


def annotate_inventory(inv_path: str, items):
    with open(inv_path, newline="") as fh:
        inv = list(csv.DictReader(fh))
    by_file = defaultdict(list)
    for i, row in enumerate(inv):
        by_file[row["file"]].append(i)
    stats = defaultdict(lambda: {"n": 0, "max": -1, "rules": Counter()})
    for x in items:
        best, span = None, 10 ** 9
        for i in by_file.get(x.file, []):
            row = inv[i]
            try:
                s, e = int(float(row["line_start"])), int(float(row["line_end"]))
            except (ValueError, TypeError):
                continue
            if s <= x.line <= e and (e - s) < span and row["kind"] != "module":
                best, span = i, e - s
        if best is None:  # fall back to the module row
            for i in by_file.get(x.file, []):
                if inv[i]["kind"] in ("module", "config"):
                    best = i
        if best is not None:
            st = stats[best]
            st["n"] += 1
            st["max"] = max(st["max"], SEV[x.severity])
            st["rules"][x.rule] += 1
    out = inv_path.replace(".csv", "") + "_with_findings.csv"
    cols = list(inv[0].keys()) + ["scan_findings", "scan_max_severity", "scan_rules"]
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, row in enumerate(inv):
            st = stats.get(i)
            row["scan_findings"] = st["n"] if st else 0
            row["scan_max_severity"] = SEV_NAMES[st["max"]] if st else ""
            row["scan_rules"] = ";".join(f"{r}x{n}" for r, n in sorted(st["rules"].items())) if st else ""
            w.writerow(row)
    print(f"annotated ledger -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--distro", help="folder whose sub-folders are repos (e.g. nomad-distro-dev/packages)")
    ap.add_argument("--out", default="audit_findings.csv", help="CSV for a single-repo scan")
    ap.add_argument("--out-dir", default="audit_results", help="output folder for --distro")
    ap.add_argument("--profile", help="profile name or .toml path (default: auto-detect)")
    ap.add_argument("--profiles-dir", default=str(HERE / "profiles"))
    ap.add_argument("--unit-registry", help="pint definitions file (e.g. pynxtools/units/default_en.txt)")
    ap.add_argument("--no-pint", action="store_true", help="use the built-in unit table only")
    ap.add_argument("--inventory", help="path to inventory.csv to annotate (single repo)")
    ap.add_argument("--min-severity", choices=list(SEV), default="info")
    ap.add_argument("--disable", default="", help="comma-separated rule ids to skip (on top of the profile)")
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--list-rules", action="store_true")
    ap.add_argument("--list-profiles", action="store_true")
    a = ap.parse_args()
    profiles_dir = Path(a.profiles_dir)

    if a.list_rules:
        for k, v in RULES.items():
            print(f"{k}  {v}")
        return 0
    if a.list_profiles:
        for p in sorted(profiles_dir.glob("*.toml")):
            d = load_toml(p).get("plugin", {})
            print(f"{p.stem:28} {d.get('description', '')}")
        return 0

    if a.distro:
        base = Path(a.distro).resolve()
        repos = [d for d in sorted(base.iterdir()) if (d / "pyproject.toml").is_file()]
        out = Path(a.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        results = []
        for d in repos:
            r = scan_repo(d, a, profiles_dir, [base])
            print_report(r)
            print()
            write_csv(out / f"{r.name}.csv", [r])
            results.append(r)
        write_csv(out / "all_findings.csv", results)
        write_summary(out / "summary.md", results)
        print(f"-> {out}/ (per-plugin CSVs, all_findings.csv, summary.md)")
        return 0

    root = Path(a.root).resolve()
    r = scan_repo(root, a, profiles_dir, [root.parent])
    write_csv(Path(a.out), [r])
    print_report(r)
    print(f"-> {a.out}")
    if a.inventory:
        annotate_inventory(a.inventory, r.items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
