# HDF5 vendor and community parsers (`pynxtools-em`)

## Source files reviewed

The descriptions below are based on the supplied parser sources from `src/pynxtools_em/parsers/` in [FAIRmat-NFDI/pynxtools-em](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop/src/pynxtools_em/parsers), with line numbers referring to the develop branch on 14th October. The repository's `develop` branch can change, so line numbers should be rechecked after updates.

- `hfive_base.py` — shared `HdfFiveBaseParser` (675 lines; HDF5 visitor, cache and report helpers).
- `hfive_apex.py` — `HdfFiveEdaxApexParser` (899 lines).
- `hfive_bruker.py` — `HdfFiveBrukerEspritParser` (325 lines).
- `hfive_dreamthreed_legacy.py` — `HdfFiveDreamThreedLegacyParser` (456 lines).
- `hfive_ebsd.py` — `HdfFiveEbsdCommunityParser` (329 lines).
- `hfive_edax.py` — `HdfFiveEdaxOimAnalysisParser` (365 lines).
- `hfive_emsoft.py` — `HdfFiveEmSoftParser` (92 lines).
- `hfive_oxford.py` — `HdfFiveOxfordInstrumentsParser` (422 lines).

## At a glance

| | |
|---|---|
| **Input family** | HDF5-based microscope / EBSD / EDS data; filename extension alone is not sufficient to identify a vendor schema |
| **Common implementation style** | Vendor-specific class derived from `HdfFiveBaseParser`; HDF5 is inspected with `h5py` |
| **Detection** | Usually HDF5 magic-header check plus required root fields, groups, manufacturer and/or version strings |
| **Output** | Mutates and returns a NeXus template dictionary; EBSD paths are normalized through shared EBSD helpers |
| **Common EBSD model** | `EbsdPointCloud`, populated with scan geometry, phase/crystal information, orientations, phase IDs and confidence/contrast data |
| **Shared downstream helpers** | `ebsd_roi_overview(...)`, `ebsd_roi_phase_ipf(...)`; checksums and unit handling where implemented |
| **Caution** | “Supported” means the parser's detection predicates passed; it does not guarantee every optional dataset is present or every modality is implemented |

## General architecture and behaviour

### 1. Construction and support detection

Each vendor parser initializes an identifier manager and a `version` structure separating expected/target signatures (`trg`) from values detected in the source (`src`). It calls `check_if_supported()` during construction and records `self.supported`. When no path is supplied, the constructor logs that a vendor-specific HDF5 file is required. See the constructors and detection methods in each file below.

Most classes first call `has_hfive_magic_header(self.file_path)` and then inspect the HDF5 root with `h5py.File(..., "r")`. Vendor identity is established by required root datasets such as `Manufacturer`, `Version`, `Software Version`, or `Format Version`, or by a set of required groups. Several parsers use a “votes for support” count. Bruker (`== 2`, l. 101), EDAX (`== 2`, l. 107), Oxford (`== 3`, l. 142) and DREAM.3D (`== 2`, l. 161) require all tested fields to match. APEX accepts a single vote (`>= 1`, `hfive_apex.py` l. 126). Community H5EBSD intends `== 2`, but its test is broken (`hfive_ebsd.py` l. 101, see below). EMsoft tests required groups instead of votes. All of this is more selective than extension-based dispatch.

### 2. Parse and normalize

The usual `parse(template)` method returns the incoming template unchanged if `self.supported` is false. If supported, it often computes a SHA-256 checksum, opens the HDF5 file, reads vendor-specific group paths, and translates their content into common concepts. The EBSD implementations typically:
1. read scan/header information (dimensions and step sizes);
2. read phase records and lattice/symmetry information;
3. read per-point orientation, coordinate, phase and quality/contrast arrays;
4. normalize values and units into an `EbsdPointCloud`;
5. call `ebsd_roi_overview(...)` and `ebsd_roi_phase_ipf(...)` to write the normalized content into the template;
6. advance ROI identifiers and clear temporary EBSD state between maps.

These are common patterns, not a promise that every parser implements every step. DREAM.3D normalizes into `EbsdPointCloud` but does not write it back (`TODO::write back`, `hfive_dreamthreed_legacy.py` l. 332) and EMsoft writes nothing. See the specific parser sections below.

