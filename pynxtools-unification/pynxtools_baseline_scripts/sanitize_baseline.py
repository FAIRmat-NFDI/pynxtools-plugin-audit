#!/usr/bin/env python3
"""Make a public copy of a baseline_<ts> folder: replace personal paths and names, then audit for secrets.

    python sanitize_baseline.py baseline_results/baseline_<ts> public/baseline_<ts>

The source folder is never modified. The script:
  1. copies SRC to DST (DST must not exist),
  2. replaces your home path, user name and host name (and any --replace OLD=NEW)
     - in file and folder names,
     - in every text file (logs, csv, tsv, json, jsonl, md, yaml, xml, txt, diff, ...),
     - in every string attribute and string dataset of HDF5 files (.nxs, .h5, .hdf5, ...), via h5py,
  3. rewrites MANIFEST.sha256 (the hashes change because the files changed),
  4. audits DST: leftover personal strings, secret-like patterns, e-mails, private IPs,
     sensitive file names, binary files that still contain your user name, and runs
     gitleaks / trufflehog when they are installed,
  5. writes DST/../<name>_sanitize_report.txt (outside DST, so it is not published) and
     exits 1 if anything needs a manual look.

Defaults are taken from the machine you run it on: $HOME -> $HOME, user -> $USER, host -> $HOSTNAME.
Placeholders are shorter than the originals, so fixed-length HDF5 strings still fit.
"""
import argparse
import getpass
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

try:
    import h5py
    import numpy as np
except ImportError:  # HDF5 files are then only audited, not rewritten
    h5py = None

HDF5_SIG = b"\x89HDF\r\n\x1a\n"
SKIP_TEXT_SUFFIXES = {".nxs", ".h5", ".hdf5", ".hdf", ".edaxh5", ".mtex.h5", ".zip", ".gz", ".png",
                      ".jpg", ".jpeg", ".tif", ".tiff", ".pdf", ".npy", ".npz", ".pkl"}

SECRET_PATTERNS = {
    "github token": r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b",
    "gitlab token": r"\bglpat-[A-Za-z0-9_\-]{20,}\b",
    "aws access key": r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
    "google api key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "slack token": r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b",
    "pypi token": r"\bpypi-[A-Za-z0-9_\-]{50,}\b",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "jwt / bearer": r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b|[Bb]earer\s+[A-Za-z0-9._\-]{20,}",
    "credentials in url": r"[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s@]+@",
    "token in url": r"https?://[^/\s@]{20,}@",
    "secret assignment": r"(?i)\b[A-Z0-9_]*(password|passwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|auth)[A-Z0-9_]*\s*[:=]\s*['\"]?(?!\$|<|\*|None|null|false|true|\s*$)[^\s'\",]{6,}",
}
INFO_PATTERNS = {
    "e-mail": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "private ip": r"\b(10\.\d{1,3}|192\.168|172\.(1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
}
SENSITIVE_NAMES = re.compile(r"(^\.env|\.env$|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|\.pfx$|\.netrc$|\.pypirc$|"
                             r"credentials|secrets?\.(ya?ml|json|toml)$|nomad\.yaml$)", re.I)
# e-mails that are fine to publish (authors in package metadata, bots, ...)
EMAIL_ALLOW = re.compile(r"(noreply|example\.(com|org)|users\.noreply\.github\.com|@python\.org)", re.I)


def is_hdf5(p: Path) -> bool:
    try:
        with p.open("rb") as fh:
            return fh.read(8) == HDF5_SIG
    except OSError:
        return False


def read_text(p: Path):
    if p.suffix.lower() in SKIP_TEXT_SUFFIXES or is_hdf5(p):
        return None
    data = p.read_bytes()
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def subst(s, repl):
    for old, new in repl:
        s = s.replace(old, new)
    return s


# ---------------------------------------------------------------- rewriting
def rename_paths(root: Path, repl):
    n = 0
    for p in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):  # deepest first
        new = subst(p.name, repl).replace("$", "")  # no shell-special '$' in file names
        if new != p.name:
            p.rename(p.with_name(new))
            n += 1
    return n


