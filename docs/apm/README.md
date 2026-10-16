# pynxtools-apm: parser audit

Status: **draft, based on static reading of the source** (manual review of the four parsers, with line numbers). No scanner run and no runtime conversion was performed for `pynxtools-apm`. Nothing here was confirmed by running the parsers on real files unless a section says so.

This folder documents how each parser of `pynxtools-apm` turns atom-probe data and its context into the `NXapm` data model: which file suffixes are accepted, which third-party reader decodes them, which quantities are written to which template path, which unit and type conversions are applied, what is hard-coded, and what should be checked. It is one part of the wider pynxtools plugin audit (see "Context" below).

The four parsers are called from `reader.py` (`APMReader`, `supported_nxdls = ["NXapm"]`, l. 33–36, 53, 106–113) and split into two groups:

1. **Data wrappers around `ifes_apt_tc_data_modeling`**, one reader per vendor format:
   - `ifes_reconstruction.py` for reconstructed or measured datasets (`.pos`, `.epos`, `.apt`, `.ato`, `.csv`, `.h5`, `.hdf5`, `.ops`, `.raw`, `_trimmed.txt`, `_xyz.txt`);
   - `ifes_ranging.py` for ranging definitions (`.env`, `.fig.txt`, `range_.h5`, `.analysis`, `.rng`, `.rrng`, `.hdf5`, `.analysisset`).
2. **YAML context parsers** that supply what vendor files lack: `oasis_eln.py` (per-experiment `eln_data.yaml`) and `oasis_config.py` (deployment-level `*.oasis.specific.yaml`).

## Contents

| File | Format | Parser |
|---|---|---|
| [ifes_reconstruction.md](ifes_reconstruction.md) | reconstruction / measurement files (11 formats) | `ifes_reconstruction.py` |
| [ifes_ranging.md](ifes_ranging.md) | ranging-definition files (8 formats) | `ifes_ranging.py` |
| [apm_oasis_eln.md](apm_oasis_eln.md) | NOMAD Oasis ELN dump `eln_data.yaml` / `eln_data.yml` | `oasis_eln.py` |
| [apm_oasis_config.md](apm_oasis_config.md) | NOMAD Oasis deployment config `*.oasis.specific.yaml` | `oasis_config.py` |

## Parsers at a glance

