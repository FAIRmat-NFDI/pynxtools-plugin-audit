#!/usr/bin/env python3
"""
monitor_resources.py - sample the computing resources of a process tree and
attribute every process to the plugin / step / case it belongs to.

Two ways to use it:

  # 1) wrap any command (standalone)
  python monitor_resources.py --out monitor/ -- ./run_baseline.sh

  # 2) attach to an already running process tree (run_baseline.sh does this)
  python monitor_resources.py --out monitor/ --root-pid 12345

Attribution: every process is tagged with the environment variables
BASELINE_PACKAGE, BASELINE_STEP and BASELINE_CASE that it inherited
(run_baseline.sh sets them per plugin and per step). Processes without tags are
labelled "-". If an events file from the pytest recorder is given
(--events-glob), samples of a pytest process are also attributed to the test
that was running at that moment.

Output (all CSV, written to --out):
  processes.csv          one row per process per sample (the raw time series)
  system.csv             one row per sample: whole-machine CPU / RAM / swap / load + tree totals
  summary_by_step.csv    per (package, step, case): duration, peak RAM of the whole
                         process group, peak of the largest single process, CPU seconds,
                         disk I/O, max threads, number of processes
  summary_by_package.csv per package: totals over all its steps
  summary_by_process.csv per process (pid): command, tags, lifetime, peak RSS, CPU seconds
  summary_by_test.csv    per pytest test id (needs --events-glob): duration, peak RSS, CPU seconds

Needs psutil. If the distro venv has no psutil, run it without touching the venv:
  uv run --no-project --with psutil python monitor_resources.py ...

Limitation: processes that live shorter than the sampling interval can be
missed (their totals are still in run_baseline.sh's resources.json files).
"""

import argparse
import csv
import glob
import json
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict

try:
    import psutil
except ImportError:
    sys.exit(
        "monitor_resources.py needs psutil. Try:\n"
        "  uv run --no-project --with psutil python monitor_resources.py ..."
    )

TAG_VARS = ("BASELINE_PACKAGE", "BASELINE_STEP", "BASELINE_CASE")
HOME = os.path.expanduser("~").rstrip("/") if os.path.expanduser("~") not in ("~", "/") else ""
MB = 2**20

PROC_FIELDS = [
    "t", "elapsed_s", "pid", "ppid", "name", "package", "step", "case",
    "rss_mb", "vms_mb", "cpu_user_s", "cpu_sys_s", "cpu_pct", "threads",
    "read_mb", "write_mb", "status", "cmdline",
]
SYS_FIELDS = [
    "t", "elapsed_s", "cpu_pct_total", "load1", "ram_used_mb", "ram_available_mb",
    "swap_used_mb", "tree_processes", "tree_rss_mb", "tree_cpu_pct", "active_tags",
]


