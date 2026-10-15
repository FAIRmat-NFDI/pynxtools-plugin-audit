# Nion Swift project parser (`pynxtools-em`)

## Source files reviewed

- `src/pynxtools_em/parsers/nxs_nion.py` — `NionProjectParser` (646 lines).
- Imported, **not** reviewed: `configurations/nion_cfg.py` (`NION_DYNAMIC_*`, `NION_STATIC_*`, `NION_WHICH_IMAGE`, `NION_WHICH_SPECTRUM`), `utils/nion_utils.py` (`nion_image_spectrum_or_generic_nxdata`, `read_numpy_array_metadata`, `uuid_to_file_name`), `concepts/mapping_functors_pint.py` (`add_specific_metadata_pint`), external `nion.swift.model.NDataHandler`.
- Project: [pynxtools-em, branch develop](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop), parsers in [`src/pynxtools_em/parsers`](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop/src/pynxtools_em/parsers).

**Line-number note:** References below refer to `nxs_nion.py` in the develop branch on 14th October 2026. `l.` = `nxs_nion.py`.

## At a glance

| | |
|---|---|
| **Input format** | Nion Swift project: either a `.zip` archive of the project or a `.nsproj` file with its sibling `<name> Data` directory (l. 105–113, 176) |
| **Parser class** | `NionProjectParser` (l. 59–646); no base class |
| **Readers** | `zipfile.ZipFile` and `mmap` for the container (l. 117–118, 135), `yaml.safe_load` for `*.nsproj` (l. 369, 373), `nion.swift.model.NDataHandler` for `*.ndata` (l. 245, 265, 305), `h5py` for `*.h5` (l. 326) |
| **Raw-data storage** | Three dicts keyed by UUID file stem: `proj_file_dict`, `ndata_file_dict`, `hfive_file_dict` (l. 91–95); arrays are read lazily, one display item at a time |
| **Entry point** | `parse()` (l. 439–449) → `parse_project_file()` (l. 361–437) |
| **Output** | One `eventID[eventN]` per display item that holds a supported array: `spectrumID[spectrum1]`, `imageID[image1]` or `DATA[data1]` NXdata plus instrument metadata (l. 512–578) |
| **Metadata mapping** | `add_specific_metadata_pint` with eight dynamic and two static config tables (l. 461–486) |
| **Switches** | `self.cfg` dict with six booleans (l. 77–84) |
| **Verbosity** | Hard-coded `verbose: bool = True` (l. 66); `DEFAULT_VERBOSITY` is not imported (l. 49) |
| **Project context** | The only parser in `pynxtools-em` that reads a *project* (a database of many datasets) and the only one that takes no sha256 into the template |

**Standard behaviour.** The constructor classifies the file as zipped or unzipped, indexes every `*.h5`, `*.ndata`, `*.nsproj` member by its stem (the stem is the UUID), runs two sanity tests and sets `supported` (l. 102–226). `parse()` loads the `*.nsproj` YAML, iterates its `display_items`, follows each item's `data_item_reference` UUID to the matching `*.ndata` or `*.h5` file, reads the JSON metadata and the array, writes metadata first and data second (l. 361–437, 315–318, 350–358).

**Comparison with the RSCIIO parsers.** No rosettasciio, no `obj` dicts with `data/axes/metadata/original_metadata`. Axes come from `dimensional_calibrations` in the Nion metadata (l. 497) rather than from `obj["axes"]`. Metadata is flattened with `fd.FlatDict(..., "/")` as in the other parsers. Source annotation writes only `context`, not file name or checksum (l. 233–238).

## What a Nion Swift project contains (as the code assumes)

| Member | Where read | Content used |
|---|---|---|
| `*.nsproj` | l. 361–373 | YAML/JSON; key `display_items`, each a dict with `type`, `uuid`, `created`, `display_data_channels` (l. 384–390) |
| `*.ndata` | l. 241–320 | Zip container; `metadata.json` (l. 260–267) and `data.npy` (l. 287–306) |
| `*.h5` | l. 322–359 | HDF5 dataset `data`; metadata JSON in attribute `data.attrs["properties"]` (l. 331–333) |
| UUID link | l. 393–395 | `display_data_channels[0]["data_item_reference"]` → `uuid_to_file_name()` → stem of the `*.ndata`/`*.h5` file |

## Formula / transformation

### Axis arrays

**Location:** l. 589–645.

$$
x_k = o + k\cdot s,\qquad k = 0,\dots,N-1
$$

`o = axis["offset"]`, `s = axis["scale"]`, `N = np.shape(numpy_array)[idx]` (l. 591–594). `axis` is one entry of `flat_metadata["dimensional_calibrations"]` (l. 497). Output dtype and long name depend on units:

