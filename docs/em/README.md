# pynxtools-em: parser audit

Status: **draft, based on static reading of the source** (manual review of the parsers, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-em`. Nothing here was confirmed by running the parsers on real files unless a section says so.

This folder documents how each parser of `pynxtools-em` turns electron-microscopy data into the `NXem` data model: how a file is recognised, which library reads it, which metadata and arrays are mapped to which template paths, which formulas and unit conversions are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

Unlike `pynxtools-xps` and `pynxtools-spm`, the `pynxtools-em` parsers are **not documented one file per format**. The 25 source files fall into five families that share a base class, a detection pattern and a way of writing the template, so each document covers one family and contains a per-parser section:

1. **HDF5 vendor parsers** (`HdfFiveBaseParser` and seven subclasses): EBSD and EDS maps, normalised through the shared `EbsdPointCloud` model.
2. **Image parsers** (PNG sets and vendor TIFF): identification is metadata-led, not extension-led.
3. **rosettasciio-backed parsers** (`rsciio_*`): the file is read by `rsciio`, the parser maps its metadata and axes.
4. **Nion Swift project parser** (`nxs_nion.py`): a zipped or unzipped project with `.ndata`/`.h5` members.
5. **Oasis ELN and config parsers**: YAML files that supply the context vendor files lack.

## Contents

| File | Family | Parsers covered |
|---|---|---|
| [hdf5_vendor_parsers.md](hdf5_vendor_parsers.md) | HDF5, EBSD / EDS | `hfive_base.py`, `hfive_apex.py`, `hfive_bruker.py`, `hfive_dreamthreed_legacy.py`, `hfive_ebsd.py`, `hfive_edax.py`, `hfive_emsoft.py`, `hfive_oxford.py` |
| [image_parsers.md](image_parsers.md) | PNG and TIFF images | `image_png_protochips.py`, `image_tiff.py`, `image_tiff_fei_legacy.py`, `image_tiff_hitachi.py`, `image_tiff_jeol.py`, `image_tiff_point_electronic.py`, `image_tiff_tescan.py`, `image_tiff_tfs.py`, `image_tiff_zeiss.py` |
| [rsciio_parsers.md](rsciio_parsers.md) | rosettasciio-backed | `rsciio_velox.py`, `rsciio_gatan.py`, `rsciio_msa.py`, `rsciio_mrc.py`, `rsciio_bruker.py` |
| [nxs_nion.md](nxs_nion.md) | Nion Swift project | `nxs_nion.py` |
| [oasis_eln_config_parsers.md](oasis_eln_config_parsers.md) | NOMAD Oasis YAML | `oasis_eln.py`, `oasis_config.py` |

## Parsers at a glance

Source code: [pynxtools-em on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop) (links point to the `develop` branch; the inspected commit is `340f154` of 13th October 2026). The reader class is `EMReader` (`supported_nxdls = ["NXem"]`, `src/pynxtools_em/reader.py` l. 71–74), registered as the `em` entry point in `pyproject.toml`. Documentation: [pynxtools-em docs](https://fairmat-nfdi.github.io/pynxtools-em/) (link not verified). Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / content | File reader | Source code |
|---|---|---|---|
| EDAX / AMETEK APEX `.edaxh5` | EBSD, EDS field of view, spectra | `h5py` | [hfive_apex.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_apex.py) |
| Bruker ESPRIT `.h5` | EBSD | `h5py` | [hfive_bruker.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_bruker.py) |
| DREAM.3D legacy `.dream3d` | EBSD-derived content (detected and normalised in memory, not yet written) | `h5py` | [hfive_dreamthreed_legacy.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_dreamthreed_legacy.py) |
| Community H5EBSD `.h5`, `.h5ebsd` | EBSD | `h5py` | [hfive_ebsd.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_ebsd.py) |
| EDAX OIM Analysis `.oh5`, `.h5` | EBSD | `h5py` | [hfive_edax.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_edax.py) |
| EMsoft HDF5 | detection only (parse is TODO) | `h5py` | [hfive_emsoft.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_emsoft.py) |
| Oxford Instruments `.h5oina` | EBSD, feature areas, EDS composition | `h5py` | [hfive_oxford.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/hfive_oxford.py) |
| Protochips heating-chip PNG set in a ZIP | image sequence with events | `zipfile`, Pillow | [image_png_protochips.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_png_protochips.py) |
| FEI / Thermo Fisher legacy TIFF | SEM / TEM images | `mmap`, Pillow | [image_tiff_fei_legacy.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_fei_legacy.py) |
| Hitachi TIFF + same-stem TXT | SEM / TEM images | `mmap`, Pillow, text sidecar | [image_tiff_hitachi.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_hitachi.py) |
| JEOL TIFF (+ optional TXT) | SEM / TEM images | `mmap`, Pillow | [image_tiff_jeol.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_jeol.py) |
| Point Electronic DISS TIFF | images | `mmap`, Pillow | [image_tiff_point_electronic.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_point_electronic.py) |
| TESCAN TIFF (+ optional HDR) | SEM images | `mmap`, Pillow | [image_tiff_tescan.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_tescan.py) |
| ThermoFisher TIFF | SEM images | `mmap`, Pillow | [image_tiff_tfs.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_tfs.py) |
| Zeiss TIFF | SEM images | `mmap`, Pillow | [image_tiff_zeiss.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/image_tiff_zeiss.py) |
| Velox `.emd` | images, spectra, spectrum images | `rsciio.emd` | [rsciio_velox.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/rsciio_velox.py) |
| Gatan `.dm2` / `.dm3` / `.dm4` | images, spectra | `rsciio.digitalmicrograph` | [rsciio_gatan.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/rsciio_gatan.py) |
| (E)MSA `.msa` | single 1D spectrum | `rsciio.msa` | [rsciio_msa.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/rsciio_msa.py) |
| MRC `.mrc` + sidecar | image stacks | `rsciio.mrc` | [rsciio_mrc.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/rsciio_mrc.py) |
| Bruker (rsciio) | spectra / images | `rsciio` | [rsciio_bruker.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/rsciio_bruker.py) |
| Nion Swift project `.zip` / `.nsproj` | images, spectra, generic NXdata | `zipfile`, `mmap`, `h5py`, `yaml` | [nxs_nion.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/nxs_nion.py) |
| `eln_data.yaml` | user, sample, instrument context from the NOMAD ELN | `yaml` | [oasis_eln.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/oasis_eln.py) |
| `*.oasis.specific.yaml` | deployment context (citation, project, users, coordinate systems) | `yaml` | [oasis_config.py](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/oasis_config.py) |

Note: `hfive_base.py` is the shared HDF5 visitor, cache and report helper and is not a format parser. A short [parsers/README.md](https://github.com/FAIRmat-NFDI/pynxtools-em/blob/develop/src/pynxtools_em/parsers/README.md) in the source tree only states that the folder holds parsers for files from technology partners.

## Context

- Plugin: `pynxtools-em` (public). Application definition: `NXem`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** The parsers were read from the `develop` branch (commit `340f154`, 13th October 2026; the five documents give 13th/14th October). The five documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour* and *Behaviour to investigate* (called *maintenance checklist* in the HDF5 and image documents) and *Scanner findings* where present. [rsciio_parsers.md](rsciio_parsers.md) and [oasis_eln_config_parsers.md](oasis_eln_config_parsers.md) add a per-parser section for each file.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin, so *Scanner findings* sections say so.
3. **Conventions.** Line numbers (`l. N`) refer to the source version that was inspected and will drift with later commits. Statements marked *(docs)* come from project documentation, not from reading code.
4. **Inherited and external code.** Not read in full: `reader.py` beyond the class header, `pynxtools_em.concepts`, `pynxtools_em.utils` (checksum, unit and chunk helpers), the mapping tables in `configurations/`, the third-party libraries `rsciio`, `h5py`, `diffpy` and `Pillow`, and the test fixtures.

## Summary of how the parsers identify their input

| Family | Identity test | Failure mode when the test is too weak |
|---|---|---|
| HDF5 vendor | HDF5 magic bytes, then required root fields, groups, manufacturer and version strings (votes) | A different HDF5 schema or version is skipped; some tests accept on a single attribute (`hfive_apex.py` l. 126) |
| Image TIFF | TIFF magic `II*\x00` plus a vendor tag (JEOL 37500, TESCAN 50431, TFS 34682, Zeiss 34118) or an embedded signature | Some parsers set `supported = True` whenever metadata is non-empty after parsing |
| Image PNG | ZIP with PNG frames and `MicroscopeControlImage` metadata of matching size | none observed |
| rsciio | Suffix (and HDF5 magic and version fields for Velox) | Velox and Gatan read the entire file in the constructor; Gatan and MSA have no version gate |
| Nion | Zip or `.nsproj` suffix, then three tests on the project members | Empty file and missing-`data` cases raise (see [nxs_nion.md](nxs_nion.md)) |
| Oasis YAML | File-name suffix (`eln_data.yaml`, `.oasis.specific.yaml`) | Any YAML with that name is accepted; wrong names leave `supported` unset |

## Summary of how the parsers write data

| Family | Data written as | Axis and unit source |
|---|---|---|
| HDF5 vendor | `EbsdPointCloud` normalised, then `ebsd_roi_overview` / `ebsd_roi_phase_ipf` helpers; APEX and Oxford also write EDS content | per-vendor step sizes and units, version-specific for EDAX OIM (`hfive_edax.py` l. 325–350) |
| Image | `imageID[image<n>]/…` with `flipud`-ed pixel arrays; multipage TIFF gives several images | vendor pixel-size keys, converted with pint |
| rsciio | `spectrumID`, `imageID` or `DATA[data1]` chosen from the unit combination of the axes | `rsciio` axes (`offset + k·scale`), unit strings from the library |
| Nion | `spectrumID`, `imageID` or generic `DATA[data1]` | `unit_combination` and dimensional calibrations from the project |
| Oasis YAML | context groups only (user, sample, citation, project, coordinate systems) | not applicable |

## Cross-cutting observations

These points appear in more than one parser family. Each is a candidate for a single check or fix.

1. **Detection is loose in places.** Parsers that accept a file when *any* metadata was found, or on one matching attribute, can claim files that belong to another vendor. See [image_parsers.md](image_parsers.md) (maintenance checklist) and `hfive_apex.py` l. 126.
2. **Unreachable or unfinished parsers.** `hfive_ebsd.py` l. 101 compares `self.supported == 2` instead of `votes_for_support == 2`, so the parser is currently unreachable. `hfive_emsoft.py` detects only, `hfive_dreamthreed_legacy.py` normalises in memory but writes nothing (l. 332), and `rsciio_msa.py` handles a single 1D spectrum.
3. **Constructors read the whole file.** The rsciio parsers load the entire file in the constructor, and `nxs_nion.py` hashes every project member under the default `verbose=True` ([rsciio_parsers.md](rsciio_parsers.md) behaviour 1, [nxs_nion.md](nxs_nion.md) behaviour 1).
4. **Unhandled edge cases at the I/O boundary.**
   - `mmap` of an empty file raises `ValueError` in all TIFF readers (`image_tiff.py` l. 74) and in `nxs_nion.py` l. 118.
   - Missing sidecars or empty sidecars: Hitachi `IndexError` (`image_tiff_hitachi.py` l. 124), TESCAN unbound `txt` after `UnicodeDecodeError` (`image_tiff_tescan.py` l. 123–131), JEOL `decoded.split` on `None` (`image_tiff_jeol.py` l. 150–154), Zeiss `IndexError` (`image_tiff_zeiss.py` l. 115).
   - YAML errors are not caught in either Oasis parser; wrong file names leave `supported` unset (`oasis_config.py`) or raise `AttributeError` in the constructor.
5. **Separator mismatch for axis-name counts.** The unit combination is split on `_` in Velox (l. 359), Gatan (l. 243) and Nion (l. 574) while other code splits on `;` and the MRC keyword uses `;`. For generic data this can leave `axis_names[idx]` out of range. Needs a test with a multi-dimensional generic dataset (`nxs_nion.md`, behaviour 10; `rsciio_parsers.md`, behaviour 4).
6. **Event counter inconsistencies.** In the Gatan parser, event ids run 1, 3, 5, … because both the data function and `parse_content` increment (l. 123–125, 178). In the Nion parser, metadata is mapped before the data function can return early, so the next item writes into the same `eventID` (`nxs_nion.py` l. 315–318, 506–510).
7. **Axis-index formula has a TODO'd assumption.** The `axis_index` attribute is derived from an assumption that is only exercised with a note in the code; verify with a non-square image and a spectrum image in Velox, Gatan and MRC.
8. **Duplicated code.** Gatan builds the same `float32` axis twice (l. 263–315); MRC has three nearly identical writer functions (l. 562–841); `parse_citations`, `parse_notes`, `parse_reference_frames` and `parse_user` in the Oasis parsers are the same loop with different tables.
9. **Orientation and calibration.** `np.flipud()` is applied in the vendor TIFF pixel methods; the convention should be validated against the NeXus coordinate system. Oxford passes radian lattice angles to `diffpy.Lattice` (`hfive_oxford.py` l. 332–339, source TODO). Unitless Nion axes are cast to `int32` (`nxs_nion.py` l. 597–612), truncating non-integer scales.
10. **Non-deterministic or ambiguous output.**
    - `", ".join(list(unique_elements))` over a `set` makes `atom_types` order unstable (`oasis_eln.py` l. 135).
    - `sorted(list(...), key=int)` runs before the `isdigit()` filter in Bruker and community H5EBSD (`hfive_bruker.py` l. 164, `hfive_ebsd.py` l. 164).
    - An ORCID is typed as `DOI` (`oasis_eln.py` l. 158).
11. **Provenance is not uniform.** Source annotation differs across the rsciio parsers (see [rsciio_parsers.md](rsciio_parsers.md), general structure 9), so the origin of a dataset is recorded differently by format.
12. **Overwrite order.** Where the ELN and config parsers can write the same keys (user fields), the later stage wins, and `user_id` advances only for non-empty entries, so reordering the YAML changes ids.
13. **Family resemblance across plugins.** The Oasis config/ELN pattern is shared in structure with `pynxtools-apm` and `pynxtools-microstructure`, and `pynxtools-microstructure` imports helpers from `pynxtools_em`; a fix in one place should be applied to all three.

## Out of scope in this folder

Not documented here: the `EMReader` class and its dispatch order (a check of the order is listed in the HDF5 maintenance checklist), `concepts/` (mapping functors), `utils/` (checksum, units, chunking, logging), the `configurations/` mapping tables, the NOMAD example uploads, and the vendored behaviour of `rsciio`, `h5py`, `diffpy` and Pillow. Findings that depend on them are marked as inferred in the individual documents.
