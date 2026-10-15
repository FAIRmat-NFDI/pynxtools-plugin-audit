# Image parsers: PNG sets and vendor-specific TIFF (`pynxtools-em`)

## Source files reviewed

The descriptions below are based on the supplied files from `src/pynxtools_em/parsers/` in [FAIRmat-NFDI/pynxtools-em](https://github.com/FAIRmat-NFDI/pynxtools-em/tree/develop/src/pynxtools_em/parsers). Line numbers refer to the develop branch on 14th October and may shift as `develop` changes.

- `image_png_protochips.py` — `ProtochipsPngSetParser` (466 lines).
- `image_tiff.py` — generic `TiffParser` base/helper (95 lines).
- `image_tiff_fei_legacy.py` — `FeiLegacyTiffParser` (370 lines).
- `image_tiff_hitachi.py` — `HitachiTiffParser` (271 lines).
- `image_tiff_jeol.py` — `JeolTiffParser` (401 lines).
- `image_tiff_point_electronic.py` — `PointElectronicTiffParser` (235 lines).
- `image_tiff_tescan.py` — `TescanTiffParser` (288 lines).
- `image_tiff_tfs.py` — `TfsTiffParser` (323 lines).
- `image_tiff_zeiss.py` — `ZeissTiffParser` (289 lines).

## At a glance

| | |
|---|---|
| **Input family** | Vendor-specific TIFF images, a Protochips ZIP containing PNG frames, and associated sidecar metadata where supported |
| **Why vendor parsers exist** | TIFF is a generic container; microscope vendors store metadata in different TIFF tags, XMP/XML blocks, or sidecar text files |
| **Image library** | Pillow (`PIL.Image`, `ImageSequence`) for image data and TIFF tags; NumPy for array conversion |
| **Metadata representation** | Usually a flattened `flatdict.FlatDict`, with values parsed to numbers or `pint` quantities where possible |
| **Output** | Mutates and returns a NeXus template; image pixels are written as compressed arrays and axes are generated where implemented |
| **Common template location** | `/ENTRY[entryN]/measurement/eventID[eventN]/imageID[imageN]/image_2d` |
| **Common safeguards** | Magic-byte checks, vendor metadata checks, optional sidecar validation, unsupported Pillow modes skipped with warnings (TIFF parsers only; the Protochips PNG reader has no mode check) |
| **Caution** | A valid TIFF/PNG signature alone does not establish that the file is a supported electron-microscopy export |

## General architecture and behaviour

### 1. Identification is metadata-led, not extension-led

The generic `TiffParser` checks TIFF magic bytes and can read TIFF tags, but its own comments explicitly note that different manufacturers store different metadata and that the extension or magic number alone is not sufficient for vendor identification (`image_tiff.py` l. 41–70; detection l. 41–81). The vendor parsers therefore add checks for their expected metadata conventions.

The TIFF readers commonly look for the little-endian TIFF signature `II*\x00`, then inspect standard or vendor-specific tags and/or an associated text file. Protochips instead expects a ZIP signature and a collection of PNG files with Protochips-specific embedded metadata.

### 2. Metadata collection and normalization

Most vendor parsers collect metadata during construction into a flattened dictionary, then set `supported` if sufficient identifying metadata is found. Metadata may come from:
- standard TIFF tags such as description, make or model;
- vendor-specific TIFF tags;
- XMP metadata;
- embedded XML fragments;
- a `.txt` or `.hdr` sidecar;
- Protochips XML stored inside PNG metadata in a ZIP archive.

Values are converted with `string_to_number()` and/or `pint` quantities when appropriate. Some readers prefer embedded metadata and only consult a sidecar if no metadata was found in the image; this avoids silently merging possibly conflicting sources.

### 3. Pixel arrays and NeXus output

The vendor image parsers' `parse(template)` methods typically calculate a SHA-256 checksum, map metadata to configured NeXus concepts, and write image data. They iterate over TIFF frames with Pillow's `ImageSequence.Iterator`, convert non-grey images to `"L"` where the implementation classifies them as not greyscale, flip arrays vertically with `np.flipud`, and skip exotic/unsupported image modes with a warning (the Protochips PNG reader does none of these; see its section). See the vendor-specific image-data methods cited below.

The common image output contains a signal (`real`), axes metadata and compressed pixel arrays. Coordinate axes are based on pixel indices and, when available, pixel-size metadata. A number of assumptions around orientation and coordinate conventions are documented as TODOs in the source; do not assume every vendor parser has identical calibration behaviour.

## Formula / transformation

The formulas below describe the transformations implemented by the supplied parsers, rather than an idealized microscope coordinate model. The parser may use pixel indices when calibration metadata is missing; in that case the axis is not a physical-length axis.

### Shared TIFF image transformation

- **Frame → NumPy array:** each TIFF frame is converted to a NumPy array. When the image is classified as not greyscale, the code converts it to Pillow mode `L` first; then it applies `np.flipud` to reverse the vertical array order (`image_tiff_fei_legacy.py` l. 205–212; `image_tiff_hitachi.py` l. 178–185; `image_tiff_jeol.py` l. 274–281; `image_tiff_point_electronic.py` l. 148–155; `image_tiff_tescan.py` l. 197–204; `image_tiff_tfs.py` l. 201–208; `image_tiff_zeiss.py` l. 181–188). This is a pixel-order transformation, not a physical rotation with recalibrated metadata.
- **Uncalibrated axes:** when physical pixel size is unavailable, the common fallback is an index-like axis with unit magnitude 1 for `i` and `j`; warnings state that pixel width/height is unitless (`image_tiff_fei_legacy.py` l. 251–254 for the active Tecnai path; `image_tiff_hitachi.py` l. 219–232; `image_tiff_jeol.py` l. 315–345; `image_tiff_point_electronic.py` l. 188–196; `image_tiff_tescan.py` l. 238–250; `image_tiff_tfs.py` l. 248–264; `image_tiff_zeiss.py` l. 222–240).
- **Axis samples:** coordinate arrays are generated with 

  $$
  x_i = \operatorname{linspace}(0,n-1,n), \qquad i=0,\ldots,n-1
  $$

   (`image_tiff_fei_legacy.py` l. 299–304, 318–326; `image_tiff_hitachi.py` l. 236–242; `image_tiff_jeol.py` l. 348–354; `image_tiff_point_electronic.py` l. 198–204; `image_tiff_tescan.py` l. 253–259; `image_tiff_tfs.py` l. 281; `image_tiff_zeiss.py` l. 247). Where pixel size is supplied, these indices are multiplied by or represented with the relevant pixel-size quantity, depending on the parser. See each parser below.

### Parser-specific transformations

#### `image_png_protochips.py`

- **Physical axes:** the scale comes from `MicroscopeControlImageMetadata.ImagerSettings.ImagePhysicalSize.X` and `.Y`, interpreted as nanometres and converted to metres, then multiplied with the index sequence (`image_png_protochips.py` l. 417–431, 443–450). If either key is missing, the parser warns and uses unitless axes (l. 432–435). The source does not state whether `ImagePhysicalSize` is a per-pixel size; verify against Protochips documentation.
- **No flip, no greyscale conversion, no mode filter:** each PNG is read with `np.array(png)` (l. 381–382; the TODO at l. 381 mentions `PILLOW_IMAGE_MODE*`). The TIFF-specific `np.flipud` rule is not applied here.

#### `image_tiff.py`

This is the generic TIFF helper: it checks the TIFF signature and reads tags (`image_tiff.py` l. 41–95), but it does not implement the vendor-specific calibrated pixel-axis formula used by the derived readers. Treat it as a base/helper, not a complete scientific image normalization path.

#### `image_tiff_fei_legacy.py`

- **Pixel-size calibration:** only the Helios branch reads `Metadata.BinaryResult.PixelSize` (`l. 255–282`, axes at l. 316–335), but `parse()` does not process Helios files (`l. 180–196`). On the active Tecnai path no pixel size is used: a warning is logged (`l. 251–254`) and both axes are pixel indices `0…n−1` with long name `… (pixel)` and no `@units` (`l. 301–315`).
- **Frame orientation and axis coordinates:** 

  $$
  A_{\mathrm{out}} = \operatorname{flipud}(A_{\mathrm{frame}})
  $$

   (or `flipud(array(convert_L(frame)))`) (`l. 205–212`); axes are generated from pixel-index sequences (Tecnai `l. 301–315`, Helios `l. 316–335`). Confirm the relationship between the axis direction and the flipped signal before interpreting orientation-sensitive data.

#### `image_tiff_hitachi.py`

- **Pixel size:** a single metadata value `PixelSize` is interpreted as nanometres and converted to metres for both `i` and `j`: 

  $$
  s_i = s_j = \mathrm{PixelSize}_{\mathrm{nm}}\times 10^{-9}\ \mathrm{m}
  $$

   (`l. 222–232`). This assumes square pixels. If the value is missing, the axes are unitless.
- **Frame orientation:** the pixel array is vertically flipped with `np.flipud` (`l. 178–185`); index coordinates are generated from the image dimensions (`l. 236–242`).

#### `image_tiff_jeol.py`

- **Pixel-size calibration (three cases, `l. 314–345`):** (1) if both `SM_MICRON_BAR` (pixel count $N$) and `SM_MICRON_MARKER` (length $L$, converted to metres) exist, $s_i = s_j = L/N$ with square pixels assumed (`l. 318–330`); (2) otherwise, if `CM_PIXEL_SIZE` is a two-element quantity, `i` takes element 1 and `j` element 0, each converted to metres (`l. 331–343`); (3) otherwise a warning and unitless axes (`l. 344–345`).
- **Metadata units:** recognized JEOL keyword values are converted using `JEOL_KEYWORD_TO_PINT_UNITS` (l. 164–211); this is a metadata-unit normalization step separate from the image pixel transform.
- **Frame orientation:** `np.flipud` is applied to each supported frame (`l. 274–281`).

#### `image_tiff_point_electronic.py`

- **Pixel size:** calibration is used only when both `PixelSizeX` and `PixelSizeY` are present; each is interpreted in metres (`l. 188–196`). Thus 

  $$
  x_i = i\,s_x, \qquad y_j = j\,s_y
  $$

  ; if either field is absent, the parser falls back to unitless axes rather than calibrating only one dimension.
- **Frame orientation:** supported frame arrays are vertically flipped (`l. 148–155`), and axis coordinates are generated from pixel indices (`l. 198–204`).

#### `image_tiff_tescan.py`

- **Pixel size:** when both `PixelSizeX` and `PixelSizeY` exist, they are interpreted in metres and used independently for the two axes (`l. 238–250`). In formula form, 

  $$
  x_i = i\,s_x, \qquad y_j = j\,s_y
  $$

  ; if the pair is incomplete, the code warns and uses unitless axes.
- **Frame orientation:** the array is vertically flipped (`l. 197–204`); axis samples use the image dimensions (`l. 253–259`). The optional HDR file contributes metadata but does not by itself guarantee that calibration is present.

#### `image_tiff_tfs.py`

- **Pixel size:** used only when both `EScan/PixelWidth` and `EScan/PixelHeight` exist; each is interpreted in metres, $x_i = i\,s_x$, $y_j = j\,s_y$ (`l. 252–262`). Otherwise a warning and unitless axes; the source comment notes that the chamber CCD overview camera has no calibration.
- **Value typing of byte-scanned metadata:** a string that `isdigit()` becomes `int64`, a float-like string `float64`, anything else stays a string (`l. 167–173`).
- **Frame orientation and axes:** `np.flipud` (`l. 205–207`); index coordinates from the image dimensions (`l. 281`).

#### `image_tiff_zeiss.py`

- **Pixel size:** the first key found among `AP_IMAGE_PIXEL_SIZE` (V08), `APImagePixelSize`, `AP_PIXEL_SIZE` (V06; the source comment says it is off by a factor two in V08) is converted `.to(meter)` for both axes, assuming square pixels (`l. 226–238`); otherwise unitless (`l. 239–240`). The source notes that a version-dependent case distinction is still required (l. 229).
- **Value conversion in metadata:** `On`/`Yes` → `True`, `Off`/`No` → `False`, `<x> °C` → degC quantity, `<x> K X` → $x\cdot 1000$ (magnification) (`l. 138–147`).
- **Frame orientation and axes:** `np.flipud` (`l. 185–187`); index coordinates from the image dimensions (`l. 247`).

### Important interpretation limits

1. **Flip does not automatically update the physical axis direction.** The code's vertical array reversal and its axis construction must be considered together; these parsers do not all demonstrate a fully explicit coordinate-origin transformation.
2. **Units depend on source metadata.** A metre-valued axis is only as reliable as the vendor metadata and its interpretation (for example, Hitachi's assumption that `PixelSize` is in nm).
3. **Missing calibration is not zero calibration.** Unitless index axes are a fallback, not a claim that the image has a physical pixel size of one metre.
4. **Intensity transforms are limited.** In the cited branches, the main image operation is array conversion and vertical flipping, with optional conversion to greyscale. No general intensity rescaling formula is applied in these paths.

## Standard behaviour (typical vendor TIFF path)

1. **Initialize.** Store the input path(s), entry ID, event ID, metadata container and supported flag.
2. **Validate container.** Check the TIFF signature before interpreting vendor tags.
3. **Extract metadata.** Read tags, XMP/XML payloads or sidecar files; flatten nested structures and convert values when possible.
4. **Decide support.** Set `supported` after identifying metadata has been collected. The exact predicate differs by parser.
5. **Parse.** Compute SHA-256 where implemented; write metadata through configured mapping functions.
6. **Decode pixels.** Iterate through image frames, convert supported modes to NumPy arrays, vertically flip the array and write the image signal.
7. **Axes.** Write axis indices and coordinate arrays; apply pixel size when the parser has the relevant metadata.

This is a family-level description. FEI, Hitachi, JEOL, Point Electronic, TESCAN, ThermoFisher (TFS) and Zeiss differ in both their support criteria and their metadata precedence rules.

## Special behaviour

### `image_tiff.py` — generic TIFF base/helper

**Class and methods:** `TiffParser` (l. 29–95); initialization (l. 32–39), signature check (l. 41–81), tag reading (l. 83–95).

- Checks the first four bytes for `II*\x00` and sets `supported` if the signature matches (l. 41–81).
- `get_tags()` uses Pillow's TIFF tag mapping to expose tag values in a dictionary (l. 83–95).
- The class comments explain why TIFF magic is only a container check: vendors may encode different content in TIFF, and manually exported images can lose acquisition context (l. 44–70).
- Treat this as a common helper / starting point, not as a complete vendor-neutral metadata normalizer.

### `image_png_protochips.py` — Protochips heating-chip PNG set in a ZIP

**Class and entry points:** `ProtochipsPngSetParser` (l. 61–466); ZIP/PNG support check (l. 86–167), XML metadata extraction (l. 169–250), parse (l. 257–279).

- **Input contract.** Expects a ZIP archive with at least one PNG frame carrying a `MicroscopeControlImage` metadata item. It checks ZIP magic `PK\x03\x04`, PNG magic, the metadata marker, and consistency of frame dimensions; it marks the set supported only after these tests pass (l. 86–167).
- **Metadata.** `get_xml_metadata()` (l. 169–250) reads and flattens XML metadata from the PNG set. The parser retains per-file metadata and event sequence state (l. 61–84).
- **Event handling.** `sort_event_data_em()` (l. 281–308), `process_event_data_em_metadata()` (l. 310–366), and `process_event_data_em_data()` (l. 368–466) sort frame/event information, map metadata and write the image data.
- **Output intent.** This is a set/time-sequence parser rather than a single standalone PNG parser: the archive groups frames and acquisition metadata associated with a Protochips heating-chip experiment.
- **Validation limit.** The code notes a current limitation around polluted ZIPs containing unrelated PNGs; it expects the archive's PNGs to follow the Protochips metadata convention (l. 121–126, 134–163).

### `image_tiff_fei_legacy.py` — FEI / Thermo Fisher legacy TIFF

**Class and entry points:** `FeiLegacyTiffParser` (l. 67–370); detection (l. 94–176), parse (l. 178–196).

- **Input families.** The code distinguishes legacy Tecnai TEM and Helios NanoLab SEM cases with separate support constants (l. 61–64, 94–172).
- **Detection and metadata.** The reader searches the TIFF byte stream for embedded metadata/XML and uses flattened XML plus value conversion (l. 94–176). Tecnai identification is based on the parsed microscope metadata (l. 132–138); the Helios path looks for instrument software/manufacturer/class fields (l. 140–172).
- **Parse stages.** `parse()` delegates to `process_event_data_em_metadata()` (l. 341–370) and `process_event_data_em_data()` (l. 198–339).
- **Legacy caveat.** Helios files are detected (`supported = FEI_LEGACY_HELIOS_SEM`, l. 165) but the XML-block route is marked as switched off (l. 166–172): `parse()` only logs and writes nothing for them, deferring to the `image_tiff_tfs` parser (l. 190–195). The Helios pixel-size branch in the data method (l. 255–282, 316–335) is therefore not reached. Do not infer that every discovered legacy metadata layout is currently accepted.

### `image_tiff_hitachi.py` — Hitachi TIFF plus same-stem TXT

**Class and entry points:** `HitachiTiffParser` (l. 52–271); constructor/input pairing (l. 53–99), detection (l. 101–156), parse (l. 158–169).

- **Input pairing.** The constructor requires exactly two files with the same stem, one TIFF and one `.txt` (l. 53–81). Despite a log message mentioning an optional sidecar, the implemented constructor path requires the pair.
- **Detection.** Checks TIFF magic, then parses the sidecar text and looks for a `[SemImageFile]` or `[TemImageFile]` section. Key/value pairs are converted to quantities when possible; `SerialNumber` is kept as a string to avoid incorrect numeric interpretation (l. 101–156).
- **Parse stages.** `parse()` calls the metadata and image-data processors (l. 158–169); image pixels and mapped metadata are handled at l. 171–271.
- **Practical implication.** A TIFF without the matching `.txt`, or a sidecar without the expected section header, will not pass the parser's intended input checks.

### `image_tiff_jeol.py` — JEOL TIFF and optional TXT sidecar

**Class and entry points:** `JeolTiffParser` (l. 57–401); file selection (l. 58–95), detection/metadata extraction (l. 97–253), parse (l. 255–266).

- **Input selection.** Selects one TIFF and allows one TXT sidecar from the supplied file list (l. 73–90).
- **Metadata priority.** TIFF/XMP and TIFF tags are inspected first. Standard tags 270, 271 and 272 become description/vendor/model metadata; tag 37500 may contain a JEOL-encoded payload (l. 110–163). The payload decoder tries several encodings (l. 54, 137–163), then converts recognized values according to `JEOL_KEYWORD_TO_PINT_UNITS` (l. 164–211).
- **Sidecar fallback.** The `.txt` file is read only when no metadata was found in the TIFF (l. 213–246). The fallback checks `SEM_DATA_VERSION` and `CM_LABEL` for the JEOL signature, though any collected metadata also leads to `supported=True` at l. 248–249.
- **Parse stages.** `parse()` dispatches to metadata and image-data processors (l. 255–266); those processors write the mapped metadata and pixel frames (l. 268–401).

### `image_tiff_point_electronic.py` — Point Electronic DISS TIFF

**Class and entry points:** `PointElectronicTiffParser` (l. 47–235); detection (l. 77–106), metadata flattening (l. 108–127), parse (l. 129–140).

- **Detection.** Requires TIFF magic and XMP metadata with `xmpmeta/xmptk == "XMP Core 5.1.2"`; extracted metadata must be non-empty for `supported=True` (l. 77–106).
- **Metadata flattening.** `get_metadata()` flattens XMP description records and converts string values to numbers where possible, avoiding overwriting duplicate keys (l. 108–127).
- **Image data.** Iterates TIFF frames, handles supported Pillow modes, flips image arrays vertically, and writes compressed `real` data with axis definitions (l. 142–222). Pixel-size axes use `PixelSizeX` and `PixelSizeY` when both are present; otherwise it warns that pixel width/height are unitless (l. 188–219).
- **Parse stages.** `parse()` calculates a file checksum and calls metadata and data processing (l. 129–140).

### `image_tiff_tescan.py` — TESCAN TIFF with optional HDR

**Class and entry points:** `TescanTiffParser` (l. 51–288); input selection (l. 52–98), detection (l. 100–176), parse (l. 178–189).

- **Input selection.** Accepts a single TIFF or a matching-stem TIFF + `.hdr` pair (l. 61–85); the sidecar is optional.
- **Embedded metadata first.** Looks for TESCAN TIFF tag 50431 and parses the payload around `Description` as UTF-8 key/value metadata (l. 114–140).
- **HDR fallback.** If no embedded metadata was obtained and an HDR path is present, parses the sidecar after checking for `[MAIN]` and `[SEM]` headers (l. 141–169). A sidecar is not merged with already-found embedded metadata.
- **Image output.** `parse()` calls metadata and pixel processors (l. 178–189); pixel processing is at l. 191–272 and metadata mapping at l. 274–288.
- **Detection caveat.** The module notes that it has mostly encountered TIMA and “MIRA3 LMH” / “Device” instances so far (l. 100–103), so support should not be generalized to all TESCAN software exports.

### `image_tiff_tfs.py` — ThermoFisher TIFF

**Class and entry points:** `TfsTiffParser` (l. 58–323); detection (l. 86–110), byte-level metadata (l. 112–180), parse (l. 182–192), pixel data (l. 194–301), metadata mapping (l. 303–323).

- **Detection.** After the TIFF magic check, TIFF tag 34682 must be present and non-empty (l. 100–103); `get_metadata()` then fills the metadata and `supported` is set if it is non-empty (l. 105–106).
- **Metadata comes from the raw bytes, not the tag payload.** The file is searched for `[Parent]` markers from `TIFF_TFS_PARENT_CONCEPTS`, parents are sorted by byte offset, and for each parent the child terms from `get_fei_childs(parent)` are located as `term=` between that parent's offset and the next one (l. 112–180). The last parent's end offset is `np.iinfo(np.uint64).max` (TODO, l. 147). The first child term not found in range ends the search for that parent (`break`, l. 180).
- **Mapping.** Seven static/dynamic tables plus the stage table (l. 303–323). `self.versions` is empty and never checked (l. 70). No sidecar.

### `image_tiff_zeiss.py` — Zeiss TIFF

**Class and entry points:** `ZeissTiffParser` (l. 53–289); detection (l. 83–106), metadata parsing (l. 108–160), parse (l. 162–173), pixel data (l. 175–267), metadata mapping (l. 269–289).

- **Detection.** TIFF tag 34118 present → `get_metadata(payload)`; `supported` if metadata is non-empty (l. 97–102).
- **Metadata parsing.** The payload is split on `\r`; lines are skipped until one starts with `ZEISS_CONCEPT_PREFIXES` (l. 111–115). Each concept line (matching `^\w{2}_`) is paired with the following line `key = value`; `Time :` and `Date :` lines are kept as strings, other values are converted as listed in the formula section (l. 116–160).
- **Versions.** Three Zeiss software versions are listed (l. 66–68) but never compared with the file.

## Cross-parser comparison

| Parser | Required / identifying source | Sidecar policy | Main distinction |
|---|---|---|---|
| `image_tiff.py` | TIFF magic bytes | None | Generic signature/tag helper |
| `image_png_protochips.py` | ZIP + PNG frames + `MicroscopeControlImage` metadata and matching dimensions | Archive embeds frame metadata | Event/time sequence of heating-chip frames |
| `image_tiff_fei_legacy.py` | FEI legacy embedded metadata / XML patterns | Embedded content | Distinguishes Tecnai and legacy Helios patterns |
| `image_tiff_hitachi.py` | TIFF + same-stem TXT with `[SemImageFile]` or `[TemImageFile]` | **Required by current constructor** | Sidecar-centred metadata |
| `image_tiff_jeol.py` | TIFF tags / JEOL tag 37500, or sidecar signature | Optional; fallback only if TIFF yielded no metadata | Tries multiple encodings for vendor payload |
| `image_tiff_point_electronic.py` | XMP toolkit signature `XMP Core 5.1.2` | None | Pixel-size axes from `PixelSizeX/Y` if available |
| `image_tiff_tescan.py` | TESCAN tag 50431 or valid HDR metadata | Optional; fallback only if embedded metadata empty | TESCAN custom tag and `.hdr` parser |
| `image_tiff_tfs.py` | TIFF tag 34682 plus byte-scanned `[Section]`/`term=` metadata | None | Metadata scanned from raw bytes; `EScan/PixelWidth` and `EScan/PixelHeight` |
| `image_tiff_zeiss.py` | TIFF tag 34118 with Zeiss concept/value line pairs | None | Line-pair text payload; V06/V08 pixel-size keys |

## Behaviour to investigate / maintenance checklist

- **TIFF byte order.** The vendor readers shown check `II*\x00` (little-endian TIFF); confirm whether big-endian TIFF exports should be supported.
- **Support predicate strength.** Some implementations set `supported=True` whenever metadata is non-empty after parsing. Verify that unrelated TIFF metadata cannot accidentally identify a file as vendor-specific.
- **Sidecar pairing.** Hitachi currently requires a two-file same-stem pair, while JEOL and TESCAN allow optional sidecars. Ensure parser dispatch passes the expected file list.
- **Conflicting metadata.** JEOL and TESCAN prefer embedded metadata and consult the sidecar only if no metadata was found; they do not merge partial fields from both sources.
- **Image orientation.** `np.flipud()` is applied in the vendor pixel-processing methods. Validate the convention against representative files and the intended NeXus coordinate system.
- **Color and exotic modes.** Unsupported Pillow modes are skipped, and some other modes are converted to greyscale. Confirm whether this loses scientifically relevant color channels for any supported instrument.
- **Pixel calibration.** Point Electronic uses `PixelSizeX/Y` only when both are present; other readers may rely on vendor-specific metadata mappings. Confirm units and axis conventions.
- **Frame semantics.** A multipage TIFF creates multiple image IDs, while Protochips uses a ZIP as an event/frame collection. Check that event/image identifiers and timestamps remain aligned.
- **Legacy support.** FEI legacy code includes a disabled Helios XML-block route; test representative older datasets before describing that route as supported.
- **Generic helper scope.** Do not use the TIFF signature helper as a substitute for vendor-specific identification.
- **Defects found in the sources:**
  - TESCAN (`image_tiff_tescan.py` l. 123–131): after a `UnicodeDecodeError` with an `.hdr` present, `txt` is unbound at `txt.split()`. l. 131 splits on whitespace instead of lines, while the HDR path (l. 152) splits on `"\n"`. The axis dict at l. 261 has no `chunks`.
  - Hitachi (`image_tiff_hitachi.py` l. 124): `txt[idx]` is evaluated before the bound test, so an empty sidecar raises `IndexError`; l. 128 is always true. l. 222–228 take `.magnitude` as nanometres whatever unit the file states.
  - Zeiss (`image_tiff_zeiss.py` l. 115): no bound check, so a payload without a concept line raises `IndexError`.
  - All TIFF readers (`image_tiff.py` l. 74, same pattern elsewhere): `mmap` of an empty file raises `ValueError`, which is not caught.
  - `self.versions` is defined in the TFS, Zeiss, Hitachi, Point Electronic and TESCAN parsers but never used.
  - JEOL (`image_tiff_jeol.py` l. 150–154): if no codec decodes the payload, `decoded` is `None` and `decoded.split` raises `AttributeError`.