class Monitor:
    def __init__(self, root_pid, out, interval):
        self.root_pid = root_pid
        self.out = out
        self.interval = interval
        self.t0 = time.time()
        self.tags = {}       # (pid, create_time) -> (package, step, case)
        self.meta = {}       # (pid, create_time) -> dict(name, cmdline, ppid)
        self.procs = {}      # (pid, create_time) -> psutil.Process (kept for cpu_percent)
        self.stop = False
        os.makedirs(out, exist_ok=True)
        self.f_proc = open(os.path.join(out, "processes.csv"), "w", newline="")
        self.f_sys = open(os.path.join(out, "system.csv"), "w", newline="")
        self.w_proc = csv.DictWriter(self.f_proc, PROC_FIELDS)
        self.w_sys = csv.DictWriter(self.f_sys, SYS_FIELDS)
        self.w_proc.writeheader()
        self.w_sys.writeheader()
        psutil.cpu_percent(None)

    def _tag(self, key, p):
        if key in self.tags:
            return self.tags[key]
        try:
            env = p.environ()
        except (psutil.Error, OSError):
            env = {}
        tag = tuple(env.get(v, "-") or "-" for v in TAG_VARS)
        # a process whose environ is unreadable inherits its parent's tags
        if tag == ("-", "-", "-"):
            try:
                parent = p.parent()
                pkey = (parent.pid, parent.create_time()) if parent else None
                tag = self.tags.get(pkey, tag)
            except (psutil.Error, OSError):
                pass
        self.tags[key] = tag
        return tag

    def _tree(self):
        try:
            root = psutil.Process(self.root_pid)
            return [root] + root.children(recursive=True)
        except psutil.NoSuchProcess:
            return []

    def sample(self):
        now = time.time()
        elapsed = round(now - self.t0, 2)
        tree = self._tree()
        if not tree:
            return False
        tot_rss, tot_cpu, active = 0.0, 0.0, set()
        for p in tree:
            try:
                key = (p.pid, p.create_time())
                proc = self.procs.setdefault(key, p)
                with proc.oneshot():
                    mem = proc.memory_info()
                    cpu = proc.cpu_times()
                    cpu_pct = proc.cpu_percent(None)  # since previous sample of this process
                    nthreads = proc.num_threads()
                    status = proc.status()
                    try:
                        io = proc.io_counters()
                        rmb, wmb = io.read_bytes / MB, io.write_bytes / MB
                    except (psutil.Error, AttributeError, OSError):
                        rmb = wmb = ""
                    if key not in self.meta:
                        try:
                            cmd = " ".join(proc.cmdline())
                        except (psutil.Error, OSError):
                            cmd = ""
                        # home path -> "~" before truncating, so no cut-off user name ends up in the csv
                        cmd = cmd.replace(HOME, "~")[:400] if HOME else cmd[:400]
                        self.meta[key] = {"name": proc.name(), "ppid": proc.ppid(), "cmdline": cmd}
                tag = self._tag(key, proc)
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                continue
            if tag[1] == "monitor" or p.pid == os.getpid():
                continue  # don't measure the monitor itself
            m = self.meta[key]
            rss = mem.rss / MB
            tot_rss += rss
            tot_cpu += cpu_pct
            if tag != ("-", "-", "-"):
                active.add("/".join(tag))
            self.w_proc.writerow({
                "t": round(now, 2), "elapsed_s": elapsed, "pid": p.pid, "ppid": m["ppid"],
                "name": m["name"], "package": tag[0], "step": tag[1], "case": tag[2],
                "rss_mb": round(rss, 1), "vms_mb": round(mem.vms / MB, 1),
                "cpu_user_s": round(cpu.user, 2), "cpu_sys_s": round(cpu.system, 2),
                "cpu_pct": round(cpu_pct, 1), "threads": nthreads,
                "read_mb": round(rmb, 2) if rmb != "" else "", "write_mb": round(wmb, 2) if wmb != "" else "",
                "status": status, "cmdline": m["cmdline"],
            })
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        try:
            load1 = round(os.getloadavg()[0], 2)
        except OSError:
            load1 = ""
        self.w_sys.writerow({
            "t": round(now, 2), "elapsed_s": elapsed, "cpu_pct_total": psutil.cpu_percent(None),
            "load1": load1, "ram_used_mb": round((vm.total - vm.available) / MB, 1),
            "ram_available_mb": round(vm.available / MB, 1), "swap_used_mb": round(sw.used / MB, 1),
            "tree_processes": len(tree), "tree_rss_mb": round(tot_rss, 1),
            "tree_cpu_pct": round(tot_cpu, 1), "active_tags": ";".join(sorted(active)),
        })
        self.f_proc.flush()
        self.f_sys.flush()
        return True

    def run(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: setattr(self, "stop", True))
        while not self.stop:
            t = time.time()
            if not self.sample():
                break
            time.sleep(max(0.0, self.interval - (time.time() - t)))
        self.f_proc.close()
        self.f_sys.close()


