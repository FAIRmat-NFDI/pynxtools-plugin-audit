# Omicron / RHK SM4 parser and formatter (`pynxtools-spm`)

## Source files reviewed and scope

This review is based on these two Python scripts:

- `omicron_sm4.py`: `Sm4Omicron(SPMBase)` parser, corresponding to the imported parser module `pynxtools_spm.parsers.omicron_sm4`.
- `omicron_sm4_stm.py`: `OmicronSM4STM(OmicronBase)` formatter.

**Line-number note:** References below use the line numbers of the scripts in the main branch on 13th October. `omicron_sm4.py` has 139 lines; `omicron_sm4_stm.py` has 560 lines. References are written as `omicron_sm4.py:29` and `omicron_sm4_stm.py:358`.

## At a glance

| Item                           | Behavior supported by the supplied scripts                                                                                                                                                      |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input                          | Omicron SM4 STM files; metadata-reader pages may include non-image pages.                                                                                                                       |
| Parser                         | `Sm4Omicron(SPMBase)` (`omicron_sm4.py:17`).                                                                                                                                                  |
| Image loading                  | `gwyddionpy.load(str(self.file_path))` (`omicron_sm4.py:34`).                                                                                                                                 |
| Metadata loading               | `read_sm4_pages(self.file_path)` imported from `rhk_sm4_metadata` (`omicron_sm4.py:33`). Binary decoding is delegated to that module.                                                         |
| Page/channel matching          | Gwyddion channels indexed by lower-cased `channel.meta.get("Page ID", "")` (`omicron_sm4.py:46-49`); lookup uses `page.page_id` (`omicron_sm4.py:69`).                                      |
| Parser output                  | One flattened dictionary containing metadata, image coordinates and available image arrays under page-label prefixes (`omicron_sm4.py:29-80`).                                                |
| Formatter                      | `OmicronSM4STM(OmicronBase)` (`omicron_sm4_stm.py:48`). Its module docstring identifies `NXstm` as the target application definition (`omicron_sm4_stm.py:1-4`).                                |
| Configuration                  | Reads a supplied config via `fhs.read_config_file()` or calls `load_default_config("omicron_sm4_stm")` (`omicron_sm4_stm.py:83-88`).                                                            |
| Coordinates                    | Ascending pixel-centre coordinates, computed independently for X and Y (`omicron_sm4.py:113-137`).                                                                                            |
| Scan region                    | Per-axis offset and range, with range `abs(scale) * points` (`omicron_sm4_stm.py:272-292`); endpoint derivation delegated to `derive_scan_2d_start_end()` (`omicron_sm4_stm.py:294`).           |
| Direction metadata             | Fast axis `x`; slow axis `+y` for positive Y scale, `-y` for non-positive Y scale, and `y` when Y scale is missing (`omicron_sm4_stm.py:418-423`).                                              |
| NXdata and array rearrangement | Delegated to the base formatter; the override passes `rearrange_2d_data=True` by default (`omicron_sm4_stm.py:524-531`) and records scan-to-data-group mappings (`omicron_sm4_stm.py:552-559`). |

## Parser standard behavior

### Page loading and flattened output

`Sm4Omicron.parse()` first calls `read_sm4_pages()` (`omicron_sm4.py:33`), then loads the file through Gwyddion (`omicron_sm4.py:34`). It builds a channel lookup dictionary (`omicron_sm4.py:46-49`) and iterates over the metadata-reader pages (`omicron_sm4.py:53`).

For each page it:

1. Chooses a unique label using `_unique_label()` (`omicron_sm4.py:54`).
2. Exports every `page.attrs` entry under `/<label>/`, rewriting unit-key suffixes (`omicron_sm4.py:55-56`).
3. If `page.is_image` is false, logs a warning and continues without generating coordinates or image data (`omicron_sm4.py:58-64`).
4. For an image page, generates X and Y coordinates before attempting channel lookup (`omicron_sm4.py:66-67`).
5. Looks up the image channel using `page.page_id` (`omicron_sm4.py:69`).
6. If a channel exists, exports `np.asarray(channel.data)` as `/<label>/data` (`omicron_sm4.py:78`).

Typical output paths are:

```text
/Topography_Forward/RHK_Xscale
/Topography_Forward/RHK_X/@unit
/Topography_Forward/coords/Topography_Forward_x
/Topography_Forward/coords/Topography_Forward_y
/Topography_Forward/data
```