### 3. Units, assumptions and incomplete source metadata

The parsers use `pint` quantities and shared unit registries for physical dimensions where supported. Some source formats omit information that the normalized representation needs; parser comments explicitly document assumptions (for example, grid geometry, phase-ID interpretation, or coordinate calibration). Such assumptions are described per parser rather than treated as universal HDF5 behaviour.

## Formula / transformation

This section records numerical transformations that change interpretation of source values. A cast, reshape, unit annotation, or generated axis is distinguished from a calibrated conversion. The line references below are to the supplied source files.

### Shared EBSD transformations

- **Euler angles expressed in degrees → radians.** Bruker ESPRIT and community H5EBSD explicitly use 

  $$
  \phi_{\mathrm{rad}} = \phi_{\mathrm{deg}}\,\frac{\pi}{180}
  $$

   for each of `phi1`, `PHI`, and `phi2`, then wrap the result in a radian quantity (`hfive_bruker.py` l. 256–265; `hfive_ebsd.py` l. 265–273). This is a unit conversion, not an orientation-convention conversion.
- **Negative-angle wrapping.** In the Bruker and community H5EBSD paths, negative Euler components are adjusted by adding the corresponding component of `EULER_SPACE_SYMMETRY` (`hfive_bruker.py` l. 260–264; `hfive_ebsd.py` l. 269–273). Conceptually, for component `k`, 

  $$
  \phi'_k = \begin{cases}\phi_k + S_k, & \phi_k < 0 \\ \phi_k, & \phi_k \geq 0\end{cases}
  $$

   when `φ_k < 0`; otherwise it is unchanged. The exact `S_k` values come from the imported shared constant.
- **Point-cloud/grid coordinates.** Bruker and community H5EBSD construct regularly spaced coordinates from scan size and step information, then tile/repeat them into point order (`hfive_bruker.py` l. 286–310; `hfive_ebsd.py` l. 290–312). The coordinate sequence is 

  $$
  x_i = \operatorname{linspace}(0, n_x-1, n_x)\,\Delta x
  $$

   and similarly for `y`, with `tile`/`repeat` defining the point ordering. Verify the source-specific half-pixel convention before comparing coordinates between vendors.
- **DREAM.3D data shape.** `EulerAngles` is cast to `float32` and reshaped from its spatial dimensions to `(product(first three dimensions), last dimension)` in C order; `Phases` is cast to `int32` and flattened to one value per point, also in C order (`hfive_dreamthreed_legacy.py` l. 409–429). The code wraps Euler values as radians without an additional degree-to-radian factor, so the source is assumed to already use radians (l. 419–421).
- **Phase IDs are not universally transformed the same way.** Community H5EBSD and Bruker preserve the source `Phase` values as `int32` (`hfive_ebsd.py` l. 276–279; `hfive_bruker.py` l. 271–278). DREAM.3D preserves flattened `Phases` values, with comments explaining the special `999`/null-model convention (`hfive_dreamthreed_legacy.py` l. 423–434). EDAX OIM changes an all-zero phase array to ones, based on an explicit assumption that all points belong to the first phase (`hfive_edax.py` l. 303–311). Do not treat these conventions as interchangeable.

### Parser-specific numerical transformations

#### `hfive_apex.py`

- **EDS energy axis:** 

  $$
  E_i = E_0 + i\,\Delta E, \qquad i=0,\ldots,N-1
  $$

  , where `E_0` is `eVOffset`, `ΔE` is `evPch`, and `i = 0 … N-1`; the resulting quantity is converted from eV to keV for the spectrum axis (`hfive_apex.py` l. 577–594). Intensity counts are cast to `int32` (l. 595–600).
- **Element-map axes:** 

  $$
  x_i = i\,\Delta x, \qquad y_j = j\,\Delta y
  $$

   for `i=0…n_x-1`, `j=0…n_y-1`; each axis is represented as a physical quantity and converted to metres before writing (`hfive_apex.py` l. 707–728). The image count array is read as stored (`l. 702–705`).
