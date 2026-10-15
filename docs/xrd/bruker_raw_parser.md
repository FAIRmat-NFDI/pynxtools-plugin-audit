# Siemens/Bruker RAW v4 binary XRD parser (`pynxtools-xrd` / `readers-xrd`)

## Source files reviewed

- `bruker_raw_parser.py` — `BrukerRAW4Parser`, `read_bruker_raw4()`, `convert_raw_to_xy()` and the `XRAY_WAVELENGTHS` table (420 lines). The file is standalone: it has no pynxtools imports and no `READER`/entry-point.
- Project: [pynxtools-xrd](https://github.com/FAIRmat-NFDI/pynxtools-xrd) and [readers-xrd](https://github.com/FAIRmat-NFDI/readers-xrd/tree/main).

**Line-number note:** References below refer to the file in the development branch on 15th October 2026. `raw l.` = `bruker_raw_parser.py`.

## At a glance

| | |
|---|---|
| **Input format** | Siemens/Bruker RAW v4 binary (`.raw`, magic `RAW4.00\0`), single-axis θ–2θ powder scans written by DIFFRAC.EVA |
| **Parser class** | `BrukerRAW4Parser` (raw l. 69–375) |
| **Reader** | `open(..., "rb").read()`, `struct.unpack` at **fixed byte offsets**, no external library (raw l. 141–143) |
| **Raw-data storage** | `self.metadata`, `self.scan_params`, `self.intensities`, `self.angles` (raw l. 114–117) |
| **Output from parser** | `{"metadata", "scan_params", "intensities", "angles"}` (raw l. 183–188) |
| **Helpers** | `read_bruker_raw4(path)` (raw l. 378–394), `convert_raw_to_xy(raw, xy=None)` (raw l. 397–419) |
| **Target definition** | none in this file; plugin side not supplied |
| **Provenance** | Header says "Generated for NOMAD", licence MIT (raw l. 11–12); other files in the audit use Apache-2.0 headers |
| **Project context** | Only binary XRD parser in the audit; based on reverse engineering, validated on a small set of files (raw l. 8–9, 89–91) |

**Standard behaviour.** `parse()` logs a scope warning, reads the whole file, checks the 8-byte magic, reads date and time, searches the rest of the file for five text tags (USER, SITE, SAMPLEID, COMMENT, CREATOR), then reads number of points, step, start angle, axis name, anode and the intensity block from fixed offsets (raw l. 120–188, 217–349). Angles are computed, not read.

**Comparison with `ikz.py`.** `ikz.py` unpacks ZIP archives of XML/ASCII (RASX, BRML) and gets named fields. This parser reads an undocumented binary layout by position, so every number depends on the file being a "standard" RAW v4.

## Formula / transformation

### Parser: byte-offset map

| Quantity | Offset | Format | Lines |
|---|---|---|---|
| magic | 0x00–0x07 | `RAW4.00\0` | 94, 146–151 |
| unknown flag | 0x08 | `<I` (ignored) | 155–159 |
| date | 0x0C, 8 bytes | ASCII | 161–166 |
| time | 0x14, 8 bytes | ASCII | 168–173 |
| anode material | 0x01A8–0x01AF | ASCII, nul-split | 278–288 |
| number of points | 0x01C3 | `<H` (uint16) | 235–237 |
| step size | 0x020F | `<d` | 244–246 |
| scan axis name | 0x04D0–0x04DF | ASCII, nul-terminated | 262–268 |
| start angle | 0x04FB | `<d` | 253–255 |
| data section | 0x051F | `<f` pairs to end of file | 320–337 |

### Parser: angle axis

**Location:** raw l. 311–317.

$$
\theta_i = \theta_0 + i\,\Delta,\qquad i = 0,\dots,N-1,\qquad
\theta_{\text{end}} = \theta_0 + (N-1)\,\Delta
$$

Example: `θ0 = 10`, `Δ = 0.02`, `N = 5` → `[10, 10.02, 10.04, 10.06, 10.08]`, end angle `10.08`. The unit (degrees) is assumed in log messages (raw l. 246, 255, 314), never read from the file.

### Parser: intensity extraction

**Location:** raw l. 319–345. All bytes from 0x051F to end of file are interpreted as little-endian float32; every second value is taken as intensity:

```python
all_floats = struct.unpack(f"<{num_floats}f", data_section[:num_floats*4])
self.intensities = [all_floats[i] for i in range(0, len(all_floats), 2)]
```

The odd-indexed values ("unknown") are discarded (raw l. 335–336).

### Parser: wavelength lookup

**Location:** raw l. 286–300 and `XRAY_WAVELENGTHS` (raw l. 23–66). For anodes `Cu, Mo, Co, Fe, Cr, Ag` the metadata gets `wavelength_kalpha1`, `…_kalpha2`, `…_kbeta`, `…_kalpha_avg`, `kalpha2_kalpha1_ratio` (Å). Example Cu: 1.540598 / 1.544426 / 1.392250 / 1.541874 / 0.5. The table cites International Tables, Vol. C (raw l. 21–22).

### Converter: XY text

**Location:** `to_xy_format()` (raw l. 351–375): `#` comment header (sample, date/time, start, step, points), then `"{angle:.4f}  {intensity:.2f}"` per line.

## Standard behaviour

1. **Scope warning** is emitted on every `parse()` call (raw l. 135–139).
2. **Read.** Entire file into memory (raw l. 141–143).
3. **Magic.** Mismatch raises `ValueError` (raw l. 146–151).
4. **Date/time.** 8 bytes each, right-stripped of nul, ASCII with `errors="ignore"` (raw l. 161–173).
5. **Tags.** For each entry in `METADATA_TAGS` (raw l. 98–104) find the first occurrence in the data after byte 20 (raw l. 176, 199); the value runs to the next `\n` within 200 bytes, else to `\0\0` (raw l. 203–206); stripped of `\0`, `\n`, space (raw l. 211); stored under `user`, `site`, `sample_id`, `comment`, `creator` if non-empty (raw l. 214–215).
6. **Scan parameters.** Number of points, step, start, axis name, anode (raw l. 233–308), each in its own `try/except` that logs and continues.
7. **End angle and angles** only if start, step and count are all available (raw l. 311–317).
8. **Intensities** from the data section (raw l. 323–349); on any exception `intensities = []` (raw l. 347–349).
9. **Return** a dict of the four stores (raw l. 183–188).

## Special behaviour

1. **Single-axis only.** The docstring and the warning state that multi-axis scans (texture, pole figures, RSM) are not supported and that omega, chi, phi are not read (raw l. 73–81, 135–139).
2. **Offsets are hard-coded** and "may not generalize to all RAW v4 variants" (raw l. 89–91).
3. **Unknown anode** is stored without wavelengths and logs a warning (raw l. 301–306).
4. **Failures are soft.** Each field failure is logged and parsing continues (raw l. 238–240, 247–249, 256–258, 269–271, 307–308).
5. **The "unknown" float** that alternates with the intensities is discarded (raw l. 335–336).

## Behaviour to investigate

1. **Intensity count is not tied to `num_points`.** Everything up to end of file is unpacked (raw l. 324–337). Trailing blocks produce extra values; an odd float count adds one more (`range(0, len, 2)`). `read_bruker_raw4` can therefore return `len(intensities) != len(angles)`; `to_xy_format` hides it through `zip` (raw l. 372).
2. **`UnboundLocalError` on a bad start angle.** If reading the start angle fails (raw l. 256–257), `start_angle` is never assigned, and `start_angle is not None` at raw l. 311 raises.
3. **Copy-paste reset.** The `except` for the axis name sets `start_angle = None` (raw l. 271), which silently disables the angle array if the axis name cannot be read.
4. **uint16 point count.** `<H` at 0x01C3 limits scans to 65 535 points (raw l. 235); verify against real long scans.
5. **θ vs 2θ.** The axis name is stored (e.g. `Theta`, raw l. 266–267) but never mapped; the XY header and column are labelled `2Theta` (raw l. 370). Confirm what the start angle and step represent in coupled scans.
6. **Units** are assumed degrees and counts; nothing is read from the file (raw l. 246, 255, 314, 370).
7. **Tag search is global.** `data.find(tag)` scans the whole remaining file, including the float block (raw l. 176, 199); random byte sequences could match, and only the first hit is used. Embedded nul bytes inside a value survive stripping.
8. **Fixed 200-byte window** for values (raw l. 204–206) truncates long comments.
9. **Performance.** `struct.unpack` of the full tail and Python lists (raw l. 330–337); `numpy.frombuffer` would be faster and cheaper in memory for large scans.
10. **Licence and provenance.** MIT header and "Generated for NOMAD" (raw l. 11–12) differ from the Apache-2.0 headers elsewhere; there is no copyright line. Decide before publishing.
11. **Encoding.** `convert_raw_to_xy` writes `°` with the platform default encoding (raw l. 366–367, 370, 416).
12. **Scope warning noise.** Logged at `warning` level for every valid file (raw l. 135–139).
13. **Typing style.** `Dict`, `Optional` (raw l. 18) while sibling modules use built-in generics.
14. **Dead variable.** The flag read at raw l. 156–158 is unused by design.

## Scanner findings

No scanner run was performed for `pynxtools-xrd` / `readers-xrd`.