There is one returned dictionary for the entire file, not one returned dictionary per page (`omicron_sm4.py:29-80`). The shape of each image array is whatever `channel.data` supplies; the parser does not explicitly reshape or validate it (`omicron_sm4.py:78`).

### Non-image pages and unmatched images

Non-image pages contribute metadata only (`omicron_sm4.py:58-64`). Their numeric spectra or other non-image payloads are not exported by this parser.

An image page with no matching Gwyddion channel contributes metadata and coordinates, but no image data (`omicron_sm4.py:66-76`). The warning says “only its metadata is read” (`omicron_sm4.py:71-75`), but the coordinates have already been written at that point. This corrects the original document's metadata-only description of unmatched images.

Whether metadata-only pages are represented in a final NeXus file depends on the configuration and base formatter; it cannot be inferred solely from the presence of parser keys.

### Unique page labels

The parser starts with `page.label` (`omicron_sm4.py:90`); label construction inside the metadata reader was not reviewed.

If the label is already taken, `_unique_label()` derives a source suffix from the last underscore-separated component of `RHK_PageSourceTypeName` (`omicron_sm4.py:96`):

```python
source = str(page.attrs.get("RHK_PageSourceTypeName", "")).rsplit("_", 1)[-1]
candidate = f"{label}_{source.capitalize()}" if source else label
```

(`omicron_sm4.py:96-97`)

For example, `RHK_SOURCE_PROCESSED` yields an initial duplicate label such as `Topography_Forward_Processed` (`omicron_sm4.py:95-97`). Further collisions use `f"{label}_{source}{index}"`, preserving the original source token's case, or `f"{label}_{index}"` if there is no source suffix (`omicron_sm4.py:98-101`). The counter starts at 2 (`omicron_sm4.py:98`). Every renamed page produces a warning (`omicron_sm4.py:102-108`).

### Unit-key rewriting

`UNIT_SUFFIX` is:

```python
re.compile(r"(units|unit)$", flags=re.I)
```

(`omicron_sm4.py:12`)

Every metadata key is transformed with `UNIT_SUFFIX.sub('/@unit', key)` (`omicron_sm4.py:56`); the value is unchanged.

Examples:

- `RHK_Xunits` → `RHK_X/@unit`
- `RHK_PiezoSensitivity_TubeXUnit` → `RHK_PiezoSensitivity_TubeX/@unit`
- If present, `RHK_API_Units` → `RHK_API_/@unit`

This is a key/path rewrite, not a unit conversion. It also applies to any other key ending in `unit` or `units`, regardless of that key's meaning (`omicron_sm4.py:12,56`).

## Formulas and transformations

### Pixel-centre coordinates

Location: `Sm4Omicron._image_coords()` (`omicron_sm4.py:113-137`).

For each axis independently (`omicron_sm4.py:126`):

```python
offset = float(attrs[f"{key}offset"])
step = abs(float(attrs[f"{key}scale"]))
points = int(attrs[f"{key}size"])
scan_range = step * points
positions = (
    offset - scan_range / 2
    + (np.arange(points, dtype=np.float64) + 0.5) * step
)
```

(`omicron_sm4.py:128-135`)

Writing `o` for offset, `s` for scale and `N` for point count:

$$
r = N|s|, \qquad
 a_i = o - \frac{r}{2} + \left(i+\frac12\right)|s|,
 \quad i=0,\ldots,N-1.
\
$$

The implementation interprets offsets as scan-area centres and the absolute scales as pixel pitches (`omicron_sm4.py:115-121,128-135`). For positive pitch, coordinates strictly ascend regardless of the original scale sign; zero pitch produces constant coordinates. The full edge-to-edge range is `N * abs(scale)` (`omicron_sm4.py:131`), whereas the distance between the first and last pixel centres is `(N - 1) * abs(scale)`.

The parser docstring describes the image origin as bottom-left and points to `tests/README.md` for evidence supporting the centre interpretation (`omicron_sm4.py:115-121`).

Coordinates are calculated separately for X and Y (`omicron_sm4.py:126-137`). This method does not apply an angle-based rotation or convert coordinate values between physical units.

### Formatter scan region and step sizes

Location: `OmicronSM4STM._construct_scan_region_grp()` (`omicron_sm4_stm.py:253-345`).