- **Line-scan energy and position (disabled code, not active behaviour).** `parse_and_normalize_eds_line_lsd()` and the SPD routine (`hfive_apex.py` l. 737 onward) are inside a string literal below a “deactivated” comment (l. 733–735), and their calls are commented out (l. 193, 200–210). The formulas in that block (energy axis $E_i = i\,\Delta E$ with $E_0 = 0$ and `eVPCh` from the attributes, l. 765–778; line length $L=\sqrt{(\Delta x)^2+(\Delta y)^2}$ and positions $s_k=\frac{(k+\tfrac12)L}{N}$, l. 780–807) are snippets for a future extension, not current output.
- **EBSD orientation matrices and coordinates:** orientation matrices are reshaped to `3×3` before conversion through `Orientation.from_matrix` (`hfive_apex.py` l. 423–429). Scan coordinates are generated from the dimensions and step size using the parser's `linspace`/`tile`/`repeat` logic (`l. 445–469`); see that code before assuming the same origin convention as another vendor.

#### `hfive_bruker.py`

- **Euler conversion:** 

  $$
  \phi_{\mathrm{rad}} = \phi_{\mathrm{deg}}\,\frac{\pi}{180}
  $$

   for each Euler component; negative components are then wrapped by adding the corresponding `EULER_SPACE_SYMMETRY` value (`l. 256–265`).
- **Grid coordinates:** generated using the scan dimension and step-size metadata, then tiled/repeated into the flattened point order (`l. 286–310`). Phase arrays are cast to `int32` when their length matches the number of points (`l. 271–278`); MAD values are cast to `float32` and tagged as radians (`l. 317–321`).
- **Lattice angles:** phase lattice angles are converted from degrees to radians (`l. 191–196`).

#### `hfive_dreamthreed_legacy.py`

- **Flattening:** spatial dimensions are collapsed in C order while preserving the final Euler-triplet dimension: 

  $$
  \operatorname{shape}(\mathrm{Euler}) \longrightarrow (n_x n_y n_z,\ n_{\mathrm{components}})
  $$

  ; phase IDs become a 1-D array with `n_x·n_y·n_z` entries (`l. 409–429`).
- **Coordinates:** each dimension is generated as 

  $$
  x_i = \left(i+\frac12\right)\Delta x, \qquad i=0,\ldots,n-1
  $$

   (`l. 436–455`), i.e. the first coordinate is half a step from the origin. Non-square tiling triggers a warning because the coordinate interpretation is less certain (`l. 436–443`).

#### `hfive_ebsd.py`

- **Euler conversion and wrapping:** same explicit degrees-to-radians operation as the Bruker parser, followed by negative-angle adjustment (`l. 265–273`). The source comment says the degree assumption is based on available examples, so treat it as a format-specific assumption.
- **Grid coordinates:** `linspace` values scaled by step size and expanded with `tile`/`repeat` (`l. 290–312`). The header also contains an unresolved comment about `SEPixelSize*` being half of the corresponding step values (`l. 153–154`); the code's actual chosen step-size fields should be consulted before relying on pixel calibration.
- **Lattice angles:** phase lattice angles are converted from degrees to radians (`l. 194–198`).

#### `hfive_edax.py`

- **Euler values:** the three source arrays are copied to `float32`; negative values are adjusted by adding the component-specific symmetry value and the result is labelled radians (`l. 288–300`). The code comments explicitly say EDAX's reported unit/normalization is not confirmed and unusually large values occur. This is an assumption, not a guaranteed calibration.
- **Phase IDs:** if every source phase ID is zero, the parser replaces the whole array with ones; otherwise it copies the original IDs to `int32` (`l. 303–311`). This is a deliberate compatibility assumption, not a generic HDF5 rule.
- **Coordinates:** for schema `OIM Analysis 8.5.1002 x64 [07-17-20]`, source X/Y positions are treated as already calibrated in µm; for other versions they are multiplied by the scan step before being labelled µm (`l. 325–363`). In formula form, 

  $$
  p = p_{\mathrm{source}}
  $$

   for the named version and 

  $$
  p = p_{\mathrm{source}}\,\Delta p
  $$

   for other versions. This version-dependent branch is important to avoid applying calibration twice.