# ----------------------------------------------------------------------------
# Summaries (can also be re-run on an existing folder with --summarize-only)
# ----------------------------------------------------------------------------
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _write(path, rows, fields=None):
    with open(path, "w", newline="") as fh:
        if not rows:
            fh.write("no data\n")
            return
        w = csv.DictWriter(fh, fields or list(rows[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_events(pattern):
    """pytest recorder events -> {pid: [(t_start, t_end, nodeid, package)]}"""
    windows = defaultdict(list)
    for path in glob.glob(pattern) if pattern else []:
        package = os.path.basename(os.path.dirname(os.path.dirname(path)))
        start = {}
        for line in open(path):
            ev = json.loads(line)
            k = (ev["pid"], ev["nodeid"])
            if ev["event"] == "start":
                start[k] = ev["t"]
            elif ev["event"] == "finish" and k in start:
                windows[ev["pid"]].append((start.pop(k), ev["t"], ev["nodeid"], package))
    return windows


def summarize(out, interval, events_glob=None):
    rows = list(csv.DictReader(open(os.path.join(out, "processes.csv"))))
    if not rows:
        print("[monitor] no samples recorded")
        return

    # per process ------------------------------------------------------------
    per_proc = {}
    for r in rows:
        k = (r["pid"], r["cmdline"])
        d = per_proc.setdefault(k, {
            "pid": r["pid"], "ppid": r["ppid"], "name": r["name"], "package": r["package"],
            "step": r["step"], "case": r["case"], "first_seen_s": _f(r["elapsed_s"]),
            "last_seen_s": 0.0, "peak_rss_mb": 0.0, "cpu_s": 0.0, "max_threads": 0,
            "read_mb": 0.0, "write_mb": 0.0, "cmdline": r["cmdline"]})
        d["last_seen_s"] = _f(r["elapsed_s"])
        d["peak_rss_mb"] = max(d["peak_rss_mb"], _f(r["rss_mb"]))
        d["cpu_s"] = max(d["cpu_s"], _f(r["cpu_user_s"]) + _f(r["cpu_sys_s"]))
        d["max_threads"] = max(d["max_threads"], int(_f(r["threads"])))
        d["read_mb"] = max(d["read_mb"], _f(r["read_mb"]))
        d["write_mb"] = max(d["write_mb"], _f(r["write_mb"]))
    procs = sorted(per_proc.values(), key=lambda d: d["first_seen_s"])
    for d in procs:
        d["lifetime_s"] = round(d["last_seen_s"] - d["first_seen_s"] + interval, 2)
        for k in ("cpu_s", "read_mb", "write_mb"):
            d[k] = round(d[k], 2)
    _write(os.path.join(out, "summary_by_process.csv"), procs, [
        "pid", "ppid", "name", "package", "step", "case", "first_seen_s", "lifetime_s",
        "peak_rss_mb", "cpu_s", "max_threads", "read_mb", "write_mb", "cmdline"])

    # per (package, step, case): group RSS = sum of its processes at each sample
    group_rss = defaultdict(lambda: defaultdict(float))
    for r in rows:
        group_rss[(r["package"], r["step"], r["case"])][r["t"]] += _f(r["rss_mb"])
    steps = {}
    for d in procs:
        k = (d["package"], d["step"], d["case"])
        s = steps.setdefault(k, {"package": k[0], "step": k[1], "case": k[2], "start_s": d["first_seen_s"],
                                 "end_s": 0.0, "n_processes": 0, "peak_group_rss_mb": 0.0,
                                 "peak_single_process_rss_mb": 0.0, "cpu_s": 0.0,
                                 "max_threads": 0, "read_mb": 0.0, "write_mb": 0.0})
        s["start_s"] = min(s["start_s"], d["first_seen_s"])
        s["end_s"] = max(s["end_s"], d["last_seen_s"] + interval)
        s["n_processes"] += 1
        s["peak_single_process_rss_mb"] = max(s["peak_single_process_rss_mb"], d["peak_rss_mb"])
        s["cpu_s"] += d["cpu_s"]
        s["max_threads"] = max(s["max_threads"], d["max_threads"])
        s["read_mb"] += d["read_mb"]
        s["write_mb"] += d["write_mb"]
    for k, s in steps.items():
        s["duration_s"] = round(s["end_s"] - s["start_s"], 2)
        s["peak_group_rss_mb"] = round(max(group_rss[k].values()), 1)
        s["avg_cpu_cores"] = round(s["cpu_s"] / s["duration_s"], 2) if s["duration_s"] else ""
        for f in ("cpu_s", "read_mb", "write_mb", "start_s", "end_s"):
            s[f] = round(s[f], 2)
    step_rows = sorted(steps.values(), key=lambda s: s["start_s"])
    _write(os.path.join(out, "summary_by_step.csv"), step_rows, [
        "package", "step", "case", "start_s", "duration_s", "n_processes", "peak_group_rss_mb",
        "peak_single_process_rss_mb", "cpu_s", "avg_cpu_cores", "max_threads", "read_mb", "write_mb"])

    # per package --------------------------------------------------------------
    pkgs = {}
    for s in step_rows:
        p = pkgs.setdefault(s["package"], {"package": s["package"], "n_steps": 0, "total_duration_s": 0.0,
                                           "peak_group_rss_mb": 0.0, "cpu_s": 0.0, "n_processes": 0})
        p["n_steps"] += 1
        p["total_duration_s"] = round(p["total_duration_s"] + s["duration_s"], 2)
        p["peak_group_rss_mb"] = max(p["peak_group_rss_mb"], s["peak_group_rss_mb"])
        p["cpu_s"] = round(p["cpu_s"] + s["cpu_s"], 2)
        p["n_processes"] += s["n_processes"]
    _write(os.path.join(out, "summary_by_package.csv"), list(pkgs.values()))

    # per pytest test (needs recorder events) ------------------------------------
    windows = load_events(events_glob)
    if windows:
        by_pid = defaultdict(list)
        for r in rows:
            by_pid[int(r["pid"])].append(r)
        tests = []
        for pid, wins in windows.items():
            samples = by_pid.get(pid, [])
            for t0, t1, nodeid, package in wins:
                inside = [r for r in samples if t0 <= _f(r["t"]) <= t1 + interval]
                cpu = [(_f(r["cpu_user_s"]) + _f(r["cpu_sys_s"])) for r in inside]
                tests.append({
                    "package": package, "test_id": nodeid, "duration_s": round(t1 - t0, 3),
                    "samples": len(inside),
                    "peak_rss_mb": max((_f(r["rss_mb"]) for r in inside), default=""),
                    "cpu_s_approx": round(cpu[-1] - cpu[0], 2) if len(cpu) > 1 else "",
                })
        _write(os.path.join(out, "summary_by_test.csv"), tests)

    print(f"[monitor] {len(rows)} samples, {len(procs)} processes, {len(step_rows)} steps -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--interval", type=float, default=0.5, help="sampling interval in seconds (default 0.5)")
    ap.add_argument("--root-pid", type=int, help="monitor this process and all its descendants")
    ap.add_argument("--events-glob", help="glob of pytest recorder event files (*/pytest/*_test_events.jsonl)")
    ap.add_argument("--summarize-only", action="store_true", help="only rebuild summaries of --out")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- command to run and monitor")
    a = ap.parse_args()

    if a.summarize_only:
        summarize(a.out, a.interval, a.events_glob)
        return 0
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    child = None
    if cmd:
        child = subprocess.Popen(cmd)
        root = child.pid
    elif a.root_pid:
        root = a.root_pid
    else:
        ap.error("give either --root-pid PID or -- command ...")

    mon = Monitor(root, a.out, a.interval)
    with open(os.path.join(a.out, "monitor_info.json"), "w") as fh:
        json.dump({"root_pid": root, "cmd": cmd, "interval_s": a.interval, "started": mon.t0,
                   "cpu_count": psutil.cpu_count(), "ram_total_mb": round(psutil.virtual_memory().total / MB)},
                  fh, indent=2)
    mon.run()
    rc = child.wait() if child else 0
    summarize(a.out, a.interval, a.events_glob)
    return rc


if __name__ == "__main__":
    sys.exit(main())
