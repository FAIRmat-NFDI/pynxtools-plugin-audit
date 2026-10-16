# pynxtools-ellips: parser audit

Status: **draft, based on static reading of the source** (manual review of the parser, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-ellips`. Nothing here was confirmed by running the parser on real files unless a section says so.

This folder documents how the parser of `pynxtools-ellips` turns a J.A. Woollam ellipsometry export into the `NXellipsometry` data model: how the file is recognised, how the column layout is obtained, how the table is sliced into arrays per angle of incidence and data type, which formulas and unit conversions are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

The plugin currently has **one parser**, `woollam.py`, which derives from `_EllipsParser` (`pynxtools_ellips/parsers/base.py`, **not supplied**). Unlike most parsers in this audit, the file does not describe its own layout: column names, separator, number of header lines, the derived-parameter type and the plot name come from the ELN YAML, which the reader passes to the parser as `header_config`.

## Contents

| File | Format | Parser |
|---|---|---|
| [ellips_plugin_woollam_parser.md](ellips_plugin_woollam_parser.md) | J.A. Woollam VASE / CompleteEASE `.dat` | `woollam.py` |

## Parsers at a glance

Source code: [pynxtools-ellips on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-ellips/tree/develop) (links point to the `develop` branch; the inspected version is the one of 15th October 2026, the cloned branch head being `95c2547` of 13th October 2026). The reader class is `EllipsometryReader` with `supported_nxdls = ["NXellipsometry"]` (`src/pynxtools_ellips/reader.py` l. 88), registered as the `ellips` entry point. The document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| Woollam `.dat` | spectroscopic ellipsometry, Ψ/Δ and derived parameters by angle of incidence / `NXellipsometry` | `pandas.read_csv(header=None, names=colnames, skiprows=skip, delimiter=sep)` | [woollam.py](https://github.com/FAIRmat-NFDI/pynxtools-ellips/blob/develop/src/pynxtools_ellips/parsers/woollam.py) |

Besides `woollam.py`, the `parsers/` folder holds only `base.py` and `__init__.py`.

## Context

- Plugin: `pynxtools-ellips` (public). Application definition: `NXellipsometry`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** `woollam.py` (268 lines) was read in full. The document has the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin.
3. **Conventions.** Line numbers (`woollam l.`) refer to the source version that was inspected and will drift with later commits.
4. **Inherited code.** Not read: `_EllipsParser` (how `header_config` reaches `_parse(**kwargs)` and how `self.data` is consumed is inferred from `woollam.py`), the reader, the JSON config, and `pynxtools.dataconverter.helpers.extract_atom_types`.

## Summary of how the parser builds the data arrays

| Step | Rule | Where |
|---|---|---|
| Detection | `VASEmethod[` in the first five lines | woollam l. 59–67 |
| Layout | defaults `{"sep": "\t", "skip": 0}` merged with ELN header; `"\\t"` is unescaped with `unicode_escape` | woollam l. 33, 70–79 |
| Angle blocks | distinct angles with `np.unique`; `E` rows counted by the `type` column | woollam l. 187–195 |
| Data arrays | `[angle, data type, point]` for values and errors, taken from block offsets (`block_idx[index + 6]`) | woollam l. 205–262 |
| Derived parameter | extra array of type `derived_parameter_type` from the ELN | woollam l. 89–132 |
| Spectrum axis | `spectrum_type`, `spectrum_unit` from the ELN; only `Angstroms` → `angstrom` is mapped | woollam l. 107–120 |
| Long name | always ends with `(degree)` | woollam l. 132 |
| Post-processing | `atom_types` via `extract_atom_types` | woollam l. 138 |

## Cross-cutting observations

With one parser the observations below concern the parser's assumptions about its input and about the ELN contract rather than differences between parsers.

1. **Hidden dependency on the ELN.** The file does not carry its layout; `colnames`, `sep`, `skip`, `derived_parameter_type`, `Data.spectrum_type`, `Data.spectrum_unit`, `Data.data_type` and `plot_name` are read with `[]` (woollam l. 92, 98–101, 118, 170), so a missing key raises `KeyError`. Required columns (`type`, `angle_of_incidence`, `err.<type>`) are not named in the docstring (woollam l. 37–47, 189–190, 261).
2. **Block layout is assumed, not checked.** Equal number of points per angle, all `E` rows first and contiguous, ascending angles, and a magic offset of 6 blocks (woollam l. 189–193, 228, 241–255). `np.empty` arrays stay uninitialised when a slice is shorter than expected (woollam l. 238–239).
3. **Possible off-by-one in the NaN search.** After one NaN column the validated column differs from the one used at woollam l. 227 (woollam l. 217–223).
4. **Angle handling truncates.** Angles go through `astype("int64")` and `int(angle)` (woollam l. 182, 192), so 65.2° and 65.7° merge and the block size is wrong.
5. **Last-row index can exceed the table length** when `len(whole_data)` is not a multiple of `counts[0]` (woollam l. 212–214).
6. **Unit and name labels are hard-coded.** `(degree)` on every long name (woollam l. 132), wrong for `tan(Ψ)/cos(Δ)` or Mueller data; only `Angstroms` is mapped (woollam l. 108–110); `spectrum_unit` is not validated.
7. **Silent pandas behaviour.** More columns than `colnames` makes `read_csv` use the extra leading columns as the index and shift the names (woollam l. 157–164).
8. **Detection is narrow.** `VASEmethod[` must appear in the first five lines (woollam l. 64); other Woollam export variants are not recognised.
9. **Duplicated checks.** `colnames/skip/sep` are tested twice for different keys (woollam l. 71–72 vs 149–152) and the separator unescape only happens when `sep` is in `header_config` (woollam l. 76).

## Out of scope in this folder

Not documented here: `parsers/base.py`, the reader entry point (`EllipsometryReader`), the JSON config and ELN models, `extract_atom_types`, and the `NXellipsometry` application definition itself. Findings that depend on them are marked as inferred in the document.