- **Quality metric:** `CI` is cast to `float32` and used as the confidence-index descriptive value (`l. 320–324`).

#### `hfive_oxford.py`

- **Euler and phase values:** Euler values are accepted only if the dataset attribute `Unit` is `rad` (otherwise warning, `EbsdPointCloud` reset and return), wrapped in a radian quantity and passed through `apply_euler_space_symmetry` (`l. 388–399`). Phase IDs are copied to `int32` (`l. 402`). No degree-to-radian multiplication is applied. Band Contrast is cast to `int32` and used as contrast (`l. 419–420`).
- **Coordinates:** source coordinate arrays are treated as pixel coordinates already multiplied by step size; the source comment says no further multiplication is needed (`l. 404–420`). Do not multiply these values by the step again.
- **Lattice parameters:** angles are read as radians only if their `Unit` attribute is `rad`, and dimensions as ångström only if `Unit` is `angstrom`; otherwise warning and reset (`l. 302–331`). There is no degree-to-radian conversion. The radian angles are passed unchanged to diffpy `Lattice` (`l. 332–339`); the source TODO there notes that degrees may be required.

#### `hfive_emsoft.py`

No scientific-data transformation formula is currently implemented in the supplied parser: its `parse()` method returns the template unchanged (l. 88–92). It identifies supported EMsoft files but does not yet normalize arrays or calibrate axes.

### Reading these formulas correctly

- A unit attached to a quantity does not prove that the source numbers were calibrated correctly; this is particularly important for EDAX Euler angles and coordinates.
- `linspace`, `tile`, `repeat`, `reshape`, and `flip`-like operations change ordering or coordinate representation but are not themselves unit conversions.
- Where the source comments say “assumption” or “TODO”, this documentation preserves that uncertainty rather than asserting a universal vendor specification.

## Standard behaviour

The following sequence describes the common path across the HDF5 parser family. It is a family-level summary; each vendor parser may omit or specialize individual steps.

1. **Initialize and identify.** Construct the parser, inspect the HDF5 magic header and check the vendor/schema signature using root attributes or required groups. A matching extension alone is not sufficient (see the detection methods cited in the parser-specific subsections below).
2. **Reject unsupported files.** If the parser's support predicate fails, `parse(template)` generally returns the incoming template without mapping scientific content.
3. **Open and inspect the HDF5 hierarchy.** Open the file read-only with `h5py`, then access vendor-specific paths. Group and dataset names are schema-specific and should not be assumed to be interchangeable across vendors.
4. **Normalize recognized metadata and arrays.** Where implemented, read scan dimensions and step sizes, phase/crystal records, orientations, point coordinates, phase IDs and quality/contrast values. Cast, reshape, generate coordinates or convert units only where the individual parser explicitly does so.
5. **Build shared EBSD structures.** EBSD parsers commonly populate `EbsdPointCloud` and pass normalized information to shared ROI/IPF helpers. This step is not universal: APEX includes EDS paths, Oxford includes selected microstructure/EDS-derived content, EMsoft currently has no content mapping, and DREAM.3D fills `EbsdPointCloud` without writing it (`hfive_dreamthreed_legacy.py` l. 332).
6. **Write to the NeXus template.** Update the supplied template with recognized output fields and return it. Optional datasets or unsupported modalities may be omitted, warned about, or left unprocessed depending on the parser.
7. **Preserve parser-specific assumptions.** Coordinate calibration, grid geometry, phase-ID conventions and version-specific branches are implementation details, not universal properties of HDF5 or EBSD.

## Special behaviour

### `hfive_apex.py` — EDAX / AMETEK APEX (`*.edaxh5`)

**Class and entry points:** `HdfFiveEdaxApexParser` (l. 50–899); constructor (l. 53–97), detection (l. 99–131), source annotation (l. 133–143), top-level parse (l. 145–245).

