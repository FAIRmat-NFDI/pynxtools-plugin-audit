#!/usr/bin/env python3
"""Make a public copy of a baseline_<ts> folder: replace personal names and paths, then verify none are left.

    python sanitize_baseline.py baseline_results/baseline_<ts> public/baseline_<ts> \\
        --term <first-name> --term <last-name> --keep <branch-to-keep>

The source folder is never modified. The script:
  1. copies SRC to DST (DST must not exist),
  2. replaces, case-insensitively,
       - home paths /home/<you>... and /Users/<you>..., also when truncated ("/home/jdo" for /home/jdoe) -> $HOME
       - your GitHub login (auto-detected from git_state.tsv) -> GITHUB_USER, except inside
         github.com/<login>/<repo> URLs, which are kept (--replace-github-urls to replace them too)
       - host name -> $HOSTNAME, user name and every --term -> $USER
         (long terms are also caught when cut off at the end of a field, e.g. "jdoe_us" for jdoe_user)
     in file and folder names, in every text file, and in HDF5/.nxs files: attributes, string
     datasets, text stored as uint8/int8 arrays, object names, soft/external link targets,
  3. rebuilds every changed HDF5 file into a fresh file, so the old strings do not survive in
     freed space inside the file (in-place edits leave them there),
  4. rewrites MANIFEST.sha256 (the hashes change because the files changed),
  5. audits DST: personal strings (with the exact HDF5 path), secret-like patterns, e-mails,
     private IPs, sensitive file names; runs gitleaks / trufflehog when installed,
  6. verifies DST by a raw, case-insensitive byte search of every file for every personal term,
  7. writes <DST>_sanitize_report.txt next to DST (not inside it) and exits 1 on any hit.

Run it with the distro's .venv/bin/python so h5py is available.
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
except ImportError:  # HDF5 files are then only byte-scanned, not rewritten
    h5py = None

HDF5_SIG = b"\x89HDF\r\n\x1a\n"
BINARY_SUFFIXES = {".nxs", ".h5", ".hdf5", ".hdf", ".edaxh5", ".zip", ".gz", ".png", ".jpg", ".jpeg",
                   ".tif", ".tiff", ".pdf", ".npy", ".npz", ".pkl", ".ibw", ".sxm", ".spe"}
# GitHub owners that are not a person; any other owner found in git_state.tsv counts as personal
PUBLIC_GITHUB_OWNERS = {"fairmat-nfdi", "nomad-coe", "fairmat-experimental", "nexusformat", "mtex-toolbox"}

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
EMAIL_ALLOW = re.compile(r"(noreply|example\.(com|org)|users\.noreply\.github\.com|@python\.org)", re.I)


# ---------------------------------------------------------------- replacement rules
class Rules:
    def __init__(self, user, home, host, terms, github_logins, extra, keep=(), keep_github_urls=True):
        self.rules = []  # (compiled regex, replacement)
        # allowed exceptions: never replaced, never reported
        keep_parts = [re.escape(k) for k in keep if k]
        if keep_github_urls and github_logins:
            logins = "|".join(re.escape(g) for g in github_logins)
            keep_parts.append(r"(?:https?://|git@)github\.com[/:](?:%s)/[A-Za-z0-9._-]+" % logins)
        self.keep = re.compile("|".join(keep_parts), re.I) if keep_parts else None
        self.keep_b = re.compile("|".join(keep_parts).encode(), re.I) if keep_parts else None
        home_names = {Path(home).name, user}
        name_alt = "|".join(re.escape(n) for n in sorted(home_names, key=len, reverse=True) if n)
        # full or truncated home paths: /home/<you>/..., /home/<cut-off name><end of field>, /Users/...
        self.rules.append((re.compile(r"(?:/home|/Users)/(?:%s)(?=[/\s'\"`,;:)\]}]|$)" % name_alt, re.I), "$HOME"))
        self.rules.append((re.compile(r"(?:/home|/Users)/[A-Za-z0-9._-]+(?=[\s'\"`,;)\]}]|$)"), self._trunc_home(home_names)))
        for login in sorted(github_logins, key=len, reverse=True):
            self.rules.append((re.compile(r"(github\.com[/:])%s(?=/|\.git|\b)" % re.escape(login), re.I), r"\1GITHUB_USER"))
            self.rules.append((re.compile(re.escape(login), re.I), "GITHUB_USER"))
        for old, new in extra:
            self.rules.append((re.compile(re.escape(old), re.I), new.replace("\\", "\\\\")))
        if host and len(host) >= 3:
            self.rules.append((re.compile(re.escape(host), re.I), "$HOSTNAME"))
            short = host.split(".")[0]
            if short != host and len(short) >= 3:
                self.rules.append((re.compile(r"\b%s\b" % re.escape(short), re.I), "$HOSTNAME"))
        self.terms = sorted({t for t in [user, *terms, *github_logins] if t and len(t) >= 3}, key=len, reverse=True)
        for t in self.terms:  # longest first; a long term cut off at the end of a field
            self.rules.append((re.compile(re.escape(t), re.I), "$USER"))  # (fixed-width columns) right after it
            if len(t) >= 6:
                prefixes = "|".join(re.escape(t[:k]) for k in range(len(t) - 1, 3, -1))
                self.rules.append((re.compile(r"(?:%s)(?=[\s'\"`,;)\]}]|$)" % prefixes, re.I), "$USER"))
        self.search_terms = sorted({*self.terms, Path(home).name, *(h for h in [host] if h and len(h) >= 3)},
                                   key=len, reverse=True)

    @staticmethod
    def _trunc_home(names):
        def repl(m):
            last = m.group(0).rsplit("/", 1)[-1].lower()
            # a cut-off home folder name such as /home/keil (prefix of the real one)
            if len(last) >= 1 and any(n.lower().startswith(last) for n in names):
                return "$HOME"
            return m.group(0)
        return repl

    def apply(self, s):
        kept = []
        if self.keep:
            def stash(m):
                kept.append(m.group(0))
                return f"\x00KEEP{len(kept) - 1}\x00"
            s = self.keep.sub(stash, s)
        for rx, new in self.rules:
            s = rx.sub(new, s)
        for i, k in enumerate(kept):
            s = s.replace(f"\x00KEEP{i}\x00", k)
        return s

    def unkept(self, s):
        """Text with the allowed exceptions blanked out, for searching."""
        return self.keep.sub(" ", s) if self.keep else s

    def unkept_bytes(self, b):
        return self.keep_b.sub(lambda m: b" " * len(m.group(0)), b) if self.keep_b else b

    def hit_regex(self):
        rx = re.compile("|".join(re.escape(t) for t in self.search_terms), re.I)
        rules = self

        class _Rx:  # search() ignores allowed exceptions
            def search(self, text):
                return rx.search(rules.unkept(text))
        return _Rx()

    def hit_bytes(self):
        return re.compile(b"|".join(re.escape(t.encode()) for t in self.search_terms), re.I)


# ---------------------------------------------------------------- helpers
def is_hdf5(p: Path) -> bool:
    try:
        with p.open("rb") as fh:
            return fh.read(8) == HDF5_SIG
    except OSError:
        return False


def read_text(p: Path):
    if p.suffix.lower() in BINARY_SUFFIXES or is_hdf5(p):
        return None
    data = p.read_bytes()
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def rename_paths(root: Path, rules):
    n = 0
    for p in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):  # deepest first
        new = rules.apply(p.name).replace("$", "")  # no shell-special '$' in file names
        if new != p.name:
            p.rename(p.with_name(new))
            n += 1
    return n


def fix_text(p: Path, rules):
    txt = read_text(p)
    if txt is None:
        return False
    new = rules.apply(txt)
    if new != txt:
        p.write_text(new, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------- HDF5
def _fix_value(v, rules):
    """Return (changed, new_value) for an attribute or dataset value."""
    if isinstance(v, bytes):
        s = v.decode("utf-8", "replace")
        n = rules.apply(s)
        return (n != s, n.encode("utf-8"))
    if isinstance(v, str):
        n = rules.apply(v)
        return (n != v, n)
    if isinstance(v, np.ndarray) and v.dtype.kind in "SUO":
        vals = [_fix_value(x, rules) for x in v.ravel()]
        if not any(c for c, _ in vals):
            return (False, v)
        new = [x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x) for _, x in vals]
        return (True, np.array(new, dtype=h5py.string_dtype()).reshape(v.shape))
    return (False, v)


def _walk(group, prefix=""):
    """Yield (path, parent_group, name, link) for every link below group (no recursion into external links)."""
    for name in list(group.keys()):
        link = group.get(name, getlink=True)
        path = f"{prefix}/{name}"
        yield path, group, name, link
        if isinstance(link, h5py.HardLink):
            obj = group[name]
            if isinstance(obj, h5py.Group):
                yield from _walk(obj, path)


def fix_hdf5(p: Path, rules):
    """Rewrite strings in place; returns number of changes."""
    changes = 0
    with h5py.File(p, "r+") as f:
        objs = [("/", f)]
        links = list(_walk(f))
        for path, parent, name, link in links:
            if isinstance(link, h5py.HardLink):
                objs.append((path, parent[name]))
        seen = set()
        for path, obj in objs:
            if obj.id in seen:
                continue
            seen.add(obj.id)
            for k in list(obj.attrs.keys()):
                try:
                    c, n = _fix_value(obj.attrs[k], rules)
                except Exception:
                    continue
                newk = rules.apply(k)
                if c or newk != k:
                    v = n if c else obj.attrs[k]
                    if newk != k:
                        del obj.attrs[k]
                    obj.attrs[newk] = v
                    changes += 1
            if not isinstance(obj, h5py.Dataset):
                continue
            if obj.is_virtual:
                changes += _fix_virtual(obj, rules)
                continue
            if obj.dtype.kind in "SUO" or h5py.check_string_dtype(obj.dtype):
                try:
                    c, n = _fix_value(obj[()], rules)
                except Exception:
                    continue
                if c:
                    _replace_dataset(obj, np.asarray(n) if not isinstance(n, (str, bytes)) else n)
                    changes += 1
            elif obj.dtype.kind in "iu" and obj.dtype.itemsize == 1 and obj.ndim == 1 and obj.size < 50_000_000:
                raw = obj[()].tobytes()
                try:
                    s = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                n = rules.apply(s)
                if n != s:
                    _replace_dataset(obj, np.frombuffer(n.encode("utf-8"), dtype=obj.dtype))
                    changes += 1
        # links and object names (deepest first so parent renames do not invalidate paths)
        for path, parent, name, link in reversed(links):
            if isinstance(link, h5py.SoftLink):
                new = rules.apply(link.path)
                if new != link.path:
                    del parent[name]
                    parent[name] = h5py.SoftLink(new)
                    changes += 1
            elif isinstance(link, h5py.ExternalLink):
                fn, lp = rules.apply(link.filename), rules.apply(link.path)
                if (fn, lp) != (link.filename, link.path):
                    del parent[name]
                    parent[name] = h5py.ExternalLink(fn, lp)
                    changes += 1
            newname = rules.apply(name)
            if newname != name:
                parent.move(name, newname)
                changes += 1
    return changes


def _fix_virtual(ds, rules):
    """Rewrite the source file names of a virtual dataset (recreated with the same mapping and attributes)."""
    dcpl = ds.id.get_create_plist()
    dec = lambda x: x.decode("utf-8", "replace") if isinstance(x, bytes) else x
    maps = [(dcpl.get_virtual_vspace(i), dec(dcpl.get_virtual_filename(i)), dec(dcpl.get_virtual_dsetname(i)),
             dcpl.get_virtual_srcspace(i)) for i in range(dcpl.get_virtual_count())]
    new_maps = [(vs, rules.apply(fn), rules.apply(dn), ss) for vs, fn, dn, ss in maps]
    if [m[1:3] for m in new_maps] == [m[1:3] for m in maps]:
        return 0
    new = h5py.h5p.create(h5py.h5p.DATASET_CREATE)
    for (vs, fn, dn, ss), (_, old_fn, old_dn, _) in zip(new_maps, maps):
        if ss.get_select_type() == h5py.h5s.SEL_ALL and ss.get_select_npoints() != vs.get_select_npoints():
            # HDF5 may report a stored "all" source space as scalar; rebuild it from the source
            # dataset (still reachable on this machine) or, failing that, as 1-D of the mapped size
            try:
                src = Path(old_fn) if os.path.isabs(old_fn) else Path(ds.file.filename).parent / old_fn
                with h5py.File(src, "r") as sf:
                    shape = sf[old_dn].shape
            except Exception:
                shape = (vs.get_select_npoints(),)
            ss = h5py.h5s.create_simple(shape)
        new.set_virtual(vs, fn.encode("utf-8"), dn.encode("utf-8"), ss)
    try:
        fv = np.zeros((1,), dtype=ds.dtype)
        ds.id.get_create_plist().get_fill_value(fv)
        new.set_fill_value(fv)
    except Exception:
        pass
    parent, name = ds.parent, ds.name.rsplit("/", 1)[-1]
    attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}
    tid, space = ds.id.get_type(), ds.id.get_space()
    del parent[name]
    h5py.h5d.create(parent.id, name.encode("utf-8"), tid, space, dcpl=new)
    for k, v in attrs.items():
        parent[name].attrs[k] = v
    return 1


def _replace_dataset(ds, value):
    """Recreate a dataset with a new value (shape or string length may change), keeping its attributes."""
    parent, name = ds.parent, ds.name.rsplit("/", 1)[-1]
    attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}
    kw = {}
    if ds.compression and not isinstance(value, (str, bytes)) and np.ndim(value) > 0:
        kw = {"compression": ds.compression, "compression_opts": ds.compression_opts, "chunks": True}
    del parent[name]
    new = parent.create_dataset(name, data=value, **kw)
    for k, v in attrs.items():
        new.attrs[k] = v


def rebuild_hdf5(p: Path):
    """Copy all content into a fresh file, so freed space with old strings is dropped."""
    tmp = p.with_name(p.name + ".rebuild")
    with h5py.File(p, "r") as src, h5py.File(tmp, "w") as dst:
        for k in src.attrs.keys():
            dst.attrs[k] = src.attrs[k]
        for name in src.keys():
            link = src.get(name, getlink=True)
            if isinstance(link, h5py.HardLink):
                src.copy(src[name], dst, name=name)
            else:
                dst[name] = link
    tmp.replace(p)


def h5_hits(p: Path, rx):
    """Exact HDF5 locations whose names, attributes, strings, text-like arrays or links match rx."""
    hits = []
    if h5py is None:
        return hits
    try:
        with h5py.File(p, "r") as f:
            def check(where, value):
                s = value if isinstance(value, str) else repr(value)
                if rx.search(s):
                    hits.append((where, s[:200]))
            for k, v in f.attrs.items():
                check(f"/@{k}", f"{k}={v!r}")
            for path, parent, name, link in _walk(f):
                check(path + " (name)", name)
                if isinstance(link, h5py.SoftLink):
                    check(path + " (soft link)", link.path)
                elif isinstance(link, h5py.ExternalLink):
                    check(path + " (external link)", f"{link.filename}:{link.path}")
                    continue
                obj = parent[name]
                for k, v in obj.attrs.items():
                    check(f"{path}/@{k}", f"{k}={v!r}")
                if isinstance(obj, h5py.Dataset):
                    if obj.is_virtual:
                        for vs in obj.virtual_sources():
                            check(path + " (virtual source)", f"{vs.file_name}:{vs.dset_name}")
                    elif obj.dtype.kind in "SUO" or obj.dtype.names or (obj.dtype.itemsize == 1 and obj.size < 50_000_000):
                        try:
                            v = obj[()]
                            check(path, v.tobytes().decode("utf-8", "replace") if isinstance(v, np.ndarray)
                                  and v.dtype.kind in "iuV" else repr(v))
                        except Exception:
                            pass
    except Exception as e:
        hits.append(("<file>", f"cannot open with h5py: {e}"))
    return hits


# ---------------------------------------------------------------- auditing
def audit(root: Path, rules):
    hits = []
    rx_terms = rules.hit_regex()
    pats = {**{k: re.compile(v) for k, v in SECRET_PATTERNS.items()},
            **{k: re.compile(v) for k, v in INFO_PATTERNS.items()}}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if rx_terms.search(str(rel)):
            hits.append(("personal string in file name", rel, str(rel)))
        if not p.is_file():
            continue
        if SENSITIVE_NAMES.search(p.name):
            hits.append(("sensitive file name", rel, p.name))
        txt = read_text(p)
        if txt is None:
            if is_hdf5(p):
                for where, what in h5_hits(p, rx_terms):
                    hits.append(("personal string in HDF5", f"{rel}:{where}", what))
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if rx_terms.search(line):
                hits.append(("personal string", f"{rel}:{i}", line.strip()[:200]))
            for name, rx in pats.items():
                m = rx.search(line)
                if m and not (name == "e-mail" and EMAIL_ALLOW.search(m.group(0))):
                    hits.append((name, f"{rel}:{i}", line.strip()[:200]))
    return hits


def verify_bytes(root: Path, rules):
    """Final pass: raw case-insensitive byte search of every file (catches compressed-free leftovers)."""
    rx = rules.hit_bytes()
    hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        data = rules.unkept_bytes(p.read_bytes())
        for m in rx.finditer(data):
            ctx = data[max(0, m.start() - 40):m.end() + 40]
            hits.append(("raw bytes", f"{p.relative_to(root)}@{m.start()}",
                         ctx.decode("latin-1").encode("unicode_escape").decode()[:200]))
            if sum(1 for h in hits if h[1].startswith(str(p.relative_to(root)) + "@")) >= 5:
                break
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


def github_logins(root: Path):
    found = set()
    for p in root.glob("00_environment/git_state.tsv"):
        for m in re.finditer(r"github\.com[/:]([A-Za-z0-9-]+)/", p.read_text(errors="replace")):
            if m.group(1).lower() not in PUBLIC_GITHUB_OWNERS:
                found.add(m.group(1))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--user", default=getpass.getuser())
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--host", default=socket.gethostname())
    ap.add_argument("--term", action="append", default=[],
                    help="extra personal string, replaced by $USER case-insensitively (repeatable)")
    ap.add_argument("--github-user", action="append", default=None,
                    help="GitHub login(s) to replace by GITHUB_USER (default: owners in git_state.tsv "
                         "other than the known public orgs)")
    ap.add_argument("--replace", action="append", default=[], metavar="OLD=NEW",
                    help="extra literal replacement, case-insensitive (repeatable)")
    ap.add_argument("--keep", action="append", default=[], metavar="TEXT",
                    help="allowed exception: left as is and not reported, e.g. --keep my_dev_branch (repeatable)")
    ap.add_argument("--replace-github-urls", action="store_true",
                    help="also replace the login inside github.com/<login>/<repo> URLs (kept by default)")
    ap.add_argument("--audit-only", action="store_true", help="only audit SRC, change nothing")
    a = ap.parse_args()

    src, dst = a.src.resolve(), a.dst.resolve()
    if not src.is_dir():
        sys.exit(f"{src} is not a folder")
    logins = set(a.github_user) if a.github_user is not None else github_logins(src)
    rules = Rules(a.user, a.home.rstrip("/"), a.host, a.term, logins,
                  [tuple(r.split("=", 1)) for r in a.replace], keep=a.keep,
                  keep_github_urls=not a.replace_github_urls)
    print("personal strings searched (case-insensitive):", ", ".join(rules.search_terms))
    print("GitHub logins replaced by GITHUB_USER:", ", ".join(sorted(logins)) or "none",
          "(github.com URLs kept)" if not a.replace_github_urls else "")
    if a.keep:
        print("kept as is:", ", ".join(a.keep))

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
        n_ren = rename_paths(root, rules)
        n_txt = n_h5 = n_h5f = 0
        rx_b = rules.hit_bytes()
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            if is_hdf5(p):
                if h5py is None:
                    continue
                try:
                    c = fix_hdf5(p, rules)
                    if c or rx_b.search(rules.unkept_bytes(p.read_bytes())):
                        rebuild_hdf5(p)
                except Exception as e:
                    print(f"  HDF5 rewrite failed for {p.relative_to(root)}: {e}")
                    c = 0
                n_h5 += c
                n_h5f += bool(c)
            elif fix_text(p, rules):
                n_txt += 1
        write_manifest(root)
        print(f"renamed {n_ren} paths, rewrote {n_txt} text files, {n_h5} HDF5 items in {n_h5f} files")
        if h5py is None:
            print("WARNING: h5py not importable, HDF5 files were NOT rewritten (run with the distro's .venv/bin/python)")

    print("auditing ...")
    hits = audit(root, rules)
    raw = verify_bytes(root, rules)
    scans = run_scanners(root)
    report = root.parent / f"{root.name}_sanitize_report.txt"
    with report.open("w") as fh:
        fh.write(f"audit of {root}\npersonal strings: {', '.join(rules.search_terms)}\n\n")
        by_kind = {}
        for kind, where, what in hits + raw:
            by_kind.setdefault(kind, []).append((where, what))
        for kind, items in sorted(by_kind.items()):
            fh.write(f"== {kind}: {len(items)} hit(s)\n")
            for where, what in items:
                fh.write(f"  {where}: {what}\n")
            fh.write("\n")
        fh.write("== external scanners\n" + "\n".join(scans) + "\n")
    print(f"{len(hits)} audit hit(s), {len(raw)} raw-byte hit(s) of personal strings; report: {report}")
    for kind in sorted({h[0] for h in hits + raw}):
        print(f"  {kind}: {sum(h[0] == kind for h in hits + raw)}")
    return 1 if (hits or raw) else 0


if __name__ == "__main__":
    sys.exit(main())
