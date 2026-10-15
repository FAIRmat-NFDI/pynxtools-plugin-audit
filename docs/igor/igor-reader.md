# pynxtools-igor `reader.py`: Igor Pro `.ibw` / `.pxp` reader and NeXus mapper

## Source files reviewed

- `src/pynxtools_igor/reader.py` — `IgorReader` and the helper functions `parse_note()`, `axis_from()`, `axis_units_from()`, `iterate_dictionary()` (344 lines).
- External: `igor2.binarywave` (`.ibw`) and `igor2.packed` (`.pxp`).
- Inherited: `pynxtools.dataconverter.readers.multi.reader.MultiFormatReader`, which owns the JSON-config walk, `callbacks.entry_name` and the order in which `handle_*`, `post_process()` and the `get_*` callbacks run.
- Inherited: `pynxtools.dataconverter.readers.utils.parse_yml`, used for the ELN file.
- Project docs: [pynxtools-igor repository (develop)](https://github.com/FAIRmat-NFDI/pynxtools-igor/tree/develop) and [Use the MultiFormatReader](https://fairmat-nfdi.github.io/pynxtools/how-tos/pynxtools/use-multi-format-reader.html).

Line-number note: references below refer to the file in the development branch on 15th October 2026. `reader l.` means `reader.py`.

## At a glance

| Aspect             | Value                                                                                                                              |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Input format       | Igor binary wave `.ibw` (one wave) or Igor packed experiment `.pxp` (many waves in a folder tree)                                  |
| Optional inputs    | ELN YAML (`.yml`/`.yaml`), JSON mapping config (`.json`), entry description YAML (`.entry`)                                        |
| Parser class       | No separate parser class; parsing happens in `process_ibw_files()` and `process_pxp_files()` (`reader l.` 210–332)                 |
| Reader class       | `IgorReader(MultiFormatReader)` (`reader l.` 108–340)                                                                              |
| Raw-data storage   | `self.data` (arrays and units, keyed `<entry>/<name>.<field>`) and `self.attrs` (strings, keyed `<entry>/…`) (`reader l.` 119–120) |
| Output from parser | No standalone output; values are looked up later by `get_data()`, `get_attr()`, `get_data_dims()` and `get_eln_data()`             |
| Target definitions | `["*"]` — any NXDL (`reader l.` 111)                                                                                               |
| Plugin entry point | `READER = IgorReader` (`reader l.` 343)                                                                                            |
| Project context    | pynxtools plugin for FHI-specific Igor data; the only reader in this audit that supports several entries in one conversion         |

**Standard behaviour.** Files are only collected while the extension handlers run (`.ibw`/`.pxp` paths are appended to lists, `reader l.` 334–340). In `post_process()` (`reader l.` 189–208) either all `.ibw` files or exactly one `.pxp` file are loaded; every wave becomes an *entry* whose data, axes, units, wave note and extra metadata are stored in two flat dictionaries. The JSON config then picks values with `@data:` and `@attrs:` paths, evaluated per entry.

## Formula / transformation

### Reader: axis values from the wave header

**Location:** `axis_from()` (`reader l.` 56–71).

$$
x_i = sfA[d]\cdot i + sfB[d],\qquad i = 0,\dots,nDim[d]-1
$$

`sfA` is the Igor scaling step, `sfB` the offset. Example: `sfA=0.5`, `sfB=10`, `nDim=4` → `[10, 10.5, 11, 11.5]`.

### Reader: axis unit from the wave header

**Location:** `axis_units_from()` (`reader l.` 74–91). `dimUnits[d]` is an array of byte fragments; each is decoded as UTF-8 and the pieces are concatenated (`reader l.` 87–89).

### Reader: wave-note parsing

**Location:** `parse_note()` (`reader l.` 33–53).

```text
b"Sample=Au111\rTemp=300"  ->  {"Sample": "Au111", "Temp": "300"}
```

`\r` becomes `\n` (`reader l.` 45); the note is then split on **any whitespace** (`reader l.` 47); a token is kept only if `split("=")` gives exactly two parts (`reader l.` 48–51). Values stay strings.

### Reader: path lookup inside a `.pxp` tree

**Location:** `iterate_dictionary()` (`reader l.` 94–105).

```text
"root/FolderA/wave0"  ->  dic["root"]["FolderA"]["wave0"]
```

The path is split on `/` one level at a time; a key missing as `str` is retried as `bytes` because `igor2.packed.load()` returns byte keys (`reader l.` 97–98). A missing level returns `None`.

### Reader: key construction

All lookups use `f"{entry}/{…}"`. Keys written by the loaders:

| Key | Content | Written at |
|---|---|---|
| `<entry>/<axis>.data` | axis values | `reader l.` 237, 290, 297 |
| `<entry>/<axis>.units` | axis unit | `reader l.` 238, 293, 301, 240, 306 |
| `<entry>/<axis>.index` | dimension number | `reader l.` 244, 310 |
| `<entry>/dims` | list of axis names | `reader l.` 247, 322 |
| `<entry>/data` | wave values | `reader l.` 248, 323 |
| `<entry>/data.units` | data unit | `reader l.` 250, 252, 325, 327 |
| `<entry>/data.errors` | error wave (pxp only) | `reader l.` 319 |
| `<entry>/note/<key>` | parsed wave note (attrs) | `reader l.` 227, 272 |
| `<entry>/<key>` | `metadata:` entries from `.entry` (attrs) | `reader l.` 257, 332 |

## Standard behaviour

### Input dispatch

Location: `IgorReader.__init__()` (`reader l.` 114–130).

| Input extension | Handler | Effect |
|---|---|---|
| `.yml`, `.yaml` | `handle_eln_file()` | `self.eln_data = parse_yml(file_path)` (`reader l.` 132–134) |
| `.json` | `set_config_file()` | `self.config_file` (`reader l.` 143–147) |
| `.ibw` | `handle_ibw_file()` | append to `self.ibw_files` (`reader l.` 334–336) |
| `.pxp` | `handle_pxp_file()` | append to `self.pxp_files` (`reader l.` 338–340) |
| `.entry` | `handle_entry_files()` | YAML → `parse_entry_dict()` (`reader l.` 160–172) |

All handlers return `{}`: they stage inputs and write no NeXus field.

### Entry description (`.entry` YAML)

An entry file maps an entry name to a dict. Keys used by the code:

| Key | Meaning | Used at |
|---|---|---|
| `data` | `.ibw`: file name to match; `.pxp`: path of the data wave (required) | `reader l.` 215, 263–265 |
| `axis<N>_name` | rename dimension N | `reader l.` 233, 279 |
| `axis<N>_units` | override unit of dimension N | `reader l.` 239, 305 |
| `axis<N>` | `.pxp`: path of a wave holding the axis values | `reader l.` 284–295 |
| `data_units` | override data unit | `reader l.` 249, 324 |
| `data_errors` | `.pxp`: path of an error wave | `reader l.` 313–319 |
| `metadata` | dict copied into `attrs` | `reader l.` 255–257, 330–332 |

The same dict can be passed programmatically through `handle_objects()` as a 1-tuple (`reader l.` 149–158). Every entry must itself be a dict (`reader l.` 166–172).

### Post-processing

Location: `post_process()` (`reader l.` 189–208).

```python
if len(ibw) > 0 and len(pxp) > 0 or len(pxp) > 1:   # (ibw>0 and pxp>0) or pxp>1
    raise ValueError(...)
```

- Several `.ibw` files, or exactly one `.pxp`, are accepted. Mixing both, or two `.pxp`, raises `ValueError` (`reader l.` 190–199).
- No input of either type → nothing happens, silently.

### `.ibw` processing

Location: `process_ibw_files()` (`reader l.` 210–257).

1. Find the entry whose `data` equals the file's base name; otherwise create an empty entry named after the file stem (`reader l.` 212–222).
2. `binarywave.load(file)` (`reader l.` 224).
3. Wave note → `attrs["<entry>/note/<key>"]` (`reader l.` 225–227).
4. For each of the 4 header dimensions with `nDim > 0` store the axis (name, values, unit, index) and extend `dims` (`reader l.` 229–245).
5. Store `data`, `data.units` (`reader l.` 247–252).
6. Copy `metadata:` from the entry description (`reader l.` 254–257).

### `.pxp` processing

Location: `process_pxp_files()` (`reader l.` 259–332). Same pattern with these differences: waves are located through `iterate_dictionary()`; an explicit axis wave may replace the header scaling (`reader l.` 283–295); an error wave can be attached (`reader l.` 312–319); missing waves raise `ValueError` (`reader l.` 263–269, 286–289, 315–318). The `data` key is mandatory for every entry (`reader l.` 263–264).

### Config-driven callbacks

| Callback | Source | Location |
|---|---|---|
| `get_data(key, path)` | `self.data[f"{entry_name}/{path}"]` | `reader l.` 174–175 |
| `get_attr(key, path)` | `self.attrs[f"{entry_name}/{path}"]` | `reader l.` 177–178 |
| `get_data_dims(key, path)` | `self.data[f"{entry_name}/dims"]` | `reader l.` 186–187 |
| `get_eln_data(key, path)` | `self.eln_data.get(path)` | `reader l.` 136–141 |
| `get_entry_names()` | keys of `self.entries`, or `["entry"]` | `reader l.` 180–184 |

`self.callbacks.entry_name` is set by `MultiFormatReader` (not supplied). All callbacks return `None` for unknown keys.

## Special behaviour

- `.ibw` input supports neither axis waves nor error waves; only `.pxp` does (`reader l.` 210–257 vs 283–319).
- Entries are created lazily for `.ibw` files without a matching entry (`reader l.` 220–222), so a conversion works without any `.entry` file.
- Empty dimensions (`nDim == 0`) are skipped (`reader l.` 231, 277); a 1D wave yields one axis.
- `metadata:` values land directly under `<entry>/<key>` and share the namespace of `<entry>/note/<key>` (`reader l.` 227, 257).
- `.index` stores the header dimension number, not the position in `dims` (`reader l.` 244, 310).
- `get_data_dims()` ignores its `key` and `path` arguments (`reader l.` 186–187).
- The ELN is parsed with `parse_yml(file_path)` and no `parent_key`, unlike the MPES reader (`reader l.` 133).
- `supported_nxdls = ["*"]` (`reader l.` 111): no definition-specific check is made.

## Behaviour to investigate

- **Config replacement is announced as a skip.** `set_config_file()` logs "Skipping the new file" but then overwrites `self.config_file` anyway (`reader l.` 144–146).
- **Note parsing splits on whitespace, not lines** (`reader l.` 47). The docstring says newline-separated (`reader l.` 36–37); a value like `Sample=Au 111` is lost, and a value containing `=` is dropped (`reader l.` 49).
- **Note decoding** uses UTF-8 (`reader l.` 45); Igor notes can be Mac Roman or Latin-1 and raise `UnicodeDecodeError`. The same risk applies to units (`reader l.` 89), e.g. `µ` or `°`.
- **Entries without data.** An entry from `.entry` that matches no `.ibw` file is listed by `get_entry_names()` but never loaded (`reader l.` 214–218), so its config lookups return `None`.
- **Name collisions.** `Path(file).name.split(".")[0]` (`reader l.` 221) cuts at the first dot (`my.sample.ibw` → `my`); two files with the same stem overwrite one entry.
- **`get_entry_names()` return type** is `dict_keys` or `list` depending on the branch (`reader l.` 181–184); entries are only populated after `post_process()`, so the call order inside `MultiFormatReader` matters.
- **No shape checks.** An axis wave given for `.pxp` is not compared with the data shape (`reader l.` 290–292), nor an error wave with the data.
- **Unit override precedence.** `axisN_units` overrides both header and axis-wave units (`reader l.` 239–242, 305–308); `data_units` likewise (`reader l.` 249–252).
- **Silent no-op.** With no `.ibw`/`.pxp` input, `post_process()` returns without a message (`reader l.` 189–208).
- **Condition readability.** `A and B or C` (`reader l.` 190–193) is correct as written but relies on precedence.
- **`.entry` replacement.** `parse_entry_dict()` overwrites an entry of the same name from an earlier file without warning (`reader l.` 172).
- **`pxp` truthiness.** `if not data_wave` / `if not axis_wave` (`reader l.` 266, 286) rely on the truthiness of the igor2 record object.
- **Large data.** Arrays are held in `self.data` for all entries at once.

## Scanner findings

No scanner run was performed for `pynxtools-igor`.