- **Detection.** Requires an HDF5 magic header and exactly one root group whose attributes `Company` (`EDAX, LLC`) and/or `PRODUCT_VERSION` (one of `2.1.0009.0001`, `2.2.0001.0001`, `2.5.1001.0001`, `V3.0.0601.0001`; l. 70–88) match. One matching vote suffices (`votes_for_support >= 1`, l. 111–131); the source comment says this is deliberately not strict because an IKZ example lacks `Company`. `schema_name` is configured (l. 73) but not tested.
- **EBSD.** Separates header, phase and per-point data into `parse_and_normalize_group_ebsd_header()` (l. 247–274), `parse_and_normalize_group_ebsd_phases()` (l. 277–392), and `parse_and_normalize_group_ebsd_data()` (l. 394–469). The top-level parse orchestrates the relevant groups and emits EBSD ROI overview/IPF content (l. 145–245).
- **EDS.** Unlike the EBSD-only readers, this parser also has routines for field-of-view metadata, spectrum data and area ROIs: `parse_and_normalize_eds_fov()` (l. 471–545), `parse_and_normalize_eds_spc()` (l. 547–603), and `parse_and_normalize_eds_area_rois()` (l. 605–731). These are the key entry points for APEX EDS-related content.
- **Implementation notes.** Uses `EbsdPointCloud`, `h5py`, NumPy, lattice/structure objects, orientation handling, X-ray-line lookup and unit/checksum utilities (imports l. 20–43). The class has separate ID counters for entries, events, ROIs, images and spectra (l. 53–69), reflecting its broader modality coverage.
- **Deactivated code.** Line-scan (`LSD`) and SPD parsing (`parse_and_normalize_eds_line_lsd()`, `…_spd()`, l. 737 onward) are inside a string literal and are not called (l. 193, 200–210). Active EDS paths are FOV, spectrum and area ROIs for `Live Map` groups (l. 165, 191–198).

### `hfive_bruker.py` — Bruker ESPRIT HDF5 (`*.h5`)

**Class and entry points:** `HdfFiveBrukerEspritParser` (l. 44–325); detection (l. 80–104), parse (l. 106–129).

- **Detection.** Requires an HDF5 header and root-level `/Manufacturer` and `/Version`; both must match configured Bruker Nano / `Esprit 2.X` signatures for support (l. 58–68, 80–104).
- **EBSD flow.** Parses the EBSD header (l. 131–153), phase groups (l. 155–230), and point data (l. 232–325). The top-level method coordinates these stages and writes ROI overview/IPF output (l. 106–129).
- **Normalization.** Imports shared EBSD space-group/symmetry utilities, string decoding, `EbsdPointCloud`, lattice structures and units (l. 20–41). Phase records include lattice and symmetry-related values; scan points are normalized to the shared EBSD model.
- **Scope.** The implementation shown is centered on EBSD maps rather than the multi-modality EDS path present in APEX.

### `hfive_dreamthreed_legacy.py` — community DREAM.3D legacy HDF5 (`*.dream3d`)

**Class and entry points:** `HdfFiveDreamThreedLegacyParser` (l. 87–455); detection (l. 139–162), content discovery (l. 165–316), parse (l. 318–336).

- **Format model.** The module comments explain that DREAM.3D files represent outputs of versioned filters/workflows, so file contents depend on the filter combination, filter versions, software version and file version (l. 34–50). The parser deliberately focuses on a limited, useful set of EBSD-derived content rather than attempting to model every possible filter output.
- **Detection and discovery.** After checking the HDF5 signature and that the root attributes `DREAM3D Version` and `FileVersion` both match the configured values (l. 142–162), `search_normalizable_ebsd_content()` searches for EBSD-like data that can be normalized (l. 165–316).
- **Normalization.** Header, phase and point data are handled separately by `parse_and_normalize_ebsd_header()` (l. 338–352), `parse_and_normalize_ebsd_phases()` (l. 355–407), and `parse_and_normalize_ebsd_data()` (l. 409–455).
- **Intended use.** The module comments frame this as extracting useful inverse-pole-figure / reconstructed microstructure information from reconstructed, discretized 3-D microstructures (l. 47–50). This should not be read as comprehensive preservation of all DREAM.3D filters or all DREAM.3D schema versions.
- **No output yet.** After normalization, `parse()` only increments `roi_id` and resets the point cloud (`# TODO::write back`, l. 326–334); `ebsd_roi_overview` and `ebsd_roi_phase_ipf` are never called, so nothing is written to the template. Like EMsoft, it is currently not a content-writing parser.