For each axis, the formatter reads page-local offset, scale and point count (`omicron_sm4_stm.py:272-276`). If any of these is `None`, it skips updating that axis (`omicron_sm4_stm.py:277`). Otherwise it stores:

```python
axis_offset = float(offset)
axis_range = abs(float(scale)) * int(points)
```

(`omicron_sm4_stm.py:289-291`)

The unit comes from the matching `RHK_X/@unit` or `RHK_Y/@unit` (`omicron_sm4_stm.py:278-286`). Only a `None` unit triggers a warning and fallback to `"m"` (`omicron_sm4_stm.py:279-286`); an empty string does not trigger that fallback.

The method then calls `self.derive_scan_2d_start_end()` (`omicron_sm4_stm.py:294`) and writes configured scan ranges, starts and ends using the scan-control object's fields (`omicron_sm4_stm.py:297-337`). The inherited endpoint implementation was not supplied, so endpoint values and direction-dependent ordering must be verified there. The pixel-coordinate formula itself uses edges `offset ± range/2` (`omicron_sm4.py:128-135`).

Location: `_construct_scan_pattern_grp()` (`omicron_sm4_stm.py:146-251`).

For supported variadic step-size fields, a truthy configured raw value is written with its unit and attributes (`omicron_sm4_stm.py:205-227`). Otherwise, when the corresponding point count and range are truthy, the fallback is (`omicron_sm4_stm.py:228-249`):

$$
\Delta x = \frac{r_x}{N_x}, \qquad
\Delta y = \frac{r_y}{N_y}.
\
$$

For matching page metadata this equals the absolute pixel pitch. Fallback units are taken from `x_start_unit` or `y_start_unit` (`omicron_sm4_stm.py:237-249`), whose assignment depends on the inherited scan-control logic.

### Z calibration

The parser docstring states that Gwyddion applies `RHK_Zscale` and `RHK_Zoffset` to raw ADC counts and returns physical values in the Z units (`omicron_sm4.py:18-24`). The implementation exports `np.asarray(channel.data)` without explicitly applying those factors itself (`omicron_sm4.py:78`).

Thus calibration ownership is delegated to Gwyddion. The configuration and base formatter must also be checked before claiming that final NeXus output is free from double calibration.

### Scan directions and array orientation

Location: `_construct_nxscan_controllers()` (`omicron_sm4_stm.py:358-456`).

```python
y_scale = self._scan_tag_raw_data[scan_tag].get(f"/{scan_tag}/RHK_Yscale")
slow_axis = "y" if y_scale is None else ("+y" if y_scale > 0 else "-y")
self.scan_control.fast_axis = "x"
self.scan_control.slow_axis = slow_axis
self.put_independent_scan_axes_in_template(
    parent_path_mod, axes=("x", slow_axis)
)
```

(`omicron_sm4_stm.py:418-425`)

The fast-axis identifier is always unsigned `x` (`omicron_sm4_stm.py:420`). This method does not infer its sign from either `RHK_Xscale` or `RHK_ScanType`. The comment explains that Forward/Backward identifies the pass rather than establishing the physical fast-axis direction (`omicron_sm4_stm.py:411-417`).

The slow-axis identifier explicitly uses Y-scale sign (`omicron_sm4_stm.py:418-419`). Zero Y scale is assigned `-y` by the implementation, even though the comment discusses only positive and negative scales (`omicron_sm4_stm.py:411-419`).

Ascending parser coordinates and signed acquisition-direction metadata describe different aspects of a scan (`omicron_sm4.py:113-137`; `omicron_sm4_stm.py:418-425`). The formatter delegates NXdata construction to its base class with a default `rearrange_2d_data=True` (`omicron_sm4_stm.py:524-531`); the supplied override does not show which rows or columns are reversed. Any assertion that a specific row-orientation correction occurs requires reviewing `OmicronBase`.

## Formatter workflow

### Configuration and ELN processing

`get_nxformatted_template()` invokes, in order (`omicron_sm4_stm.py:78-82`):

1. `walk_though_config_nested_dict(self.config_dict, parent_path="")` (`omicron_sm4_stm.py:79`).
2. `_format_template_from_eln()` (`omicron_sm4_stm.py:80`).
3. `_handle_special_fields()` (`omicron_sm4_stm.py:81`).

