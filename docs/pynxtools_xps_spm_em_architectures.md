# pynxtools Plugin Architectures: XPS, SPM, and EM

`pynxtools-xps`, `pynxtools-spm`, and `pynxtools-em` are all pynxtools reader plugins. They share the same outer contract: a `reader.py` entry point receives input files, fills a NeXus template dictionary, and returns it to pynxtools for serialization as an HDF5/NeXus file.

Their internal architectures differ because each technique has different file formats, metadata models, and NeXus application definitions.

## pynxtools-xps

**Repository:** https://github.com/FAIRmat-NFDI/pynxtools-xps

`pynxtools-xps` uses a **model-and-map architecture**.

```text
vendor/source file
  → parser
  → intermediate XPS domain model
  → central mapping layer
  → NeXus template
  → NXmpes / NXxps file
```

### Main components

- `parsers/`: reads heterogeneous XPS vendor and community formats.
- `models/`: holds intermediate, technique-specific representations of spectra, metadata, and provenance.
- `mapping.py`: maps the parsed model onto NeXus concepts.
- `numerics.py` and `peak_finding.py`: provide XPS-specific numerical processing.
- `reader.py`: orchestrates parsing, mapping, and template construction.

### Key characteristic

The parser does not write directly to NeXus. It first produces a structured internal model; a separate mapping layer then converts that model into `NXmpes` or `NXxps` NeXus content.

This makes the XPS plugin well suited to heterogeneous spectral formats, because format-specific parsing is separated from NeXus serialization.

## pynxtools-spm

**Repository:** https://github.com/FAIRmat-NFDI/pynxtools-spm

`pynxtools-spm` uses a **parser-to-formatter architecture**.

```text
vendor file
  → parser
  → NeXus formatter
  → NeXus template
  → NXstm / NXsts / NXafm file
```

### Main components

- `parsers/`: reads SPM vendor formats, including scanning tunneling microscopy, spectroscopy, and atomic force microscopy data.
- `nxformatters/`: builds technique- and format-specific NeXus structures.
- `configs/`: contains configuration used during parsing and formatting.
- `reader.py`: dispatches input files to the appropriate parser/formatter path.

### Key characteristic

There is no single universal intermediate domain model or central `mapping.py`. Instead, parsers extract format-specific content and hand it to `nxformatters/`, which construct the relevant NeXus output.

This fits SPM because the plugin covers several related but distinct techniques: STM, STS, and AFM each map to different NeXus application definitions.

## pynxtools-em

**Repository:** https://github.com/FAIRmat-NFDI/pynxtools-em

`pynxtools-em` uses a **semantic-concept composition architecture**.

```text
ELN/config/vendor/image files
  → use-case selector
  → ELN/config parsers
  → NXem application-definition scaffolding
  → technology-partner parsers
  → post-processing resolvers
  → NeXus template
  → NXem file
```

### Main components

- `reader.py`: implements `EMReader`, the pynxtools entry point.
- `parsers/`: contains vendor-specific, image-format, RSCIIO-backed, Nion, ELN, and OASIS configuration parsers.
- `concepts/`: defines reusable semantic building blocks for electron microscopy.
- `configurations/`: stores parser- and format-specific configuration.
- `geometries/` and `methods/`: represent EM-specific spatial and experimental-method concepts.
- `utils/`: contains shared helpers for logging, plotting, atom types, file checks, and profiling.

### Processing flow

1. `EMReader.read()` clears the shared NeXus template.
2. `EmUseCaseSelector` classifies the input files into configuration, ELN, custom ELN, and technology-partner data categories.
3. Optional OASIS configuration and ELN parsers write research-data-management metadata into the template.
4. `NxEmAppDef` initializes the `NXem` application-definition structure.
5. Vendor, image, RSCIIO, and Nion parsers add instrument metadata and measurement data.
6. `NxEmDefaultPlotResolver` selects default plots.
7. `NxEmAtomTypesResolver` resolves atom-type information.
8. The completed template is returned to pynxtools for `NXem` HDF5 serialization.

### Sidecar files

A sidecar file is an additional companion file containing metadata for a main data file.

For example, a JEOL measurement may consist of:

```text
micrograph.tif
micrograph.txt
```

Here, `micrograph.tif` contains the image and `micrograph.txt` is the sidecar containing instrument metadata. The JEOL parser first tries to read metadata embedded in the TIFF; only if that fails does it use the text sidecar.

`EMReader` routes parsers based on the number of data files:

- One data file: parsers that require no sidecar.
- One or more data files: parsers that accept an optional sidecar, such as JEOL and Tescan TIFF.
- Exactly two data files: parsers that require a sidecar, such as Hitachi TIFF and MRC.

## Architectural comparison

| Plugin | Internal strategy | Main middle layer | Primary NeXus targets |
|---|---|---|---|
| `pynxtools-xps` | Model-and-map | `models/` plus `mapping.py` | `NXmpes`, `NXxps` |
| `pynxtools-spm` | Parser-to-formatter | `nxformatters/` | `NXstm`, `NXsts`, `NXafm` |
| `pynxtools-em` | Semantic-concept composition | `concepts/`, `configurations/`, `geometries/`, `methods/` | `NXem` |

## Summary

- **XPS** separates parsing from mapping through an explicit intermediate model.
- **SPM** delegates NeXus construction to technique-specific formatters.
- **EM** composes NeXus output from reusable semantic concepts and coordinates multiple metadata and data sources, including optional or required sidecar files.