| Case | dtype | `@long_name` | Lines |
|---|---|---|---|
| `units == ""`, spectrum | `int32` | `Identifier spectrum` | 596–605 |
| `units == ""`, image | `int32` | `Identifier image` | 606–615 |
| `units == ""`, other | `float32` | axis name | 616–626 |
| `units == "eV"` | `float32`, `@units` set | `Energy (eV)` | 633–641 |
| other unit | `float32`, `@units` set | `Coordinate along <x>-axis (<unit>)` | 633–635, 642–645 |

### Axis index attribute

`@AXISNAME_indices[<name>_indices] = len(axis_names) - 1 - idx` (l. 583–586). The comment at l. 581–582 states that `axis_names` and `dimensional_calibrations` are aligned but reversed with respect to the indices; for generic data the names are reversed explicitly with `[::-1]` (l. 573–575).

### Unit combination

`nion_image_spectrum_or_generic_nxdata(axes)` (l. 498; defined in `utils/nion_utils.py`, not reviewed) returns a string. It is looked up in `NION_WHICH_SPECTRUM` (l. 519) and `NION_WHICH_IMAGE` (l. 537); each value is a pair `(NXdata group name, axis_names)` (l. 522, 536, 540, 554). The remaining case is tested with `value in ["1/", "iteration"]` after `split(";")` (l. 555–557).

## Standard behaviour

1. **Construction.** `entry_id` clamped to ≥ 1 (l. 71); `cfg` defaults all `True` (l. 77–84); `id_mgn = {"event_id": 1}` (l. 85).
2. **Type detection.** `.zip` → zipped, `.nsproj` → unzipped, anything else → debug message and return (l. 105–113).
3. **Zip magic number.** `mmap` the file and require `PK\x03\x04` (l. 117–123); `OSError`/`FileNotFoundError` caught (l. 130–132).
4. **Index zipped members.** `*.h5|*.hdf|*.hdf5`, `*.ndata`, `*.nsproj` are registered by stem (l. 136–174). First occurrence of a key wins (l. 147, 159, 171).
5. **Index unzipped project.** `glob` over `<stem> Data/**/*` (l. 176–204); `*.nsproj` itself is the input so `proj_file_dict` stays empty.
6. **Test 2.** `ndata` and `hfive` key sets must be disjoint (l. 206–210).
7. **Test 3.** Zipped only: exactly one `*.nsproj` (l. 211–215).
8. **Parse project.** Load YAML (l. 363–373), require `display_items` (l. 384–386).
9. **Select display items.** Keep items with keys `type, uuid, created, display_data_channels` and exactly one channel that has `data_item_reference` (l. 387–395).
10. **Route.** UUID key in `ndata_file_dict` → `process_ndata`; else in `hfive_file_dict` → `process_hfive`; else warning (l. 397–436).
11. **`process_ndata`.** `nsnd.parse_zip` (l. 245), read `metadata.json` (l. 260–267), flatten, then read `data.npy` (l. 286–319); metadata mapped, then data written (l. 315–318); `break` after the first `data.npy` (l. 319).
12. **`process_hfive`.** Reads `data.attrs["properties"]` as JSON (l. 331–333), mapping and writing as for ndata (l. 350–358).
13. **Metadata mapping.** Dynamic tables with identifier `[entry_id, event_id, 1]` (l. 460–471); static detector and lens tables with `[entry_id, 1]` (l. 480–486).
14. **Data writing.** Skip if `parse/data` is off (l. 506) or the unit combination is empty (l. 509); increment `event_id` (l. 513); branch spectrum / image / generic (l. 519–578); write axes (l. 580–645). Arrays are passed as `{"compress", "strength", "chunks"}` dicts with `prioritized_axes_heuristic` (l. 528–534).

## Special behaviour