It mutates the template and has no explicit return statement. The configuration walker and ELN mapping are inherited; their full behavior was not reviewed.

### Scan-controller discovery

`_construct_nxscan_controllers()` collects raw-data paths matching (`omicron_sm4_stm.py:379-382`):

```python
r"/(?=topography|current|backward|forward)([\w]+)/"
```

The match is case-insensitive (`omicron_sm4_stm.py:382`). A label must start with one of these prefixes and consist of word characters before the next slash. Arbitrary channel labels, labels with spaces, and other labels do not necessarily produce scan controllers.

For each collected scan tag, the configured `SPM_SCAN_CONTROL[...]` group name must contain a wildcard run matching the formatter's expected pattern (`omicron_sm4_stm.py:394-403`). Otherwise the method raises `ValueError` (`omicron_sm4_stm.py:404-406`). It substitutes the lower-cased scan tag for the wildcard (`omicron_sm4_stm.py:406-407`) and rewrites configured raw-path page prefixes to the current tag (`omicron_sm4_stm.py:373-381,408-410`).

The formatter constructs `scan_region` before `meshSCAN[mesh_scan]`, making ranges available for the step-size fallback (`omicron_sm4_stm.py:428-445`). It also handles direct raw-path fields, skipping those with a `#note` key in this branch (`omicron_sm4_stm.py:446-456`).

Controller discovery does not test for the presence of `/<tag>/data` (`omicron_sm4_stm.py:379-392`), so a recognized metadata-only page can enter this workflow.

### NXdata association and links

`_nxdata_grp_from_conf_description()` delegates actual group construction to the base formatter (`omicron_sm4_stm.py:524-541`). If the returned group name is truthy (`omicron_sm4_stm.py:542-543`), it checks the configured `data.raw_path` for a known scan-tag prefix (`omicron_sm4_stm.py:547-559`) and records the resulting group path (`omicron_sm4_stm.py:559`).

`_handle_special_fields()` later writes mesh-scan `DATA[scan_data]` links using `convert_data_dict_path_to_hdf5_path()` (`omicron_sm4_stm.py:519-522`). Tags with no recorded NXdata group are skipped (`omicron_sm4_stm.py:512-514`). Association uses a substring test between the lower-cased scan tag and the controller name (`omicron_sm4_stm.py:515`), not an exact tag-to-controller identity check.

The supplied code therefore supports conditional linking (`omicron_sm4_stm.py:508-522`), not a guarantee that every parsed page creates an NXdata group or receives a link.

### Lock-in channel selection

`find_active_channel()` searches for `RHK_CH(\d*)Drive_MasterOscillator` (`omicron_sm4_stm.py:97-99`). When inspecting a raw-data dictionary it returns the channel suffix of the first matching key whose value can be converted to an integer (`omicron_sm4_stm.py:104-115`).

It does not check whether that integer is nonzero or denotes an enabled channel; zero is accepted (`omicron_sm4_stm.py:110-114`). `_construct_lockin_amplifier_grp()` uses the result to replace `RHK_CH[0-9]*Drive` in configured raw keys (`omicron_sm4_stm.py:120-143`). Selection is made from the full raw dictionary (`omicron_sm4_stm.py:133`), rather than explicitly per scan page.

### Start and end times

`_handle_special_fields()` first delegates to its base implementation (`omicron_sm4_stm.py:459`). For a matching entry-level `start_time` (`omicron_sm4_stm.py:467-469`), it calls `fhs.add_local_timezone(val)` (`omicron_sm4_stm.py:470`). If the configured end-time field has a `raw_path` (`omicron_sm4_stm.py:473-484`), it obtains the duration-like raw value and calculates (`omicron_sm4_stm.py:488-490`):

```python
end_time = datetime.datetime.fromisoformat(start_time) + datetime.timedelta(float(data))
```

The positional argument to `datetime.timedelta` is days, not seconds (`omicron_sm4_stm.py:490`). This code therefore interprets `float(data)` as a day count.

The resulting end-time string is also passed to `add_local_timezone()` (`omicron_sm4_stm.py:491-492`). `ValueError` and `TypeError` inside the calculation are silently ignored (`omicron_sm4_stm.py:493-494`).

## Behavior to investigate

### Parser checks

