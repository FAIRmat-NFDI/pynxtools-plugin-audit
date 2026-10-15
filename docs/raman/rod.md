# Raman Open Database `.rod` (CIF) parser (`pynxtools-raman`)

## Source files reviewed

- `pynxtools_raman/parsers/rod.py` — `RodParser` and `build_citation_fields()` (425 lines).
- Inherited: `_RamanParser` (`pynxtools_raman/parsers/base.py`). Behaviour attributed to it below (`matches_file` dispatch, `unused_attrs` handling, calling `_parse()` and `post_process()`) is inferred from names and usage in `rod.py` only.
- Companion mapping, **not supplied**: `config_file_rod.json` (named at rod l. 60).
- External: `gemmi` (CIF reader).
- Project: [pynxtools-raman repository](https://github.com/FAIRmat-NFDI/pynxtools-raman).

**Line-number note:** References below refer to the file in the develop branch on 15th October 2026. `rod l.` = `rod.py`.

## At a glance

| | |
|---|---|
| **Input format** | `.rod` file: a CIF record from the Raman Open Database (ROD), one `data_` block (rod l. 59, 92) |
| **Parser class** | `RodParser(_RamanParser)` (rod l. 51–357) |
| **Reader** | `gemmi.cif.read_file()` for values (rod l. 91) plus a plain-text line scan of the same file for key discovery (rod l. 85–86, 97–112) |
| **Raw-data storage** | `self.cif_doc`, `self.cif_block`, `self.lines` (rod l. 65–67); results in `self.data`, `self.attrs`, `self.unused_attrs` |
| **Output from parser** | `self.data`: `{"_raman_spectrum.raman_shift": [float…], "_raman_spectrum.intensity": [float…]}` (rod l. 232–236). `self.attrs`: flat dict of every other CIF key (strings, a few lists) plus synthetic keys (rod l. 237–319, 337–356) |
| **Config** | `config_file_rod.json` (rod l. 60); `unused_attrs_group_name = "unused_rod_keys"` (rod l. 61) |
| **Target definition** | NeXus Raman application definition (implied by the package; the NXDL name is not stated in this file) |
| **Project context** | [pynxtools-raman](https://github.com/FAIRmat-NFDI/pynxtools-raman). Only parser that reads a database record rather than an instrument export; the only one that emits NXcite instances. |

**Standard behaviour.** `matches_file` accepts any file with a `data_` line in the first 50 lines (rod l. 69–79). `_parse` loads the CIF, discovers every `_key` line by scanning the raw text, decides per key whether it is a single value or a `loop_` column, reads the values with gemmi, moves the two spectrum arrays into `self.data`, keeps everything else as attributes, then normalizes cell parameters, dates, environment and optics strings and adds citation fields (rod l. 227–319). `post_process` converts the spectral resolution from cm⁻¹ to nm and derives the grating period (rod l. 321–356).

**Comparison with other `pynxtools-raman` parsers.** `WitecParser` reads an instrument export with a hand-written line loop. `RodParser` reads a self-describing, key-addressed database record, so most of its code is key discovery and clean-up, not column handling.

## Formula / transformation

### Parser: spectral resolution from cm⁻¹ to nm

**Location:** `post_process()` (rod l. 321–347).

$$
\tilde\nu_L = \frac{10^7}{\lambda_L},\qquad
\Delta\lambda = \frac{\Delta\tilde\nu}{\tilde\nu_L}\,\lambda_L = \frac{\Delta\tilde\nu\,\lambda_L^2}{10^7}
$$

`λ_L` = `_raman_measurement_device.excitation_laser_wavelength` (nm), `Δν̃` = `_raman_measurement_device.resolution` (cm⁻¹) (rod l. 322–327). Example: 532 nm, 2 cm⁻¹ → 0.0566 nm. The comment (rod l. 330) states the assumption that the resolution refers to the laser wavelength. Written to `…/INSTRUMENT[instrument]/wavelength_resolution/resolution` with `@units = "nm"` and `physical_quantity = "wavelength"` (rod l. 337–345).

### Parser: grating period

**Location:** rod l. 349–356. `period = 1 / float(diffraction_grating)` written to `…/MONOCHROMATOR[monochromator]/GRATING[grating]/period`. The unit of the input is not checked or written here.

### Parser: crystallographic uncertainty removal

**Location:** rod l. 263–288. Regex `\(\d+\)` is removed from each of `_cell_length_a/b/c` and `_cell_angle_alpha/beta/gamma`, then `float()`:

```text
"9.40(3)" -> 9.40       "90" -> 90.0       "5.4321(12)" -> 5.4321
```

Result: `rod_unit_cell_length_abc = [a, b, c]` (rod l. 268–272) and `rod_unit_cell_angles_alphabetagamma = [α, β, γ]` (rod l. 281–285). The six source keys are deleted from `unused_attrs` (rod l. 273–275, 286–288).

### Parser: date to ISO 8601

**Location:** rod l. 296–309. `datetime.strptime(value, "%Y-%m-%d")`, `tzinfo` forced to UTC (comment: "assume UTC … not specified"), `isoformat()`:

```text
"2019-03-14" -> "2019-03-14T00:00:00+00:00"
```

### Parser: CIF value extraction

**Location:** `get_cif_value_from_key()` (rod l. 159–207).

| Case | Handling | Lines |
|---|---|---|
| single value, multi-line (`;` text field) | strip `;\n` and `\n;`, replace remaining `\n` by space, `lstrip()` | 185–190 |
| single value starting with `'` | **all** `'` removed | 192–193 |
| other single value | returned as the string gemmi gives | 194 |
| loop column | list of strings; if every item converts, list of `float` | 195–206 |

### Parser: citation fields

**Location:** `build_citation_fields()` (rod l. 372–424). Produces four synthetic keys, referenced from the JSON config as `@attrs:<key>`:

| Key | Content | Lines |
|---|---|---|
| `rod_citation_publication_author` | authors joined with `"; "`, quotes stripped | 387, 396–397 |
| `rod_citation_publication_description` | `"<title>. <journal>, <volume>, <p1>-<p2> (<year>)."` | 399–412 |
| `rod_citation_rod_url` | `https://solsa.crystallography.net/rod/<code>.html` | 414–417 |
| `rod_citation_rod_description` | ROD entry text + CC0 licence + ROD paper citation | 418–422 |

## Standard behaviour

1. **Detection.** First 50 lines, any line starting with `data_`; `OSError` returns `False` (rod l. 72–79).
2. **CIF load.** `gemmi.cif.read_file(...)`, `doc.sole_block()` (raises if the file has more than one block), and the raw lines are re-read as UTF-8 (rod l. 90–95).
3. **Key discovery by text scan.**
   - `loop_` positions: lines containing `"loop_\n"` (rod l. 210, 109–111).
   - candidate keys: lines whose first character is `_` (rod l. 211, 101–104).
   - loop keys: consecutive key lines directly after a `loop_` line; hard stop after 100 (rod l. 145–157).
4. **Key → "is loop" map.** Loop keys keep the whole line (minus `\n`) as the dict key; non-loop keys are cut at the first space (rod l. 114–143).
5. **Value lookup.** For every key `get_cif_value_from_key()` (see table above), result dict `key → value` (rod l. 217–225).
6. **Split.** Keys in `ROD_SPECTRUM_DATA_KEYS` are popped into `self.data`; the rest becomes `self.attrs` (rod l. 232–237).
7. **Key sanitising.** `_[local]_` → `_local_` so square brackets do not clash with NXclass assignment syntax (rod l. 239–243).
8. **Unused-keys bookkeeping.** `self.unused_attrs` is a deep copy of the attrs (rod l. 245); keys consumed later are removed from it (rod l. 248–257, 261, 273–275, 286–288, 347).
9. **Citation.** `self.attrs.update(build_citation_fields(self.attrs))` (rod l. 247).
10. **Normalisation.** COD service name (rod l. 259–261), cell parameters (263–288), environment lower-cased (290–294), date to ISO (296–309), optics type lower-cased and mapped to the NXDL enum `objective | lens | glass fiber | none | other` (311–319).
11. **post_process.** Resolution and grating period (rod l. 321–356); results are written into `self.attrs` under full template paths.

## Special behaviour

1. **Two readers of one file.** Keys come from a text scan, values from gemmi (rod l. 209–225). A key present in the text but unknown to gemmi would fail at `find_value`.
2. **Spectrum arrays are not attributes.** `_raman_spectrum.intensity` and `.raman_shift` are the only two keys routed to `self.data` (rod l. 48, 232–236).
3. **Template-path keys inside `attrs`.** `post_process` writes keys such as `/ENTRY[entry]/INSTRUMENT[instrument]/wavelength_resolution/resolution` directly into `self.attrs` (rod l. 337–345, 354–356), unlike the CIF keys.
4. **ROD provenance is embedded.** The licence (CC0) and the ROD paper citation are written into the NeXus file (rod l. 33–43, 418–422).
5. **COD link.** If `_cod_database_code` exists, `COD_service_name = "Crystallography Open Database"` is set (rod l. 259–261).
6. **Optics enum fallback.** Any optics type not in the four allowed values becomes `"other"` (rod l. 317–319).
7. **`__all__`** exports `build_citation_fields` (rod l. 31), so it can be reused or tested on its own.

## Behaviour to investigate

1. **`post_process` crashes before its own guard.** `float(self.attrs.get(...))` (rod l. 322–327) raises `TypeError` for a missing key, so the `is not None` check at rod l. 329 is dead. Records without laser wavelength or resolution fail the whole conversion.
2. **Always-true guards.** `x is not None or ""` (rod l. 259, 263, 276) is `(x is not None) or ""`; the `or ""` has no effect, and an empty string passes.
3. **Only `a` and `alpha` are checked.** rod l. 263 and 276 test one key, then read `b`, `c`, `beta`, `gamma` (rod l. 266–267, 279–280). A record with `_cell_length_a` but no `_cell_length_b` raises `TypeError` in `re.sub`.
4. **CIF null values.** `?` and `.` are never treated as missing; `float("?")` raises `ValueError` (rod l. 268–272, 281–285, 322–327, 356).
5. **Trailing-space key lines.** A key line like `"_key \n"` contains a space, so `split(maxsplit=1)` returns one element and the two-name unpacking at rod l. 130 raises `ValueError` (checked: `"_key \n".split(maxsplit=1)` returns `['_key']`).
6. **Text scan is not CIF-aware.** A line starting with `_` inside a `;` text field, or a `loop_` with trailing blanks or CRLF endings, is misclassified (rod l. 101–104, 109–111, 210).
7. **Duplicate keys** collapse in the dict; a length mismatch is only an `info` log (rod l. 139–143).
8. **Quote stripping is blunt.** `value.replace("'", "")` removes apostrophes inside the value as well (rod l. 192–193).
9. **Date format.** Only `%Y-%m-%d` is accepted (rod l. 300); a value with a time raises `ValueError`. The `isinstance`/`tzinfo` checks at rod l. 303–304 are always true.
10. **Grating unit.** `1 / float(diffraction_grating)` (rod l. 356) writes no unit, and divides by zero for `0`. Confirm what ROD stores (lines per mm?) and what the NXDL expects.
11. **Wrong docstring.** `get_cif_value_from_key` is documented as "Parse the top-level Prodigy export settings into a dict" (rod l. 163), a leftover from another plugin.
12. **Dead code.** `rod_lines is None` can never be true (rod l. 106); the f-string at rod l. 107 has no placeholder; the loop-bool conversion comment block (rod l. 199–201) is commented-out code.
13. **Citation edge cases.** `_journal_paper_doi` is read but never emitted, only used to trigger the block (rod l. 394, 399). A trailing `.` is always appended (rod l. 412), producing `..` if the title already ends with one. `_journal_paper_doi` and `_rod_database.code` are not removed from `unused_attrs`.
14. **`__init__` signature.** `*args, **kwargs` are accepted but `super().__init__()` is called without them (rod l. 63–64).
15. **Encoding.** UTF-8 is assumed (rod l. 73, 85); gemmi reads the file independently.

## Scanner findings

No scanner run was performed for `pynxtools-raman`.
