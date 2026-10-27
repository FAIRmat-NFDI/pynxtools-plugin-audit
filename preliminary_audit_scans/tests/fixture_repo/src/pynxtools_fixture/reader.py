import pickle
import subprocess
import tarfile
import numpy as np
import yaml
from lxml import etree
import xml.etree.ElementTree as ET
from pint import UnitRegistry

ureg = UnitRegistry()

MAP = {
    "map_to_f8": [
        ("energy", ureg.electron_volt, "src/energy", ureg.meter),   # U09 + U10
        ("working_distance", ureg.meter, "src/wd"),                  # U11
    ],
}
UNITS = {
    "temperature": "C",        # U08 high + U10
    "particle_charge": "C",    # fine: C is a charge here
    "intensity": "au",         # U08
    "rate": "c/s",             # U08
}


def read(template, path, opts):
    template["/ENTRY[entry]/data/energy/@units"] = "eV "           # U06 + U05
    template["/ENTRY[entry]/sample/temperature/@units"] = "eV"     # U06 + U10
    data = pickle.load(open(path, "rb"))                           # S02
    cfg = yaml.load(open(path))                                     # S03
    subprocess.run("ls " + path, shell=True)                       # S04
    tarfile.open(path).extractall("out")                           # S05
    tree = etree.parse(path)                                        # S06 medium
    ET.parse(path)                                                  # S06 low
    eval(opts.get("expr", "1"))                                     # S01 + D01
    img = np.rot90(data).T                                          # A04
    small = data.astype(np.float32)                                 # N07
    d = {"a": 1, "a": 2}                                            # K01
    try:
        x = 1 / 0
    except Exception:                                               # E02
        pass
    return data[::-1] * 1e3                                          # A01 + N01