### `hfive_ebsd.py` — community / modified H5EBSD (`*.h5`, `*.h5ebsd`)

**Class and entry points:** `HdfFiveEbsdCommunityParser` (l. 44–329); detection (l. 80–104), parse (l. 106–129).

- **Detection.** Requires HDF5 magic plus root `/Manufacturer` and `/Version`, with configured values `xcdskd` and `0.1` (l. 58–68, 80–104). The class docstring describes the input as modified H5EBSD, likely from the Britton group (l. 44–46). **Known defect:** l. 101 tests `if self.supported == 2:` instead of `votes_for_support == 2`, so `supported` can never become `True` and, as written, this parser is never used.
- **EBSD flow.** Header, phases and point data are normalized by the routines at l. 131–153, 155–232 and 234–329. The top-level parser writes ROI overview/IPF output (l. 106–129).
- **Implementation notes.** It uses shared space-group, symmetry, string-reading and EBSD helpers (l. 20–41). The support test is tied to the implementation's stated manufacturer/version signature; the `.h5` extension alone does not qualify a file.
- **Missing failure branch.** Unlike `hfive_bruker.py` (`else: … return`, l. 266–269), the Euler block here has no `else`, so `n_pts` is undefined if the Euler shape does not match `n_x·n_y` (l. 262–278). The data stage also requires `X SAMPLE` and `Y SAMPLE` (l. 242–254) although positions are regenerated from `NCOLS`/`XSTEP` rather than read.

### `hfive_edax.py` — EDAX OIM Analysis (`*.oh5` / `*.h5`)

**Class and entry points:** `HdfFiveEdaxOimAnalysisParser` (l. 45–363); detection (l. 85–110), parse (l. 112–134).

- **Detection.** Checks HDF5 magic and root `/Manufacturer` and `/Version`. The configured source signatures identify EDAX and specific OIM Analysis writer/version strings (l. 59–74, 85–110).
- **EBSD flow.** Header, phase and point data use separate normalization methods at l. 136–169, 175–265 and 267–363. The top-level parser coordinates those methods and produces the ROI overview/IPF output (l. 112–134).
- **Format-specific decisions.** The point-data code documents assumptions around the meaning of phase ID `0` and uses a special case for the OIM Analysis 8.5.1002 coordinate calibration (phase assumption l. 303–311, coordinate calibration l. 325–363). These are explicit compatibility choices, not generic EBSD rules.
- **Normalization dependencies.** Shared tiling/symmetry utilities and the `EbsdPointCloud` abstraction are imported at l. 20–42.

### `hfive_emsoft.py` — EMsoft HDF5

**Class and entry points:** `HdfFiveEmSoftParser` (l. 28–92); detection (l. 62–86), parse (l. 88–92).

- **Detection.** Requires HDF5 magic and the root groups `CrystalData`, `EMData`, `EMheader`, `NMLfiles`, and `NMLparameters` (l. 62–78). The version/source fields are then populated from the configured EMsoft labels (l. 79–86).
- **Current parse behaviour.** The parse method logs that it is using the EMsoft parser, emits a critical `TODO::add functionality` message, and returns the template without mapping HDF5 content (l. 88–92).
- **Important distinction.** This is currently a format recognizer / placeholder, not a functional content-normalization parser. A successful `supported` check must not be interpreted as evidence that EMsoft data are already transferred into NeXus.

### `hfive_oxford.py` — Oxford Instruments AZtec / H5OINA (`*.h5oina`)

**Class and entry points:** `HdfFiveOxfordInstrumentsParser` (l. 59–420); detection (l. 114–149), parse (l. 151–225).