1. **`cfg` switches** (l. 77–84): `sha256/compute`, `parse/metadata`, `parse/data`, `parse/data/images`, `parse/data/spectra`, `parse/data/other`. They can only be changed by editing `parser.cfg` after construction; there is no constructor argument. With both `parse/metadata` and `parse/data` off, only shape and dtype are logged (l. 290–303, 345–348).
2. **Inspection mode.** The comment at l. 277–282 documents that the missing `break` in verbose mode was used to survey metadata over five years of data; the loop `break`s after the first `metadata.json` only when `verbose` is false (l. 275–276).
3. **Checksum.** Computed only for debug logging (l. 128, 144, 156, 168, 188, 200); `self.file_path_sha256` stays `None` (l. 90). The checksum and file-name lines of `annotate_information_source` are commented out "to reduce computational costs" (l. 233–236).
4. **Source annotation** writes only `PROCESS[process]/input/context` with the path of the member file inside the project (l. 237–238, 523–525).
5. **One event per display item** (comment l. 87–89); `event_id` is incremented only when an array is actually written (l. 513).
6. **Static quantities are overwritten.** Detector and lens static tables use identifier `[entry_id, 1]` for every display item, last write wins (l. 472–486).
7. **Axis names for generic data** are reversed (`[::-1]`, l. 575). The Gatan and Velox parsers do not reverse.
8. **Generic data are excluded** if any axis unit is `1/` or `iteration` (l. 555–557, 576–578).
9. **Unitless axes** are written as `int32` for spectra and images (l. 597–612) and are not compressed, unlike in the RSCIIO parsers.
10. **Hard-coded `eV`** for the energy long name (l. 636); comment at l. 637–638 refers to the Gatan base-unit solution.
11. **Simple approach.** Only one array is in memory at a time; the project is parsed "in place" (l. 443–447).
12. **7z** is mentioned as a possible future input (l. 100).

## Behaviour to investigate

1. **`DEFAULT_VERBOSITY` not used.** `verbose=True` (l. 66) makes every default run log the flat metadata and compute and log a sha256 of every member (l. 140–145, 152–157, 164–169, 269–274). On large projects this is costly; compare the other parsers, which take `DEFAULT_VERBOSITY`.
2. **No `file_path` guard.** `self.file_path` is set only `if file_path:` (l. 69–70) but `check_if_nionswift_project()` is always called (l. 99); an empty path raises `AttributeError` at l. 105 instead of logging a warning as the other parsers do.
3. **Empty file.** `mmap.mmap(fp.fileno(), 0, ...)` on a zero-length file raises `ValueError` (l. 118), which is not caught (l. 130 catches `OSError`, `FileNotFoundError`).
4. **Stem extraction for `.hdf`/`.hdf5`.** The stem is built with `.replace(".h5", "")` for all three extensions (l. 146, 190), so `abc.hdf` keeps its extension and cannot match a UUID from `uuid_to_file_name`. `file.rfind("/")` (l. 146, 158, 170, 190, 202) also assumes POSIX separators for `glob` results.
5. **Test 3 only for zipped projects** (l. 211). For `.nsproj` input no check is made that the file is a project at all beyond the suffix.
6. **Display items with several channels** are silently skipped (l. 391); items without `data_item_reference` (l. 392) too.
7. **Event id and metadata order.** In `process_ndata`/`process_hfive` the metadata is mapped *before* the data function decides whether to write (l. 315–318, 350–358). If the data function returns early (`parse/data` off, empty `unit_combination`, l. 506–510) the id is not incremented, so the next item writes its metadata into the same `eventID`. Static tables are overwritten anyway (special 6).
8. **HDF5 attribute read before existence check.** `h5r["data"].attrs["properties"]` is accessed at l. 331–333 and the test `"data" not in h5r` follows at l. 341–343; a file without `data` raises `KeyError`. A missing `properties` attribute raises too.
9. **`nparr` type.** l. 308 only logs if `nparr` is an `ndarray`; `process_event_data_em_data` is called regardless (l. 316–318).
10. **Axis-name count vs. separator.** `axis_names` for generic data is cut with `len(unit_combination.split("_"))` (l. 574) while the same string is split on `";"` at l. 556 and the MRC parser's keyword uses `;` (`"dimensionless;meter;meter"`, `rsciio_mrc.py` l. 567). If the Nion keyword also uses `;`, `split("_")` yields one element and `axis_names[idx]` (l. 590) fails for 2D+ generic data. Needs a test against `nion_image_spectrum_or_generic_nxdata`.
11. **`int32` cast of unitless axes** (l. 597–612): `offset + k*scale` with non-integer scale or offset is truncated.
12. **`DATA[data1]` annotation order.** `annotate_information_source` runs (l. 559–561) before the `parse/data/other` test (l. 562–563); the context is written even when the data group is skipped. Spectra and images test first (l. 520, 538).
13. **Unit-agnostic energy.** Only the literal `"eV"` gets an energy label (l. 636); `keV` falls to "Coordinate along …".
14. **Unzipped branch encoding.** `open(self.file_path)` without `encoding` (l. 372) vs. `encoding="utf-8"` in the YAML parsers.
15. **`h5py` on a `ZipExtFile`.** `h5py.File(file_hdl, "r")` (l. 326) on a compressed zip member relies on seekable file-like access; each seek decompresses. Check performance with large `*.h5`.
16. **Multiple `*.nsproj` in unzipped mode** cannot occur (the file itself is the project), but the loop at l. 366–370 keeps only the last one in zipped mode; Test 3 prevents more than one.

## Scanner findings

No scanner run was performed for `pynxtools-em`.