1. Unit suffix rewriting can over-match unrelated key names and leave an underscore before `/@unit` (`omicron_sm4.py:12,56`).
2. Channel lookup overwrites earlier channels with identical normalized Page IDs, including repeated missing IDs stored as `""` (`omicron_sm4.py:46-49`). Normalization is applied to channel IDs, not explicitly to `page.page_id` in this script (`omicron_sm4.py:46-49,69`); verify the metadata reader's representation and byte order.
3. Unmatched image warnings omit the fact that coordinates have already been exported (`omicron_sm4.py:66-76`).
4. Non-image numeric payloads are not exported (`omicron_sm4.py:58-64`). Decide whether an additional spectroscopy path is needed.
5. `_image_coords()` directly indexes required attributes and does not validate positive dimensions, finite numbers or array shape (`omicron_sm4.py:124-137`). Missing or invalid values may raise exceptions; zero/negative pitches or counts need explicit expectations.
6. `parse()` does not wrap metadata loading or Gwyddion loading in exception handling (`omicron_sm4.py:29-80`). The actual exception types depend on those libraries.
7. Confirm calibration and units in Gwyddion and configuration (`omicron_sm4.py:18-24,78`). The metadata reader's storage dtypes and precision cannot be inferred from these scripts alone.

### Formatter checks

1. `_scan_list`, `_scan_tag_raw_data` and `_scan_tag_to_data_group` are mutable class attributes (`omicron_sm4_stm.py:57-60`). The supplied subclass does not initialize per-instance replacements. Check whether the base class resets them; otherwise state can leak between instances or repeated conversions.
2. Scan discovery is label-restricted rather than page-type based (`omicron_sm4_stm.py:379-392`). Test arbitrary channel names, spaces, processed duplicates and metadata-only pages.
3. If an axis lacks offset, scale or count, scan-region construction skips its update (`omicron_sm4_stm.py:272-292`) and still derives endpoints (`omicron_sm4_stm.py:294`). Check whether stale scan-control fields can be reused from another page.
4. X and Y region units are read independently (`omicron_sm4_stm.py:272-292`). However, emitted ranges, endpoints and fallback pitches use inherited start-unit fields (`omicron_sm4_stm.py:297-337,237-249`); verify their propagation and the separate NXdata coordinate-unit mapping.
5. The non-variadic `scan_points` branch reads from the original full raw dictionary and does not pass `func_on_raw_key`, unlike the variadic branch (`omicron_sm4_stm.py:159-194`). Verify that it selects the current scan rather than a configured fixed page.
6. Step-size recognition differs between the first and second loops: `step_size[\w]+\[` is deferred (`omicron_sm4_stm.py:196-201`), but only list-valued `step_size[A-Y]{1}\[` is processed later (`omicron_sm4_stm.py:205-249`). Check unsupported field-name forms and confirm how zero or negative configured values should behave.
7. Temporary replacement of `self.raw_data` is restored only at normal method exit, not in a `finally` block (`omicron_sm4_stm.py:149-151,251`; `omicron_sm4_stm.py:263-345`). Exceptions may leave the formatter bound to page-local data.
8. Confirm duration units for `datetime.timedelta(float(data))` (`omicron_sm4_stm.py:490`); if the source is seconds, this requires a code correction rather than a documentation reinterpretation.
9. End-time configuration traversal mutates the local `config_dict` variable and assumes every intermediate node supports `.get()` (`omicron_sm4_stm.py:472-484`). Missing nodes or multiple entries need tests. Time-conversion failures may be silent (`omicron_sm4_stm.py:493-494`).
10. Active-channel selection accepts any integer-convertible value and the first matching key (`omicron_sm4_stm.py:104-115`). The key-only path can fall through to `raw_dt_dct.items()` when the supplied key does not match and no dictionary exists (`omicron_sm4_stm.py:90-115`).
11. NXdata-to-controller linking uses substring matching (`omicron_sm4_stm.py:515`). Tags such as a base scan and its processed variant can overlap, potentially replacing a previously chosen link in the same loop (`omicron_sm4_stm.py:508-517`).
12. Review inherited endpoint derivation, axis-array rearrangement, angle mapping, and configuration-based fields before documenting exact final-file geometry or claiming that `RHK_Angle` is exported as `scan_angle`.

## Validation status

This is a static source review of the supplied scripts. No scanner, runtime conversion, SM4 fixture test or NeXus validation was performed. Dependencies and configuration remain necessary for end-to-end verification.
