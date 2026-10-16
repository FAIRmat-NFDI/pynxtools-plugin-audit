# pynxtools-xrd: parser audit

Status: **draft, based on static reading of the source** (manual review of two reader modules, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-xrd` or `readers-xrd`. Nothing here was confirmed by running the readers on real files unless a section says so.

This folder documents how `pynxtools-xrd` obtains X-ray diffraction data for `NXxrd_pan`. The plugin itself (`pynxtools_xrd/reader.py`, `XRDReader`) is thin: it imports `read_file` from the separate package [readers-xrd](https://github.com/FAIRmat-NFDI/readers-xrd) (`fairmat_readers_xrd`), and that package holds the actual file parsers. Two of them are documented here:

1. **Rigaku RASX and Bruker BRML** (`ikz.py`): ZIP archives of XML/ASCII, adapted from `IKZ/xray/io.py`; two classes with a shared set of accessor methods.
2. **Siemens/Bruker RAW v4** (`bruker_raw_parser.py`): an undocumented binary layout read at fixed byte offsets, based on reverse engineering.

## Contents

| File | Format | Parser |
|---|---|---|
| [ikz.md](ikz.md) | Rigaku `.rasx` and Bruker `.brml` (ZIP of XML/ASCII) | `ikz.py` (`RASXfile`, `BRMLfile`) |
| [bruker_raw_parser.md](bruker_raw_parser.md) | Siemens/Bruker RAW v4 binary `.raw` | `bruker_raw_parser.py` (`BrukerRAW4Parser`) |

## Parsers at a glance

Source code: [pynxtools-xrd](https://github.com/FAIRmat-NFDI/pynxtools-xrd) and [readers-xrd](https://github.com/FAIRmat-NFDI/readers-xrd/tree/main). The reader class is `XRDReader` with `supported_nxdls = ["NXxrd_pan"]` and `supported_formats = [".rasx", ".xrdml", ".brml"]` (`src/pynxtools_xrd/reader.py` l. 128–129), registered as the `xrd` entry point. Dispatch happens in `read_file()` in `fairmat_readers_xrd/readers.py` l. 46–64 by file-name suffix: `.rasx`, `.xrdml`, `.brml`, `.raw`; anything else raises `NotImplementedError`. Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| Rigaku `.rasx` | powder / thin-film XRD, RSM / `NXxrd_pan` | `zipfile`, `np.loadtxt`, `ElementTree` | [ikz.py](https://github.com/FAIRmat-NFDI/readers-xrd/blob/main/src/fairmat_readers_xrd/ikz.py) |
| Bruker `.brml` | XRD / `NXxrd_pan` | `zipfile`, `xmltodict` | [ikz.py](https://github.com/FAIRmat-NFDI/readers-xrd/blob/main/src/fairmat_readers_xrd/ikz.py) |
| Siemens/Bruker `.raw` (RAW4.00) | θ–2θ powder scans written by DIFFRAC.EVA / `NXxrd_pan` | `struct.unpack` at fixed offsets | [bruker_raw_parser.py](https://github.com/FAIRmat-NFDI/readers-xrd/blob/main/src/fairmat_readers_xrd/bruker_raw_parser.py) |
| PANalytical `.xrdml` | XRD / `NXxrd_pan` | `read_panalytical_xrdml()` in `readers.py` | [readers.py](https://github.com/FAIRmat-NFDI/readers-xrd/blob/main/src/fairmat_readers_xrd/readers.py) (**not documented here**) |

Note: in the cloned `readers-xrd` repository (main) `ikz.py`, `bruker_raw_parser.py` and `readers.py` sit in `src/fairmat_readers_xrd/`; the head of `pynxtools-xrd` inspected for the reader details is the `develop` commit `ba9b33a` of 13th October 2026. `bruker_raw_parser.py` is standalone: it has no pynxtools imports and no entry point.

## Context

- Plugins: `pynxtools-xrd` and `readers-xrd` (public). Application definition: `NXxrd_pan`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** `ikz.py` (553 lines) and `bruker_raw_parser.py` (420 lines) were read in full from the development branches of 15th October 2026. Both documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin.
3. **Conventions.** Line numbers (`ikz l.`, `raw l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited and external code.** Not read: `XRDReader`, `read_file()` and the other readers in `readers.py` (including `read_panalytical_xrdml`, `read_rigaku_rasx`, `read_bruker_brml`, `read_bruker_raw`), `fairmat_readers_xrd.utils` (`to_pint_quantity`), the JSON config, the test fixtures, and `xmltodict`.

## Summary of how the parsers read scan data and metadata

| Format | Access | Axis / angles | Units | Source info |
|---|---|---|---|---|
| RASX | `Profile*.txt` loaded with `np.loadtxt` (N×3), images, metadata XML | 2θ, intensity, third column; axis positions collapsed to scalars when constant | `to_pint_quantity` from XML units | `TargetName, Voltage, Current, WavelengthKalpha1/2, WavelengthKbeta` (ikz l. 299–316) |
| BRML | `DataContainer.xml` and `RawData*.xml`, `Datum` matrices cut by `DataView` | scan axis reconstructed from start/stop/increment (ikz l. 394–398) | `to_pint_quantity` | `TubeMaterial, Voltage, Current, WaveLengthAlpha1/2/Beta/Ratio` (ikz l. 520–550) |
| RAW v4 | whole file read, fixed-offset `struct.unpack` | angles **computed** from start angle and step, not read | assumed degrees and counts, nothing read from the file | anode material at 0x01A8, five text tags searched globally |

## Cross-cutting observations

1. **Positional assumptions without validation.** RAW v4 depends on fixed offsets (point count at 0x01C3 as uint16, step at 0x020F, anode at 0x01A8; raw l. 235–288); the intensity block is read to the end of the file and not limited by `num_points` (raw l. 324–337). BRML assumes a single `DataRoute` and a defined `nsteps` (ikz l. 354–362), RASX assumes equal-length scans for RSM (ikz l. 212–213).
2. **Missing keys crash with unrelated exceptions.** `UnboundLocalError` for `start_angle` (raw l. 256–257, 311); `AttributeError`/`KeyError` for missing `HWConfigurations`, `Detector`, `RASHeader` elements (ikz l. 55–61); `IndexError` for zero counters (ikz l. 444–447); `KeyError` for `axtitle[i]` (ikz l. 123); `TypeError` in `get_RSM` for a missing axis (ikz l. 198, 220–224).
3. **Single-element XML collapses to a dict.** `mounted_optics_info` can be a dict rather than a list, so iterating it breaks `get_source_info` for a single optic (ikz l. 513–514).
4. **Time zone.** `time.mktime` interprets a UTC timestamp as local time (ikz l. 321–323); `calendar.timegm` would fix it. The RAW date and time are read as plain strings (raw l. 161–173).
5. **Unit labels are assumed or wrong.** RAW assumes degrees and counts (raw l. 246, 255, 314, 370); the BRML wavelength ratio gets a length unit (ikz l. 537–550); the docstrings of `get_source_info` still describe `[value, unit]` lists although `pint` quantities are returned (ikz l. 285–288, 502–505).
6. **Different keys for the same quantity.** Sample axes are `Omega, Chi, Phi, X, Y` in RASX and `Theta, Chi, Phi` in BRML; `get_scan_info` returns the whole `ScanInformation` for RASX and only `ScanName` for BRML (ikz l. 259, 281, 467, 494–496); the RSM output key `Intensity` differs from `intensity` in `get_scan_data` (ikz l. 214, 251).
7. **Axis semantics.** RAW stores the axis name (for example `Theta`) but the XY output always labels the column `2Theta` (raw l. 266–267, 370). In BRML `scan_two_theta_value` is normalised and the original `Value` is passed on (ikz l. 455–461).
8. **Edge cases of the axis length.** For `nsteps == 1` the BRML axis has `n_int` points including the endpoint and `Increment == 0` raises `ZeroDivisionError` (ikz l. 394–398); the RAW point count is limited to 65 535 by `<H` (raw l. 235).
9. **Deprecated or inefficient numerics.** `np.fromstring` on binary data (ikz l. 188) and `struct.unpack` of the full tail into Python lists (raw l. 330–337); `numpy.frombuffer` is the usual replacement.
10. **Text handling.** RAW tag search scans the whole remainder of the file, including the float block, and values are read in a fixed 200-byte window (raw l. 176, 199, 204–206); `convert_raw_to_xy` writes `°` with the platform default encoding (raw l. 366–370).
11. **Provenance and licence.** `bruker_raw_parser.py` has an MIT header and "Generated for NOMAD" (raw l. 11–12), unlike the Apache-2.0 headers elsewhere; `ikz.py` is adapted from `IKZ/xray/io.py` by Dr. Carsten Richter (ikz l. 1–5) and the upstream licence should be checked.
12. **Scope noise and stale text.** The RAW parser logs its scope warning for every valid file (raw l. 135–139); stale docstrings and an unused flag (raw l. 156–158) remain.

## Out of scope in this folder

Not documented here: `pynxtools_xrd/reader.py` (`XRDReader`), `fairmat_readers_xrd/readers.py` including the PANalytical `.xrdml` reader, `utils.py`, the JSON config and ELN models, the third-party libraries, and the `NXxrd_pan` application definition. Findings that depend on them are marked as inferred in the individual documents.
