# MTex `*.mtex.h5` parser (`pynxtools-microstructure`)

## Source files reviewed

- `pynxtools_microstructure/…/nxs_mtex.py` — `NxEmNxsMtexParser` plus helpers `hfive_dataset_to_template()` and `hfive_attribute_to_template()` (815 lines). The exact folder was not stated.
- Imported, **not supplied**: `pynxtools.dataconverter.chunk.prioritized_axes_heuristic`; `pynxtools_em.utils.default_config` (`DEFAULT_COMPRESSION_LEVEL`, `DEFAULT_VERBOSITY`); `pynxtools_em.utils.get_checksum.get_sha256_of_file_content`.
- External: `h5py`, `numpy`, `mmap`.
- Project: [pynxtools-microstructure](https://github.com/FAIRmat-NFDI/pynxtools-microstructure).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `mtex l.` = `nxs_mtex.py`.

## At a glance

| | |
|---|---|
| **Input format** | HDF5 written by an MTex (Matlab) script, `*.mtex.h5` / `*.mtex.hdf5`, already organised like NXem (`/entry1/roi1/ebsd/indexing/…`, `/entry1/profiling`) |
| **Parser class** | `NxEmNxsMtexParser` (mtex l. 123–814) |
| **Reader** | `h5py.File(…, "r")`, reopened in every `parse_*` method (mtex l. 197, 225, 334, 353, 405, 468) |
| **Raw-data storage** | None kept: values are copied directly into the template |
| **Output** | Entries in the `template` dict. Scalars as Python/NumPy values; arrays as `{"compress": ndarray, "chunks": …, "strength": level}` (mtex l. 79–93); attributes as `…/@name` keys (mtex l. 110–119) |
| **Target definition** | `NXem` (EBSD, microstructure) with `NXmicrostructure*` base classes (mtex l. 18–24) |
| **Entry** | `entry_id` (default 1) builds `ENTRY[entry<id>]`; the source group is always `/entry1` (mtex l. 131, 198–199) |
| **Project context** | Decouples expensive MTex processing (about 2.4k datasets, about 120 h; mtex l. 27–34) from metadata completion. Part of a family with `oasis_config.py`. |

**Standard behaviour.** The constructor accepts files ending in `.mtex.h5` or `.mtex.hdf5`. `check_if_mtex_hfive()` verifies the HDF5 signature and three required groups. `parse()` hashes the file and then runs six copy routines: profiling, MTex configuration, various scalars, ROI default plot, phases (IPF, ODF), microstructure (points, polylines, crystals, interfaces, triple junctions) (mtex l. 166–191). Every copy goes through the two helpers.

## Formula / transformation

### Helper: value conversion

**Location:** `hfive_dataset_to_template()` (mtex l. 53–94).

| Source shape | Result | Lines |
|---|---|---|
| source path missing | template untouched | 60–61 |
| `()` scalar | `value = dset[()]`; `bytes` decoded as UTF-8 | 62–67 |
| `(1,)` | warning, first element stored (scalar promotion unrolled) | 68–72 |
| anything else | `{"compress": array, "chunks": prioritized_axes_heuristic(array, arange(ndim)), "strength": DEFAULT_COMPRESSION_LEVEL}` | 73–93 |

The compressed/uncompressed branch at mtex l. 75–93 builds the same dict in both arms.

### Helper: attribute copy

**Location:** `hfive_attribute_to_template()` (mtex l. 97–120). Target `trg/trg_dst_name/@trg_att_name` (or `trg/@trg_att_name` without dataset name); skipped if the source dataset or the attribute is missing; the attribute value is copied unchanged (mtex l. 119). The comment (mtex l. 109) states that attribute names are pre-harmonised on both sides.

### Parser: boolean flags

**Location:** mtex l. 289–296.

```python
template[f"{trg}/{dst_name}"] = bool(h5r[f"{src}/{dst_name}"])
```

### Parser: path mapping examples

| Source (HDF5) | Target (template) |
|---|---|
| `/entry1/profiling/<x>_elapsed_time` | `/ENTRY[entry1]/profiling/eventID[event_mtex]/<x>_elapsed_time` (mtex l. 198–208) |
| `/entry1/roi1/ebsd/indexing/mtex/numerics/eps` | `/ENTRY[entry1]/roiID[roi1]/ebsd/indexing/microstructureID[microstructure1]/configuration/programID[program1]/mtex/COLLECTION[numerics]/eps` (mtex l. 226–228, 276–285) |
| `…/indexing/phaseN/unit_cell/a` | `…/indexing/phaseID[phaseN]/unit_cell/a` (mtex l. 406–434) |
| `…/microstructure1/cg_polyline/…` | `…/microstructureID[microstructure1]/polylines/…` (mtex l. 487–526) |
| `…/interfaces/indices_polylines` | `…/interfaces/indices_polyline` (singular) (mtex l. 568–576) |

## Standard behaviour

1. **Gate.** Name ends with `.mtex.h5` / `.mtex.hdf5` (mtex l. 129). `entry_id <= 0` becomes 1 (mtex l. 131).
2. **Signature.** `mmap` the file, first four bytes must be `\x89HDF` (mtex l. 144–148). `OSError`/`FileNotFoundError` log a warning and the file is unsupported (mtex l. 149–151).
3. **Required content.** `/entry1/roi1/ebsd/indexing/phase1`, `…/indexing/roi`, `…/indexing/microstructure1/crystals` must exist, else a warning and unsupported (mtex l. 155–164).
4. **Hash.** SHA-256 computed and logged (mtex l. 169–173); stored in `self.file_path_sha256` only.
5. **Profiling** — five `<x>_elapsed_time` (`ebsd, load, microstructure, odf, total`) with `units` (mtex l. 193–219).
6. **MTex configuration** (mtex l. 221–328)
   - `conventions/euler_angle` (mtex l. 239–249).
   - `numerics` — `eps`, `fft_accuracy`, `max_sone_bandwidth`, `max_stwo_bandwidth`, `max_sothree_bandwidth` (mtex l. 276–285).
   - `miscellaneous` — four booleans and `voronoi_method` (mtex l. 287–301).
   - `system/memory` with `units` (mtex l. 303–309).
   - `program1…3` with `version` attribute, written to `PROGRAM[program<idx>]` (mtex l. 311–327).
7. **Various** — `indexing_rate`, `number_of_scan_points`, `pixel_shape`, `pixel_unit_cell` with `units` (mtex l. 330–347).
8. **ROI default plot** — `axes`, `signal`, `axis_x/y_indices` attributes; `axis_x`, `axis_y`, `data` with their attributes (`long_name`, `units`, `CLASS`, `IMAGE_VERSION`, `SUBCLASS_VERSION`); `descriptor`, `title` (mtex l. 349–399).
9. **Phases** — every group matching `phase[0-9]+` (mtex l. 410–412): `index_offset`, `name`, `number_of_scan_points`; `phase0` (not indexed) stops there (mtex l. 423–424); other phases add unit cell `a, b, c, alpha, beta, gamma` (+units) and `point_group` (mtex l. 425–453), IPF 1 (mtex l. 454–457) and ODF 1 (mtex l. 458–461).
10. **IPF** (`parse_phase_ipf`, mtex l. 660–714) — `color_model`, `projection_direction`; for `map` and `legend` the NXdata attributes, axes, `data`, `title` (legend units skipped, mtex l. 690).
11. **ODF** (`parse_phase_odf`, mtex l. 716–814) — `characteristics/texture_index`, `configuration/*`, `phi_two_plot` (intensity and three angle axes), `kth_extrema`, `noncircular` as `PROCESS[noncircular]`.
12. **Microstructure** (mtex l. 464–658) — `configuration`, `points`, `polylines`, `crystals`, `crystals/orientation`, `interfaces`, `interfaces/misorientation`, `triple_junctions`.

## Special behaviour

1. **`parse()` does copy data** although its docstring says it passes (mtex l. 167–168).
2. **Known issues are listed in the code** (mtex l. 174–183, 525, 644, 653): booleans stored as `uint8` by MTex, unitless memory, `roi` not recognised in the NXdata model, `use_these` → `depends_on` refactor, a validation bug with `depends_on` in `NXmicrostructure_feature`.
3. **Hot-fixes overwrite `depends_on`** with absolute paths for `polylines` (mtex l. 520–526) and `triple_junctions/indices_polyline` (mtex l. 653–656), using `/entry{id}/roi1/...` literals.
4. **Selective copy.** Only IPF 1 and ODF 1 per phase are read (mtex l. 454, 458); parts of the MTex plotting configuration are disabled by a string literal (mtex l. 251–274) and a commented list of `conventions` (mtex l. 242–247).
5. **Everything is read into memory** before it is wrapped for compression (mtex l. 74).
6. **`AXISNAME_indices[@…]`** is used as a target attribute name for the axis index attributes (mtex l. 360–370, 676–686, 749–763).

## Behaviour to investigate

1. **`bool(dataset)` is always true.** `h5py` objects define truthiness as "valid object", not as value, so `bool(h5r[...])` at mtex l. 296 stores `True` for all four flags (`inside_poly`, `methods_advise`, `mosek`, `stop_on_symmetry_mismatch`). It should read the value, `bool(h5r[...][()])`. Not run here (h5py was not installable in the review sandbox); confirm with a file in which a flag is false. A missing dataset also raises `KeyError`, unlike the other copy calls.
2. **Triple-junction indices are never copied.** The calls at mtex l. 625–633 and 645–652 pass arguments in the wrong order: `hfive_dataset_to_template(src, name, trg, h5r, name, template)` puts `h5r` in the `trg_dst_name` slot and the string in `obj`. The function then tests `src_path not in obj` on a string and returns without writing. The matching `depends_on` attributes are still written (mtex l. 634–643, 654–656), so the template can hold attributes without their datasets.
3. **`AttributeError` for non-matching file names.** If the name does not end in `.mtex.h5`/`.mtex.hdf5`, `self.supported` is never set, but is read at mtex l. 135.
4. **Empty file.** `mmap.mmap(fileno, 0)` raises `ValueError` on an empty file; only `OSError` is caught (mtex l. 145, 149).
5. **Docstrings with the wrong extension.** `*.nxs.mtex` (mtex l. 124, 167) vs `.mtex.h5` (mtex l. 129).
6. **Hash not stored.** `file_path_sha256` is only logged and held on the object (mtex l. 170–173); nothing in the template records it.
7. **Hard-coded source groups.** `/entry1`, `roi1`, `microstructure1`, `program1…3` (mtex l. 156–160, 198, 226, 469); `entry_id` changes only the target. Files with other group names are ignored with a warning.
8. **Duplicate branch.** Both arms of the compression `if` are identical (mtex l. 75–93).
9. **Group sources.** The comment at mtex l. 57 mentions groups, but `obj[src_path].shape` fails on an `h5py.Group`.
10. **Bytes arrays.** Attributes and non-scalar string datasets are copied unchanged (mtex l. 74, 119).
11. **Variable `trg` used for a source path** in the validation loop (mtex l. 156–163) — confusing, not wrong.
12. **`phase` regex.** `re.match("phase[0-9]+", name)` is not anchored at the end (mtex l. 411), so `phase1_old` matches.
13. **`AXISNAME_indices[@axis_x_indices]`** contains a second `@` inside the brackets (mtex l. 367). Check against the template naming rules of the installed pynxtools version.
14. **Unit attributes are copied for some fields only**, e.g. `numerics` has none (mtex l. 276–285); depends on what MTex writes.
15. **`depends_on` for `polylines`** is forced to `…/microstructure1/points`, which the comment calls an MTex script bug (mtex l. 522–526).
16. **`entry_id` used in absolute `depends_on`** strings but the target keys use `ENTRY[entry<id>]` (mtex l. 523, 655), so both must agree.
17. **Reopening the file six times** (mtex l. 197–468) is simple but repeats I/O.

## Scanner findings

No scanner run was performed for `pynxtools-microstructure`.
