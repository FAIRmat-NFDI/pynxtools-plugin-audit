"""Usage: measure.py RESULT.json TIMEOUT_S -- cmd args...  (stdout/stderr pass through)"""
import datetime, json, resource, subprocess, sys, time

out, timeout = sys.argv[1], float(sys.argv[2])
cmd = sys.argv[sys.argv.index("--") + 1:]
started = datetime.datetime.now().isoformat(timespec="seconds")
t0 = time.perf_counter()
timed_out = False
try:
    rc = subprocess.run(cmd, timeout=timeout).returncode
except subprocess.TimeoutExpired:
    rc, timed_out = 124, True
    print(f"[measure] TIMEOUT after {timeout:.0f} s: {cmd}", file=sys.stderr)
except FileNotFoundError as exc:
    rc = 127
    print(f"[measure] {exc}", file=sys.stderr)
wall = time.perf_counter() - t0
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
# ru_maxrss: kilobytes on Linux, bytes on macOS. Peak of the largest child process.
rss_bytes = ru.ru_maxrss if sys.platform == "darwin" else ru.ru_maxrss * 1024
with open(out, "w") as fh:
    json.dump(
        {
            "cmd": cmd,
            "started": started,
            "exit_code": rc,
            "timed_out": timed_out,
            "wall_s": round(wall, 3),
            "user_cpu_s": round(ru.ru_utime, 3),
            "sys_cpu_s": round(ru.ru_stime, 3),
            "peak_rss_mb": round(rss_bytes / 2**20, 1),
        },
        fh,
        indent=2,
    )
sys.exit(rc)
