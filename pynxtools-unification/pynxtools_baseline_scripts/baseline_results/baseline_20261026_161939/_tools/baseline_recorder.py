"""pytest plugin (-p baseline_recorder): append each convert() call to $BASELINE_RECORD_FILE."""
import functools, inspect, json, os, pathlib, sys, time

_ORIG = None


def _jsonable(obj, flags):
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, (pathlib.PurePath,)):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [_jsonable(o, flags) for o in obj]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v, flags) for k, v in obj.items()}
    flags["replayable"] = False
    return {"__repr__": repr(obj)}


def _wrap(orig):
    sig = inspect.signature(orig)
    var_kw = next((n for n, p in sig.parameters.items() if p.kind == p.VAR_KEYWORD), None)

    @functools.wraps(orig)
    def wrapper(*args, **kwargs):
        try:
            call = dict(sig.bind_partial(*args, **kwargs).arguments)
            if var_kw:
                call.update(call.pop(var_kw, {}) or {})
        except TypeError:
            call = {"__args__": list(args), **kwargs}
        status, t0 = "ok", time.perf_counter()
        try:
            return orig(*args, **kwargs)
        except BaseException as exc:  # recorded, then re-raised unchanged
            status = f"raised {type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            flags = {"replayable": True}
            rec = {
                "test_id": os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0],
                "cwd": os.getcwd(),
                "status_in_test": status,
                "seconds_in_test": round(time.perf_counter() - t0, 3),
                "call": _jsonable(call, flags),
            }
            rec["replayable"] = flags["replayable"] and "__args__" not in call
            path = os.environ.get("BASELINE_RECORD_FILE")
            if path:
                with open(path, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")

    wrapper.__baseline_wrapped__ = True
    return wrapper


def _patch_everywhere():
    global _ORIG
    try:
        import pynxtools.dataconverter.convert as mod
    except Exception as exc:
        print(f"[baseline_recorder] cannot import pynxtools: {exc}", file=sys.stderr)
        return
    if _ORIG is None:
        _ORIG = mod.convert
        mod.convert = _wrap(_ORIG)
    # modules that already did "from ...convert import convert"
    for m in list(sys.modules.values()):
        try:
            if getattr(m, "convert", None) is _ORIG:
                setattr(m, "convert", mod.convert)
        except Exception:
            pass


def pytest_configure(config):
    _patch_everywhere()


def _event(kind, nodeid):
    path = os.environ.get("BASELINE_EVENTS_FILE")
    if path:
        with open(path, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "event": kind, "nodeid": nodeid, "pid": os.getpid()}) + "\n")


def pytest_runtest_logstart(nodeid, location):
    _event("start", nodeid)


def pytest_runtest_logfinish(nodeid, location):
    _event("finish", nodeid)


def pytest_collection_finish(session):
    _patch_everywhere()