def fix_text(p: Path, repl):
    txt = read_text(p)
    if txt is None:
        return False
    new = subst(txt, repl)
    if new != txt:
        p.write_text(new, encoding="utf-8")
        return True
    return False


def _fix_value(v, repl):
    """Return (changed, new_value) for an attribute or dataset value."""
    if isinstance(v, bytes):
        s = v.decode("utf-8", "replace")
        n = subst(s, repl)
        return (n != s, n.encode("utf-8"))
    if isinstance(v, str):
        n = subst(v, repl)
        return (n != v, n)
    if isinstance(v, np.ndarray) and v.dtype.kind in "SUO":
        out = v.copy()
        changed = False
        for idx, item in np.ndenumerate(v):
            c, n = _fix_value(item, repl)
            if c:
                out[idx] = n
                changed = True
        return (changed, out)
    return (False, v)


def fix_hdf5(p: Path, repl):
    if h5py is None:
        return 0
    changes = 0
    with h5py.File(p, "r+") as f:
        objs = [f]
        f.visititems(lambda name, obj: objs.append(obj))
        for obj in objs:
            for k in list(obj.attrs.keys()):
                try:
                    c, n = _fix_value(obj.attrs[k], repl)
                except Exception:
                    continue
                if c:
                    if isinstance(n, np.ndarray) and n.dtype.kind == "O":
                        n = np.array([x.decode() if isinstance(x, bytes) else x for x in n.ravel()],
                                     dtype=h5py.string_dtype()).reshape(n.shape)
                    obj.attrs[k] = n
                    changes += 1
            if isinstance(obj, h5py.Dataset) and (obj.dtype.kind in "SUO" or h5py.check_string_dtype(obj.dtype)):
                try:
                    v = obj[()]
                except Exception:
                    continue
                c, n = _fix_value(v, repl)
                if c:
                    obj[()] = n
                    changes += 1
    return changes


# ---------------------------------------------------------------- auditing
def h5_strings(p: Path):
    out = []
    if h5py is None:
        return out
    try:
        with h5py.File(p, "r") as f:
            def visit(name, obj):
                out.append(name)
                for k, v in obj.attrs.items():
                    out.append(f"{name}@{k}={v!r}")
                if isinstance(obj, h5py.Dataset) and obj.dtype.kind in "SUO" and obj.size < 10000:
                    try:
                        out.append(f"{name}={obj[()]!r}")
                    except Exception:
                        pass
            f.visititems(visit)
    except Exception as e:
        out.append(f"<cannot open: {e}>")
    return out


def audit(root: Path, personal):
    hits = []
    pats = {**{k: re.compile(v) for k, v in SECRET_PATTERNS.items()},
            **{k: re.compile(v) for k, v in INFO_PATTERNS.items()}}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        for s in personal:
            if s and s in str(rel):
                hits.append(("personal string in name", rel, s))
        if not p.is_file():
            continue
        if SENSITIVE_NAMES.search(p.name):
            hits.append(("sensitive file name", rel, p.name))
        txt = read_text(p)
        if txt is not None:
            lines = txt.splitlines()
        elif is_hdf5(p):
            lines = h5_strings(p)
        else:
            data = p.read_bytes()
            for s in personal:
                if s and s.encode() in data:
                    hits.append(("personal string in binary file (cannot rewrite)", rel, s))
            continue
        for i, line in enumerate(lines, 1):
            for s in personal:
                if s and s in line:
                    hits.append(("personal string", f"{rel}:{i}", line.strip()[:200]))
            for name, rx in pats.items():
                m = rx.search(line)
                if m and not (name == "e-mail" and EMAIL_ALLOW.search(m.group(0))):
                    hits.append((name, f"{rel}:{i}", line.strip()[:200]))
    return hits


