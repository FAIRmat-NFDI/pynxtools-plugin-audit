"""Usage: replay_convert.py CALL.json OUTPUT.nxs"""
import json, logging, os, sys

rec = json.load(open(sys.argv[1]))
call = dict(rec["call"])
call["output"] = os.path.abspath(sys.argv[2])
if rec.get("cwd") and os.path.isdir(rec["cwd"]):
    os.chdir(rec["cwd"])  # relative input paths resolve as they did in the test
if isinstance(call.get("input_file"), list):
    call["input_file"] = tuple(call["input_file"])
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
print("Replaying conversion from test:", rec.get("test_id"))
print(json.dumps(call, indent=2, default=str), flush=True)
from pynxtools.dataconverter.convert import convert
convert(**call)
print("Conversion finished:", call["output"])
