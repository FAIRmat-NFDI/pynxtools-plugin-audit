# pynxtools-mpes `reader.py`: MPES HDF5 reader and NeXus mapper

## Source files reviewed

- `src/pynxtools_mpes/reader.py` — `MPESReader` and all HDF5/xarray/ELN helper functions (248 lines).
- Inherited: `pynxtools.dataconverter.readers.multi.reader.MultiFormatReader`, which owns the JSON-config walk and template population.
- Inherited: `pynxtools.dataconverter.readers.utils.parse_yml`, used to load the ELN YAML file.
- Project docs: [pynxtools-mpes documentation](https://fairmat-nfdi.github.io/pynxtools-mpes/) and [Use the MultiFormatReader](https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html).

Line-number note: references below refer to the `develop` branch source supplied in the conversation. `reader l.` means `reader.py`.

## At a glance

| Aspect | Value |
|---|---|
| Input format | A normalized MPES HDF5 file containing `/binned/BinnedData`, `/axes/*`, and optionally `/metadata/*` |
| Optional metadata input | YAML ELN file, loaded with `parse_yml(..., parent_key="/ENTRY")` |
| Mapping input | JSON config file, interpreted by the inherited `MultiFormatReader` |
| Parser class | No separate parser class; parsing is embedded in `h5_to_xarray()` and `recursive_parse_metadata()` |
| Reader class | `MPESReader(MultiFormatReader)` (`reader l.` 159–245) |
| Raw-data storage | `self.data_xarray`, an `xarray.DataArray` containing values, dimensions, coordinates, units, and metadata (`reader l.` 58–131) |
| Output from parser | No standalone output dictionary; the xarray and ELN dictionary are queried later through `get_data()`, `get_attr()`, and `get_eln_data()` |
| Target definitions | `NXmpes` and `NXmpes_arpes` (`reader l.` 162) |
| Plugin entry point | `READER = MPESReader` (`reader l.` 248) |
| Project context | [pynxtools-mpes repository](https://github.com/FAIRmat-NFDI/pynxtools-mpes/tree/develop); a pynxtools plugin for multidimensional photoelectron spectroscopy |

**Standard behaviour.** The reader expects the MPES data to have already been binned and written into a specific HDF5 layout. It reads `/binned/BinnedData` as the signal, `/axes/axN` datasets as coordinates, and `/metadata` as nested metadata. It converts these into one `xarray.DataArray`, then exposes three lookup callbacks—data, attributes, and ELN—that a JSON mapping file uses to populate the NeXus template (`reader l.` 58–131, 225–245).

**Comparison with parser-based pynxtools plugins.** This repository does not contain separate parsers for vendor formats such as SPE, SES, or EMD. Instead, upstream processing is expected to produce the normalized HDF5 structure; `reader.py` is an adapter from that structure to NeXus. The JSON config supplies the field-by-field mapping, while `MultiFormatReader` performs the actual conversion.

## Formula / transformation

### Reader: HDF5 to xarray

Location: `h5_to_xarray()` (`reader l.` 58–131).

```text
signal = /binned/BinnedData
coords = /axes/ax0, /axes/ax1, ...
dims   = /axes/axN.attrs["name"]
```

The reader constructs:

```python
xr.DataArray(
    data,
    dims=bin_names,
    coords={
        name_0: axis_values_0,
        name_1: axis_values_1,
        ...
    },
)
```

For example, if `BinnedData` has shape `(500, 256)` and the axes are named `energy` and `angle`, the result is an array with:

```python
dims=["energy", "angle"]
coords={"energy": energy_values, "angle": angle_values}
```

### Reader: recursive metadata conversion

Location: `recursive_parse_metadata()` (`reader l.` 29–55).

```text
/metadata/file/analyzer/work_function = 4.5
```

becomes:

```python
{
    "file": {
        "analyzer": {
            "work_function": 4.5
        }
    }
}
```

HDF5 groups become dictionaries. Scalar datasets become Python scalars through `entry.item()`; byte strings are decoded with `.decode()`. Non-scalar datasets remain NumPy arrays (`reader l.` 41–53).

### Reader: voltage-key normalization

Location: `reader l.` 98–104.

```text
<name>VSet  ->  <name>V
```

For every key in `/metadata/file` containing `VSet`, the reader removes the final three characters, copies the value to the shortened key, and deletes the original key:

```python
"LensVSet" -> "LensV"
```

No unit conversion is performed; only the key name changes.

### Reader: data lookup

Location: `rgetattr()` (`reader l.` 146–156) and `get_data()` (`reader l.` 225–239).

For a normal dotted path:

```text
@data:energy.values
```

the reader evaluates:

```python
self.data_xarray.energy.values
```

For an index request:

```text
@data:energy.index
```

it returns:

```python
self.data_xarray.dims.index("energy")
```

For `dims = ["energy", "angle"]`, this returns `0`.

### Reader: metadata lookup

Location: `iterate_dictionary()` (`reader l.` 134–143) and `get_attr()` (`reader l.` 244–245).

```text
@attrs:metadata/file/analyzer/work_function
```

is resolved as:

```python
self.data_xarray.attrs["metadata"]["file"]["analyzer"]["work_function"]
```

The slash-separated path is split recursively. A missing intermediate key returns `None`.

## Standard behaviour

### Plugin registration

At the end of the file:

```python
READER = MPESReader
```

(`reader l.` 248.)

This is the entry point discovered by `pynxtools`. The class declares:

```python
supported_nxdls = ["NXmpes", "NXmpes_arpes"]
```

(`reader l.` 162), so the converter knows which NeXus application definitions the reader can populate.

### Input dispatch

Location: `MPESReader.__init__()` (`reader l.` 165–175).

```python
self.extensions = {
    ".yml": self.handle_eln_file,
    ".yaml": self.handle_eln_file,
    ".json": self.set_config_file,
    ".h5": self.handle_hdf5_file,
    ".hdf5": self.handle_hdf5_file,
}
```

| Input extension | Handler | Stored as |
|---|---|---|
| `.h5`, `.hdf5` | `handle_hdf5_file()` | `self.data_xarray` |
| `.yml`, `.yaml` | `handle_eln_file()` | `self.eln_data` |
| `.json` | `set_config_file()` | `self.config_file` |

The handlers return `{}` because they stage inputs; they do not directly write NeXus fields.

### HDF5 handling

Location: `handle_hdf5_file()` (`reader l.` 177–181).

```python
self.data_xarray = h5_to_xarray(file_path)
```

The resulting xarray contains:

- `.values`: the binned measurement array
- `.dims`: axis names
- `.coords`: axis values
- `.attrs["metadata"]`: nested HDF5 metadata
- `.attrs["units"]` and `.attrs["long_name"]`: signal description

### Signal extraction

Location: `reader l.` 72–78.

```python
data = np.asarray(h5_file["binned"]["BinnedData"])
```

The reader requires `/binned/BinnedData`. If it is absent, it raises:

```python
ValueError("Wrong Data Format, the BinnedData was not found.")
```

### Axis extraction

Location: `reader l.` 80–91.

```python
for axis in h5_file["axes"]:
    bin_axes.append(h5_file["axes"][axis])
    bin_names.append(h5_file["axes"][axis].attrs["name"])
```

Each axis dataset is expected to have:

- `attrs["name"]`: dimension name
- `attrs["unit"]`: coordinate unit, read later

The expected datasets are `ax0`, `ax1`, etc. If `/axes` or a required attribute is missing, the reader raises:

```python
ValueError("Wrong Data Format, the axes were not found.")
```

### Metadata extraction

Location: `reader l.` 93–96 and `recursive_parse_metadata()` (`reader l.` 29–55).

```python
metadata = recursive_parse_metadata(h5_file["metadata"])
```

If `/metadata` exists, its complete group tree is converted into nested Python dictionaries and attached to the xarray:

```python
xarray.attrs["metadata"] = metadata
```

(`reader l.` 128–129.)

### Coordinate and signal attributes

Location: `reader l.` 106–126.

The reader creates coordinates from the axis names and values:

```python
coords[name] = vals
xarray = xr.DataArray(data, dims=bin_names, coords=coords)
```

It then attaches:

- `unit` to each coordinate from `/axes/axN.attrs["unit"]`
- `units` and `long_name` to the signal from `/binned/BinnedData`

Missing attributes are replaced with empty strings rather than raising an error (`reader l.` 112–126).

### ELN handling

Location: `handle_eln_file()` (`reader l.` 189–195).

```python
self.eln_data = parse_yml(
    file_path,
    parent_key="/ENTRY",
)
```

The YAML ELN file is loaded with an `/ENTRY` prefix. Conceptually, a YAML entry such as:

```yaml
user:
  name: Jane Doe
```

is stored under an `/ENTRY/user/name`-style path.

### JSON config handling

Location: `set_config_file()` (`reader l.` 183–187).

```python
self.config_file = file_path
```

The reader only stores the JSON path. The inherited `MultiFormatReader` later parses the JSON and walks its entries.

### Config-driven callbacks

After staging, `MultiFormatReader` walks the JSON config. For each mapping value, it calls the relevant callback:

| Config value | Callback | Source |
|---|---|---|
| `@data:...` | `get_data()` | `self.data_xarray` |
| `@attrs:...` | `get_attr()` | `self.data_xarray.attrs` |
| `@eln` | `get_eln_data()` | `self.eln_data` |

This callback convention is part of the `MultiFormatReader` design documented by pynxtools.

### Data callback

Location: `get_data()` (`reader l.` 225–239).

```python
value = rgetattr(obj=self.data_xarray, attr=path)
```

Examples:

| JSON mapping value | Returned value |
|---|---|
| `@data:values` | `self.data_xarray.values` |
| `@data:energy` | The `energy` coordinate |
| `@data:energy.values` | The NumPy array of energy values |
| `@data:energy.index` | The integer index of `energy` in `.dims` |

The special case:

```python
if key.rsplit("/", maxsplit=1)[-1] == "@axes":
    return list(value)
```

returns the dimension names as a list when the destination key ends in `@axes`. For example, it may return:

```python
["energy", "angle"]
```

### Metadata callback

Location: `get_attr()` (`reader l.` 244–245).

```python
return iterate_dictionary(self.data_xarray.attrs, path)
```

This retrieves values from the metadata dictionary attached to the xarray. It is the route by which HDF5 instrument metadata reaches NeXus fields.

### ELN callback

Location: `get_eln_data()` (`reader l.` 197–202).

```python
return self.eln_data.get(path)
```

This implementation uses `path`, not `key`. Therefore, the JSON config must provide the full ELN path, for example:

```json
"@eln:/ENTRY/user/name"
```

### Direct xarray input

Location: `handle_objects()` (`reader l.` 204–223).

Besides file paths, the reader accepts an `xarray.DataArray` directly, either alone or as the first element of a tuple. This supports programmatic use and preserves backwards compatibility with older calls that passed a single xarray object.

If no xarray is found, the reader logs an informational message and skips the objects; it does not raise.

## Special behaviour

- The reader does not parse arbitrary MPES vendor files. It requires `/binned/BinnedData`, `/axes`, and, nominally, optionally `/metadata` (`reader l.` 72–96); in practice a file without `/metadata` raises `AttributeError` at `reader l.` 99 (see *Behaviour to investigate*).
- Metadata before or outside `/metadata` is not captured; only the `/metadata` group is recursively converted (`reader l.` 93–96).
- `VSet` keys are renamed only inside `metadata["file"]`; other metadata branches are untouched (`reader l.` 98–104).
- Axis names come from HDF5 attributes, not from the dataset names `ax0`, `ax1`, etc. (`reader l.` 85–87).
- Axis units are read from `/axes/axN.attrs["unit"]`; missing units become empty strings (`reader l.` 112–118).
- The signal’s `units` and `long_name` are read from `/binned/BinnedData`; missing values become empty strings (`reader l.` 119–126).
- `get_data()` catches `ValueError` and `AttributeError`, logging warnings but returning `None` implicitly (`reader l.` 232–239).
- `get_data_dims()` returns all xarray dimensions as strings, regardless of the requested `path` (`reader l.` 241–242).
- The JSON config—not `reader.py`—determines which xarray values, metadata values, and ELN values are written to which NeXus paths.
- `handle_objects()` accepts a bare xarray or a tuple whose first element is an xarray (`reader l.` 204–217).

## Behaviour to investigate

- **Required HDF5 layout.** The reader fails unless `/binned/BinnedData` and `/axes` exist. There is no support for alternative dataset names or layouts.
- **Axis naming assumptions.** The code iterates all entries in `/axes`, but later reads units specifically from `ax{axis}` (`reader l.` 112–118). Nonstandard axis dataset names may cause units to be missed.
- **Missing `/metadata` raises.** `metadata` is set to `None` when the group is absent (`reader l.` 95–97), but the next statement is `if "file" in metadata.keys()` (`reader l.` 99). `None.keys()` raises `AttributeError`, so a file without `/metadata` fails here even though the metadata is documented as optional. The `"metadata" in h5_file` check protects only the assignment, not this line. Not run on a real file; check with one that has no `/metadata`. A guard such as `if metadata and "file" in metadata` would fix it.
- **`VSet` renaming is broad.** Any metadata key containing `VSet` is renamed, not only lens-voltage keys (`reader l.` 101–104).
- **Silent lookup failures.** `get_data()` and `get_attr()` may return `None` after logging a warning. Whether the resulting NeXus field is omitted, written as null, or causes validation problems depends on the converter and JSON config.
- **ELN path convention.** `get_eln_data()` uses `path`, while the method signature also accepts `key`. Config authors must know which value the `MultiFormatReader` passes for `@eln` mappings.
- **No schema validation in the reader.** `reader.py` does not validate whether extracted values match the expected NeXus type, shape, or unit.
- **No raw-event support.** The reader consumes binned data only; raw detector event lists must be binned upstream.
- **Single data array.** Only one xarray is retained in `self.data_xarray`. Multiple HDF5 data files cannot be merged by this reader.
- **JSON config is essential.** Without a suitable JSON mapping, staged xarray and ELN data are not automatically placed into the NeXus template.

## Scanner findings

No scanner run was performed for `pynxtools-mpes`.