Source code: [pynxtools-apm on GitHub](https://github.com/FAIRmat-NFDI/pynxtools-apm) (links point to the `main` branch; the inspected version is the one of 15th October 2026, the cloned `main` head being `c839a42` of 26th June 2026). The reader class is `APMReader`, registered as the `apm` entry point. Each document has an "At a glance" section with the standard and special behaviour.

| Format | Technique / target | File reader | Source code |
|---|---|---|---|
| reconstruction `.pos`, `.epos`, `.apt`, `.ato`, `.csv`, `.h5` (pyccapt), `.hdf5` (Cameca), `.ops`, `.raw` (Stuttgart), `_trimmed.txt`, `_xyz.txt` | positions, mass-to-charge, voltages, hit positions, detector and pulser data / `NXapm` | one `ifes_apt_tc_data_modeling` reader per format | [ifes_reconstruction.py](https://github.com/FAIRmat-NFDI/pynxtools-apm/blob/main/src/pynxtools_apm/parsers/ifes_reconstruction.py) |
| ranging `.env`, `.fig.txt`, `range_.h5`, `.analysis`, `.rng`, `.rrng`, `.hdf5`, `.analysisset` | ion types, mass-to-charge ranges, nuclide lists, charge states / `NXapm` ranging (`NXion`, `peak_identification`) | one `ifes_apt_tc_data_modeling` reader per format, one shared writer | [ifes_ranging.py](https://github.com/FAIRmat-NFDI/pynxtools-apm/blob/main/src/pynxtools_apm/parsers/ifes_ranging.py) |
| `eln_data.yaml` | sample, specimen, users, instrument, laser, workflow / `NXapm` | `yaml.safe_load` → `FlatDict` | [oasis_eln.py](https://github.com/FAIRmat-NFDI/pynxtools-apm/blob/main/src/pynxtools_apm/parsers/oasis_eln.py) |
| `*.oasis.specific.yaml` | citation, project, coordinate systems, users, start time / `NXapm` | `yaml.safe_load` → `FlatDict` | [oasis_config.py](https://github.com/FAIRmat-NFDI/pynxtools-apm/blob/main/src/pynxtools_apm/parsers/oasis_config.py) |

The `parsers/` folder also holds `hfive_base.py`, which was not reviewed. Other folders: `concepts/` (mapping functors), `configurations/` (mapping tables), `nomad/`, `examples/`, `utils/`.

## Context

- Plugin: `pynxtools-apm` (public). Application definition: `NXapm`.
- Task: for every reader/parser/handler in a pynxtools plugin, document input formats, processing, unit conversions, mathematical transformations, metadata mapping and assumptions, compare them with the NeXus application definition and format specifications, and record non-standard behaviour with evidence from source code, tests or documentation.
- General pynxtools documentation used as background:
  - https://fairmat-nfdi.github.io/pynxtools/tutorial/build-a-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/build-a-plugin.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/using-pynxtools-test-framework.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html
  - https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-with-nomad.html
  - https://fairmat-nfdi.github.io/pynxtools/learn/pynxtools/architecture.html

## How the analysis was done

1. **Manual review.** Each parser was read in full from the `main` branch of 15th October 2026 (`ifes_reconstruction.py` 1011 lines, `ifes_ranging.py` 475, `oasis_eln.py` 224, `oasis_config.py` 171). The four documents share the sections *At a glance*, *Formula / transformation*, *Standard behaviour*, *Special behaviour*, *Behaviour to investigate* and *Scanner findings*.
2. **No static scanner.** The scanner used for `pynxtools-xps` was not run on this plugin, so every "Scanner findings" section says so.
3. **Conventions.** Line numbers (`recon l.`, `rng l.`, `eln l.`, `cfg l.`) refer to the source version that was inspected and will drift with later commits.
4. **External and inherited code.** Not read: the `ifes_apt_tc_data_modeling` readers (all file decoding happens there), `add_specific_metadata_pint`, the mapping tables in `pynxtools_apm.configurations`, `parse_composition_table`, `prioritized_axes_heuristic`, `get_sha256_of_file_content`, and `hfive_base.py`.

## Summary of what each data wrapper writes

| Parser | Dispatch | Writer | Typical content |
|---|---|---|---|
| `ifes_reconstruction.py` | eleven independent `if` statements on the file suffix (recon l. 980–1009) | each format has its own function and writes its own subset | positions (N×3), mass-to-charge, voltages, raw/calibrated time of flight, hit positions (N×2), pulser, stage, detector, voltage curve (`.ops`), mass spectrum (Stuttgart) |
| `ifes_ranging.py` | first matching suffix from `VALID_FILE_NAME_SUFFIX_RANGE` (rng l. 360–367) | seven near-identical extract functions feed one shared writer | `ionID[ion<n>]/{nuclide_hash, charge_state, mass_to_charge_range, nuclide_list, name}`, optional `charge_state_analysis`, plus `specimen/atom_types` |

## Summary of what the YAML parsers write

| Parser | Gate | Stages | Overwrite and identifier rule |
|---|---|---|---|
| `oasis_eln.py` | name ends with `eln_data.yaml` / `.yml` (eln l. 65) | composition, atom types, users (+ ORCID), pulser sources, then eleven mapping tables | table writes use the fixed identifier `[entry_id, 1]` and can replace earlier output (eln l. 204–222) |
| `oasis_config.py` | name ends with `.oasis.specific.yaml` / `.yml` (cfg l. 39–41) | SHA-256 hash, coordinate systems, citation (first only), project, description, users, start time | the description is written after the project mapping and replaces any `experiment_description` it produced (cfg l. 143–151) |

## Cross-cutting observations

These points appear in more than one parser. Each is a candidate for a single check or fix.

1. **Non-deterministic `atom_types`.** Both `ifes_ranging.py` (rng l. 399) and `oasis_eln.py` (eln l. 131) write `", ".join(list(set))`, whose order changes between interpreter runs, and both can write `specimen/atom_types`, so the final value depends on call order in the reader. Sorting would make output reproducible.
2. **`supported` is unset or a constructor crashes for wrong file names.** `oasis_config.py` leaves `supported` unset (cfg l. 52–55, 72); `oasis_eln.py` never sets `self.file_path` and raises `AttributeError` at `open(self.file_path)` (eln l. 70).
3. **YAML errors are not caught.** `yaml.YAMLError` and an empty file (`safe_load` returns `None`, then `FlatDict(None)` fails) in both Oasis parsers (eln l. 71; cfg l. 61); the "support check" accepts any readable YAML (cfg l. 65).
4. **Type assumptions on YAML values.** `specimen/atom_types` is assumed to be a string (`.split(",")`, eln l. 124); `user` is assumed to be a list of dicts, otherwise silently ignored (cfg l. 155–156); a list-valued `author` is written as its Python repr (cfg l. 138); laser `power`, `pulse_energy`, `wavelength` are read without an `in` check and raise `KeyError` (eln l. 187).
5. **Same recipe, partly different bugs.** The experiment-description text, the single-citation `break` and the dead `cite_id` counter are shared with `pynxtools-em` and `pynxtools-microstructure` (cfg l. 105–151); a fix should be applied to all three. The ORCID is typed as `DOI` (eln l. 158), as in the `pynxtools-em` ELN parser.
6. **Unit handling is by formatting or by assumption.** `@units` come from pint formatting (recon l. 63; rng l. 113) while `"Da"` and `"s"` are hard-coded for mass and half-lives (rng l. 76, 143, 163, 170, 202, 230); in the ELN parser the `@units` lines for composition are commented out and `ppm` and `ppb` are accepted as `at.-%` without scaling (eln l. 90–116).
7. **Float32 everywhere in the data wrapper.** Positions, mass-to-charge, voltages and times are cast to `float32` and counters to `uint32` (recon l. 56, 159, 191, 206), losing precision for `float64` sources and truncating or wrapping fractional or negative counts (recon l. 895).
8. **Mass-spectrum min/max written as arrays.** `min_mass_to_charge` and `max_mass_to_charge` are both set to `np.float32(m_z[0].magnitude)`, the whole axis array, not a minimum and a maximum (recon l. 879–882). The bin width assumes a uniform axis from the first two values (recon l. 889, 916).
9. **Silent partial results.** A `None` quantity is only logged as a warning, so a valid template without reconstruction can result (recon l. 65); an unknown composition `normalization` drops all elements (eln l. 103–104); a laser block without details only logs a misleading message (eln l. 165–167, 199); a ranging file with no valid nuclide list skips `atom_types` silently (rng l. 400–402).
10. **Name and signature clashes across modules.** `extract_data_from_cameca_hfive_file` exists in both wrappers with different signatures (recon l. 678; rng l. 320). `.hdf5` means a reconstruction in one and a ranging in the other, and suffix dispatch is ambiguous for `.csv`, `.h5`, `.hdf5`, `.raw` and `.ops` (recon l. 988–995).
11. **Large repetition.** The block "read → cast → chunk → units → warn → del" appears about 45 times in the reconstruction wrapper (recon l. 237–238), seven near-identical extract functions exist in the ranging wrapper (rng l. 248–347), and the Oasis stages are the same loop with different tables.
12. **Reader-side warnings are advisory only.** More than 256 ion definitions logs a warning in each of eight copies and the message uses a constant different from the literal 256 in the check (rng l. 57, 252–253).
13. **Verbose logging can expose private fields.** With `verbose=True` both Oasis parsers log every key and value (eln l. 72–74; cfg l. 62–64), and the hash is only logged and not stored (cfg l. 74–77).
14. **Placeholders left in code.** Commented-out plot blocks for hundreds of millions of values (recon l. 386–414), TODOs for multiplicity data (recon l. 217–218, 469, 511, 673), a disabled `min_abundance_product` entry (rng l. 137–139).

## Out of scope in this folder

Not documented here: `reader.py` (`APMReader`), `hfive_base.py`, the `ifes_apt_tc_data_modeling` library, `concepts/mapping_functors_pint.py`, the mapping tables in `configurations/`, `nomad/` and `examples/`, `utils/`, and the `NXapm` application definition. Findings that depend on them are marked as inferred in the individual documents.
