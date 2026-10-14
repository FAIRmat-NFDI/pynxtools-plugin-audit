# Bruker NanoScope `.spm` parser and formatter (`pynxtools-spm`)

## Source files reviewed

- `pynxtools_spm/parsers/bruker_spm.py` — `SpmBruker` parser (282 lines).
- `pynxtools_spm/nxformatters/bruker/bruker_spm_afm.py` — `BrukerSpmAFM` formatter (343 lines).
- Inherited: `BrukerBase` (`nxformatters/bruker/bruker_base.py`, incl. `rearrange_data_according_to_axes`), `derive_scan_2d_start_end()`, `_pixel_centres()`, `put_scan_2d_region_field_in_template()` (base formatter), `_get_data_unit_and_others()`, `to_intended_t()`, `unit_short()` (`nxformatters/helpers.py`).
- Project docs: `reference/bruker.html`, `explanation/scan-region/bruker-spm.html`.

**Line-number note:** References below refer to the main branch on 13th October 2026. `parser l.` = `bruker_spm.py`, `formatter l.` = `bruker_spm_afm.py`.

## At a glance

| | |
|---|---|
| **Input format** | Bruker NanoScope `.spm` (ASCII header up to `\*File list end`, then binary image blocks); AFM |
| **Parser class** | `SpmBruker(SPMBase)` (parser l. 74–282) |
| **Image reader** | `gwyddionpy.load()` (Gwyddion `nanoscope` importer) (parser l. 100); rows left in gwyddionpy order (parser l. 136–139) |
| **Header reader** | Own parser `_read_header_sections()` → list of `(section, {key: value})` (parser l. 157–186) |
| **Raw-data storage** | `spm_dict` (flat), `channel_data[channel][direction]` arrays (parser l. 102–104) |
| **Output from parser** | Flat dict: `/<Channel>/forward\|backward`, `/Scan_list`, `/File/…`, `/Equipment_list/<i>/…`, `/Scanner_list/<i>/…`, `/Scan/<Channel>/<direction>/…` (parser l. 84–96, 117–154) |
| **Formatter class** | `BrukerSpmAFM(BrukerBase)` (formatter l. 33–343); default config `bruker_spm_afm` (formatter l. 62–66) |
| **Target definition** | `NXafm` (docs) |
| **Tested versions** | NanoScope 9.x (Dimension Icon, `\Version: 0x09400105`); ELN model `9.64` (docs) |
| **Project context** | See the [project repository](https://github.com/FAIRmat-NFDI/pynxtools-spm/). One `.spm` gives one NeXus file with several `NXdata` groups (docs). |

**Standard behaviour.** The parser reads the ASCII header into sections, loads the image layers with gwyddionpy, pairs the *k*-th `Ciao image list` section with the *k*-th channel, multiplies each image by a unit factor from the header and exposes every channel as `forward` and `backward` (parser l. 99–155). The formatter builds `scan_region`, `meshSCAN[mesh_scan]` and the `NXdata` axes (formatter l. 68–86, 131–266, 268–343).

**Comparison with other `pynxtools-spm` parsers.** One file carries many channels and both scan directions, unlike `.flt`. The header is parsed by the parser itself because gwyddionpy merges all sections into one flat dict (parser l. 74–82).

## Formula / transformation

### Parser: Z scale factor (SI → channel unit)

**Location:** `_scale_factor()` (parser l. 215–252), applied at l. 140–142.

```python
factor = 1.0 / ureg.Quantity(1.0, sens_unit).to_base_units().magnitude      # l. 243–246
if z_scale_unit == "mV": factor *= MILLI_VOLT_FACTOR                        # l. 250–251
data = channel.data * factor                                                 # l. 140–142
```

$$
z_{\text{out}} = z_{\text{SI}}\cdot\frac{1}{m(u_{\text{sens}})}\cdot\begin{cases}1000 & \text{Z-scale unit} = \text{mV}\\ 1 & \text{otherwise}\end{cases}
$$

`m(u)` is the base-unit magnitude of the sensitivity unit (nm → 1e-9, factor 1e9). `u_sens` comes from the line named by `@2:Z scale` (regexes l. 53–57), e.g. `\@Sens. ZsensSens: V 485.6748 nm/V` → `nm`. The factor is `1.0` if Z scale, sensitivity or its unit cannot be matched (l. 228–229, 236–237, 240–241) or if pint raises (l. 247–248).

### Parser: header value and unit

**Location:** `extract_data_unit()` (parser l. 254–282); regexes l. 46, 48.

| Shape        | Example                                  | Output                                   | Lines   |
| ------------ | ---------------------------------------- | ---------------------------------------- | ------- |
| scaled       | `V (0.00001164153 kHz/LSB) 172.0493 kHz` | `key = '172.0493'`, `key/@units = 'kHz'` | 267–272 |
| value + unit | `20000 nm`                               | `key = '20000'`, `key/@unit = 'nm'`      | 274–279 |
| other        | anything else                            | `key = val`                              | 281     |

### Formatter: scan range and aspect ratio

**Location:** `construct_scan_region_grp()` (formatter l. 131–197).

$$
R_x = \text{ScanSize},\qquad R_y = \frac{R_x}{\text{AspectRatio}},\qquad \text{AspectRatio}=\frac{a}{b}\ \text{from "a:b"}
$$

`range_val = ureg.Quantity(data, unit).to(x_offset_unit)` (l. 188); `y_range = x_range / aspect_ratio_val` (l. 190). Aspect ratio from `/Scanner_list/0/Aspect_Ratio` (l. 173–187); default `1.0`.

Offsets are the frame **centre**: start/end = offset ∓ range/2 (docstring l. 142–146; arithmetic in `derive_scan_2d_start_end()`, base class, l. 194).

### Formatter: step size

**Location:** `construct_scan_pattern_grp()` l. 250–262.

$$
\Delta_x = \frac{R_x}{N_x},\qquad \Delta_y = \frac{R_y}{N_y}
$$

Comment l. 250: "The step is the pixel pitch, so the axis values are pixel centres." No `N < 2` or zero check.

### Formatter: geometry value with embedded unit

**Location:** `_scalar_with_unit()` (formatter l. 88–129). A string such as `"-3750 nm"` is parsed with pint (`ureg.Quantity(value)`, l. 108) and converted to the config unit (l. 123–126). Unparsable strings give `None` (l. 115–120).

### Formatter: slow-axis sign

**Location:** l. 225–248. `\Frame direction` over all image layers: `{up}` → `+y`, `{down}` → `-y`, mixed → `y` with warning (l. 238–243), none → `y` silently. Fast axis is always `x` (l. 244).

## Standard behaviour

1. **Header.** `_read_header_sections()`: reads the whole file (l. 163–164), cuts at `HEADER_END` (l. 165), warns and returns `[]` if absent (l. 166–168), decodes `latin-1` (l. 176) and builds sections with `SECTION` / `KEY_VALUE` (l. 39, 43).
2. **Section routing** (`parse()`, l. 111–142): `File list` → `/File`, `Equipment list` → `/Equipment_list/<i>` (l. 112–117); `Ciao scan list` → `/Scanner_list/<i>` (l. 118–120); `Ciao image list` → channel/direction (l. 121–142). All other sections are dropped.
3. **Channel and direction.** `_channel_and_direction()` (l. 197–213): quoted title of `@2:Image Data` (`IMAGE_DATA`, l. 50) with spaces → `_` (l. 210); `Trace` → `forward`, `Retrace` → `backward`, missing → `forward` (l. 212). Unannotated layer → warning, layer skipped (l. 205–209).
4. **Pairing.** `channels[image_index - 1]` (l. 140–142); extra layers beyond `len(channels)` → warning and `continue` (l. 122–127).
5. **Fill-in.** Each channel is exposed under both directions; a missing direction takes the stored one (l. 144–152).
6. **Scan list.** `/Scan_list` = `"<Channel>/<direction>"` strings (l. 135, 154).
7. **Formatter.** `get_nxformatted_template()` (l. 56–60); `_construct_nxscan_controllers()` builds `scan_region` and `meshSCAN[mesh_scan]` (l. 68–86). `NXdata` axes `X`, `Y` are pixel centres via `_pixel_centres()` (l. 328–336); `@axes = [Y, X]` if empty (l. 338–342).

## Special behaviour

1. **Single-direction channel appears twice**, as both `forward` and `backward` (parser l. 146–152).
2. **Row orientation untouched in the parser** (l. 136–139); flip is in `BrukerBase.rearrange_data_according_to_axes` (not read).
3. **Key normalisation.** Whitespace → `_` (l. 264); a `/` inside a key (`Samps/line`) adds a path level.
4. **Unit parsing in the formatter.** Geometry values such as `"-3750 nm"` that the parser leaves as strings are resolved with pint (formatter l. 88–129).
5. **Axes rebuilt from the image.** If header counts differ from the signal shape, a warning is logged and `x_points`/`y_points` are replaced by the shape (formatter l. 311–326).
6. **Both axes ascend.** Row 0 / column 0 is the bottom-left corner (formatter l. 328–330).
7. **Config values are consumed.** `popitem()` on the offset and points entries (formatter l. 154, 212) mutates the config dict; the FLT formatter explicitly avoids this.
8. **Title.** Written from the config `title` entry if present (formatter l. 290–294).
9. **Parser selection** uses extension plus ELN vendor/model (docs).

## Behaviour to investigate

1. **`@units` vs `@unit`.** The scaled-value branch writes `key/@units` (parser l. 271), all others `key/@unit` (l. 278). A config looking for `/@unit` misses scaled values. The FLT parser writes `/@unit`, the TXT parser `/unit`.
2. **Negative or exponent values stay strings in the parser.** `VALUE_WITH_UNIT` `[\d]+[.]?[\d]*` (l. 48) and `SCALED_VALUE` `[\d.]+` (l. 46) reject `-` and `e-05`; `\X Offset: -3750 nm` remains one string. The formatter recovers geometry values with pint (`_scalar_with_unit`, formatter l. 88–129), but any other negative header value is not split.
3. **Units with `/`.** `(\w+)` does not match `nm/V` (l. 48), so such values are not split.
4. **Positional image ↔ channel pairing** (l. 140–142, comment l. 108). If gwyddionpy skips or reorders a layer, data and metadata shift with no check.
5. **Duplicate channel + direction** overwrite in `channel_data` (l. 140) while `/Scan_list` gets both entries (l. 135).
6. **Duplicated direction** for one-direction channels (l. 146–152): the `backward` entry is a copy of `forward`.
7. **Channel title regex** `[\w\s]+` (l. 50) fails for titles with `-` or `.`; the layer is dropped with a warning, but `image_index` was already incremented (l. 129–131).
8. **Z factor.** Only an exact `"mV"` Z-scale unit is corrected (l. 250); `µV`, `kV` etc. are not. pint failure returns `1.0` silently (l. 247–248). The signal unit is not exported.
9. **Sensitivity lookup** takes the first section that has `@<name>` (l. 232–235).
10. **Aspect ratio fallback is partly silent.** A warning appears only if the string contains `:` but the parts are not digits (formatter l. 175–187); a value without `:` falls back to 1:1 without a message (l. 174–175). Parts with a minus sign fail `isdigit` (l. 178).
11. **Range unit depends on offsets.** `.to(self.scan_control.x_offset_unit)` (formatter l. 188) fails if the offset field is missing or has no unit.
12. **Empty variadic list.** `offset_fld_list[0]` / `scan_points_fld_list[0]` (formatter l. 152, 209) raise `IndexError` for an empty list.
13. **Step size** uses header `N` (formatter l. 251–262) before the axes are rebuilt from the signal shape (l. 311–326); no zero or `N < 2` guard.
14. **Dropped sections.** Anything other than `File list`, `Equipment list`, `Ciao scan list`, `Ciao image list` is discarded (parser l. 112–142).
15. **Frame direction** missing in all layers gives an unsigned `y` silently (formatter l. 228–237).
16. **Stale docstring.** `_nxdata_grp_from_conf_description()` docstring (formatter l. 277) describes forward/backward and line scans, not what the method does.
17. **Memory.** The whole file is read for the header (l. 163–164) and again by gwyddionpy.

## Scanner findings

No scanner run was performed for `pynxtools-spm`.