def run_scanners(root: Path):
    out = []
    if shutil.which("gitleaks"):
        for cmd in (["gitleaks", "dir", str(root), "--no-banner", "--redact"],
                    ["gitleaks", "detect", "--no-git", "--source", str(root), "--no-banner", "--redact"]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if "unknown command" not in (r.stderr + r.stdout):
                out.append(f"$ {' '.join(cmd)}  (exit {r.returncode}; 0 = no leaks)\n{r.stdout}{r.stderr}")
                break
    else:
        out.append("gitleaks not installed (https://github.com/gitleaks/gitleaks), skipped")
    if shutil.which("trufflehog"):
        cmd = ["trufflehog", "filesystem", str(root), "--no-update", "--fail"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        out.append(f"$ {' '.join(cmd)}  (exit {r.returncode}; 0 = nothing found)\n{r.stdout}{r.stderr}")
    else:
        out.append("trufflehog not installed (https://github.com/trufflesecurity/trufflehog), skipped")
    return out


def write_manifest(root: Path):
    man = root / "MANIFEST.sha256"
    if not man.exists():
        return
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p != man:
            h = hashlib.sha256()
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            lines.append(f"{h.hexdigest()}  ./{p.relative_to(root)}")
    man.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--user", default=getpass.getuser())
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--host", default=socket.gethostname())
    ap.add_argument("--replace", action="append", default=[], metavar="OLD=NEW",
                    help="extra replacement, e.g. --replace 'Keila Moral=$NAME' (repeatable)")
    ap.add_argument("--audit-only", action="store_true", help="only audit SRC, change nothing")
    a = ap.parse_args()

    host_short = a.host.split(".")[0]
    repl = [(a.home.rstrip("/"), "$HOME")]
    repl += [tuple(r.split("=", 1)) for r in a.replace]
    repl += [(a.host, "$HOSTNAME")]
    if host_short != a.host:
        repl.append((host_short, "$HOSTNAME"))
    repl.append((a.user, "$USER"))
    repl = [(o, n) for o, n in repl if o and len(o) >= 3]
    personal = sorted({o for o, _ in repl}, key=len, reverse=True)

    src, dst = a.src.resolve(), a.dst.resolve()
    if not src.is_dir():
        sys.exit(f"{src} is not a folder")
    if a.audit_only:
        root = src
    else:
        if dst.exists():
            sys.exit(f"{dst} exists; give a new folder (the source is never changed in place)")
        if dst == src or src in dst.parents:
            sys.exit("DST must be outside SRC")
        print(f"copying {src} -> {dst}")
        shutil.copytree(src, dst, symlinks=True)
        root = dst
        for p in root.rglob("*"):
            if p.is_symlink():
                print(f"  removing symlink {p.relative_to(root)} -> {os.readlink(p)}")
                p.unlink()
        n_ren = rename_paths(root, repl)
        n_txt = n_h5 = n_h5f = 0
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if is_hdf5(p):
                try:
                    c = fix_hdf5(p, repl)
                except Exception as e:
                    print(f"  HDF5 rewrite failed for {p.relative_to(root)}: {e}")
                    c = 0
                n_h5 += c
                n_h5f += bool(c)
            elif fix_text(p, repl):
                n_txt += 1
        write_manifest(root)
        print(f"renamed {n_ren} paths, rewrote {n_txt} text files, {n_h5} HDF5 strings in {n_h5f} files")
        if h5py is None:
            print("WARNING: h5py not importable, HDF5 files were NOT rewritten (run with the distro's .venv/bin/python)")

    print("auditing ...")
    hits = audit(root, personal)
    scans = run_scanners(root)
    report = root.parent / f"{root.name}_sanitize_report.txt"
    with report.open("w") as fh:
        fh.write(f"audit of {root}\nreplacements: " + ", ".join(f"{o!r}->{n!r}" for o, n in repl) + "\n\n")
        by_kind = {}
        for kind, where, what in hits:
            by_kind.setdefault(kind, []).append((where, what))
        for kind, items in sorted(by_kind.items()):
            fh.write(f"== {kind}: {len(items)} hit(s)\n")
            for where, what in items:
                fh.write(f"  {where}: {what}\n")
            fh.write("\n")
        fh.write("== external scanners\n" + "\n".join(scans) + "\n")
    print(f"{len(hits)} hit(s); report: {report}")
    for kind in sorted({h[0] for h in hits}):
        print(f"  {kind}: {sum(h[0] == kind for h in hits)}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