- **Detection.** Requires HDF5 magic and `/Manufacturer`, `/Software Version`, and `/Format Version`. All three values must match the configured Oxford Instruments / AZTec / H5OINA signatures (l. 74–101, 114–149).
- **EBSD.** The parser currently selects the root slice named `"1"` when it contains `/1/EBSD`, then reads header, phases and point data through `parse_and_normalize_slice_ebsd_header()` (l. 227–260), `parse_and_normalize_slice_ebsd_phases()` (l. 263–370) and `parse_and_normalize_slice_ebsd_data()` (l. 372–420). The selected EBSD content is written through the shared ROI overview/IPF helpers (l. 159–172).
- **Microstructure / EDS-derived content.** The top-level parse also walks numbered groups for `Electron Image/Data/Feature/Area` and EDS composition plus sigma datasets; it builds `Crystal` records and maps them with `microstructure_to_template()` when any are found (l. 174–221).
- **Scope caveat.** The code explicitly notes that other imaging modalities remain TODO (l. 224). EBSD selection is currently limited to slice `"1"` rather than every possible slice (l. 160–164).

## Cross-parser comparison

| Parser | Input identity / support signature | Normalized content indicated by implementation |
|---|---|---|
| `hfive_apex.py` | EDAX APEX signature and schema version | EBSD plus EDS field-of-view, spectra and area ROIs |
| `hfive_bruker.py` | Bruker Nano + `Esprit 2.X` | EBSD header, phases and point data |
| `hfive_dreamthreed_legacy.py` | DREAM.3D legacy structure and discoverable EBSD content | Selected EBSD-derived content from workflow/reconstruction files, normalized in memory only (**not yet written to the template**) |
| `hfive_ebsd.py` | `Manufacturer=xcdskd`, `Version=0.1` | Modified/community H5EBSD maps |
| `hfive_edax.py` | EDAX OIM Analysis writer/version signature | EBSD header, phases and point data |
| `hfive_emsoft.py` | Required EMsoft root groups | **Detection only; parse functionality is TODO** |
| `hfive_oxford.py` | Oxford manufacturer + software and format versions | EBSD plus selected feature-area / EDS composition microstructure content |

## Practical interpretation

1. **Use the parser's support test, not the extension, as the identity test.** HDF5 is a container and can hold unrelated schemas.
2. **Expect vendor-specific paths.** Each reader handles the source schema explicitly, then maps only understood fields to common concepts.
3. **Treat assumptions as part of provenance.** Coordinate calibration, grid tiling, phase-ID conventions and missing metadata may affect interpretation.
4. **Distinguish detection from implementation coverage.** EMsoft is the clearest example: it recognizes a file layout but currently does not normalize content.
5. **Review tests and examples alongside source before changing mappings.** The source code includes format/version-specific branches and comments documenting unresolved schema differences.

## Behaviour to investigate / maintenance checklist

- Whether the parser registry's dispatch order avoids ambiguous signatures when multiple HDF5 readers could inspect a file.
- Whether unsupported schema versions fail clearly and whether adding a version requires a fixture and regression test.
- Whether missing optional datasets leave a valid partial ROI or reset the `EbsdPointCloud`; inspect each parser's warning/early-return branches.
- Whether coordinate units and calibration are consistent across writer versions (especially EDAX OIM's version-specific handling at `hfive_edax.py` l. 325–350).
- Whether DREAM.3D's filter/version combinations are represented sufficiently by the current discovery heuristics.
- What minimum useful normalization should be implemented for `hfive_emsoft.py` after the current TODO.
- Whether Oxford files with multiple slices should process more than slice `"1"` (`hfive_oxford.py` l. 159–172).
- Fix `hfive_ebsd.py` l. 101 (`self.supported == 2` → `votes_for_support == 2`) and add an `else` branch for the Euler shape check as in `hfive_bruker.py` l. 266–269; add a regression fixture, because the parser is currently unreachable.
- `sorted(list(...), key=int)` runs before the `isdigit()` filter (`hfive_bruker.py` l. 164, `hfive_ebsd.py` l. 164); a non-numeric phase group raises `ValueError`.
- Decide whether DREAM.3D should write its normalized `EbsdPointCloud` (`hfive_dreamthreed_legacy.py` l. 332).
- Oxford passes radian lattice angles to diffpy `Lattice` (`hfive_oxford.py` l. 332–339, source TODO); verify against a known phase.
- APEX accepts a file on one matching attribute (`hfive_apex.py` l. 126); decide whether a stricter test is wanted.
