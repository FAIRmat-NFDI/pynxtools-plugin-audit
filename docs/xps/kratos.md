# Kratos parser

Source folder: `pynxtools_xps/parsers/kratos/` (`parser.py`, `metadata.py`, `data_model.py`). Line numbers refer to `parser.py` unless a file is named.

This parser has **no energy formula**. The only processing is turning comment lines into typed metadata fields. It is used through VAMAS comments, not as a standalone file parser.

## At a glance

| | |
|---|---|
| **Input format** | Kratos files in VAMAS ISO 14976 format (`.vms`). The Kratos-specific metadata is read from the VAMAS comment lines. |
| **URL (source code)** | [kratos](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/kratos/) |
| **Documentation** | [Data from Kratos instruments](https://fairmat-nfdi.github.io/pynxtools-xps/reference/kratos.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/kratos/metadata.py) |

**Standard behaviour.** Metadata-only parser. It reads Kratos header comment lines (`key : value`) passed in from the VAMAS comment handler, normalises keys (`start`→`energy_start`, `end`→`energy_end`, `centre`→`energy_centre`, `width`→`energy_width`, `tilt`→`sample_tilt`, `lens`→`lens_mode`), converts values to the dataclass field types (dates, description and deflection tuples, booleans), sets eV units for energy fields and flattens the result (`_units` → `/@units`). No spectrum data or energy axis is built.

**Special behaviour.**

- `_parse` is a stub (`pass`) and `matches_file` always returns `True` (`parser.py` l. 52, 78); the parser is used only through `vms/comment_handler.py`.
- Lines without exactly one `" : "` and unknown keys are skipped silently. The energy axis, binding/kinetic type, excitation and pass energy come from the VAMAS parser, not from here.

## Formula / transformation

**Step 1: split each header line (`parse_header_into_metadata`, l. 93-98)**

```
key, raw_value = line.split(" : ")
```

A line without exactly one `" : "` raises `ValueError`, which is caught, and the line is skipped (`continue`, l. 97-98). A value that itself contains `" : "` gives three parts and is also silently dropped.

**Step 2: normalise the key (l. 100; `metadata.py` l. 78-88)**

```
key = _context.normalize_key(key)
start -> energy_start;  end -> energy_end;  centre -> energy_centre;  width -> energy_width
tilt -> sample_tilt;  lens -> lens_mode;  anode_library -> anode_material;  x-ray_power -> x_ray_power;  location_i_d -> location_id
```

The body of `normalize_key` was not inspected. From keys like `x-ray_power` it appears to lowercase and replace spaces with underscores before applying `_KEY_MAP`.

**Step 3: keep only known fields (l. 90-91, 102)**

```
datacls_fields = dataclass field names without "_units"
if key in datacls_fields: ...      (otherwise the line is ignored)
```

Energy-related fields in `data_model.py` (l. 55-65): `energy_start`, `energy_end`, `energy_centre`, `energy_width`, `step_size` (eV) and `number_steps` (int).

**Step 4: convert and store (l. 103-110)**

```
field_type = type(getattr(self.metadata, key))          (type taken from the field's default)
key, value, unit = _context.format(key, raw_value)
setattr(self.metadata, key, field_type(value))
if unit:  setattr(self.metadata, f"{key}_units", unit)
```

- An energy field defaults to `0.0`, so the value is converted with `float(...)`. `number_steps` defaults to `0`, so `int(...)` is used.
- Units come from the data-model defaults (`"eV"`) unless `format` returns a unit. `_UNIT_MAP` is empty (`metadata.py` l. 100) and `_DEFAULT_UNITS` only sets `sample_tilt` to degree and `resolution` to eV (`metadata.py` l. 102-105).
- `validate_types()` runs at the end (l. 112).

**Step 5: value converters (`metadata.py` l. 39-98)**

```
date_created:       parse_datetime with "%d.%m.%Y %H:%M" or "%d/%m/%Y %H:%M"     (l. 32, 91-94)
description:        "(x, y, z) unit" -> {x, y, z (strings), x_units, y_units, z_units}   (l. 34-55)
deflection:         "(x, y) unit"    -> {x, y (floats), x_units, y_units}                (l. 61-75)
charge_neutraliser: _convert_bool
```

Example (my own numbers, from the docstring format at l. 59): `"(0.000, 0.000)mm"` gives `{"x": 0.0, "y": 0.0, "x_units": "mm", "y_units": "mm"}`.

**Step 6: flatten for output (`flatten_metadata`, l. 114-151)**

```
dict-valued fields:   flattened["{key}_{sub_key}"] = sub_value
other fields:         flattened[key] = value
keys containing "_units":  "{name}_units" -> "{name}/@units"
```

Example (my own numbers): `energy_start = 1200.0` and `energy_start_units = "eV"` become `energy_start` and `energy_start/@units`.

## Special behaviour

1. **`_parse` is a stub (l. 54-78).** It consists of `pass` and TODO comments, so nothing is read from a file and `self.data` is never filled, although the docstring says it is.
2. **`matches_file` always returns `True` (l. 48-52).** There is a TODO; the vendor and extension attributes are commented out (l. 36-39).
3. **Only used through VAMAS comments.** `vms/comment_handler.py` l. 173-178 creates `KratosParser()`, calls `parse_header_into_metadata(comment_list)` and returns `flatten_metadata()`. The Kratos block is recognised by `'Quality'` or `'X-ray Power'` (`comment_handler.py` l. 96).
4. **Silent filtering (l. 94-102).** Lines that don't split cleanly and keys that aren't dataclass fields are ignored without any message.
5. **Energy axis and type come from elsewhere.** The axis, binding/kinetic type, excitation energy and pass energy come from the VAMAS parser, so axis issues belong to the [VAMAS analysis](vms.md).

## Behaviour to investigate

- **`matches_file` always `True` (l. 52):** if this class is ever registered or discovered, it would claim every file. Check the parser registry.
- **`_parse` does nothing (l. 78):** check what the base class does with empty data and no error.
- **Conversion errors aren't caught (l. 105-107):** only the split is inside the `try` (l. 94-98). A `ValueError` from a malformed description or deflection, a bad date or an invalid number (e.g. `int("301.0")` for `number_steps`) ends parsing of the whole comment block. Check whether the VAMAS handler catches it.
- **Values containing `" : "` are lost (l. 95-98):** the line is skipped with no warning.
- **`step_size` and `number_steps` mapping:** they match only if the normalised file key equals the field name exactly. Print the metadata for a real file to confirm they are filled.
- **Types follow the defaults (l. 103, 107):** a field defaulting to `0.0` is always `float`, so a text value for it raises an error.
- **Description values are strings, deflection values are floats (`metadata.py` l. 47-52 vs 69-72):** inconsistent types for similar data.
- **Regex limits (`metadata.py` l. 34-36, 62):** no exponent form (`1e-3`) or trailing-dot numbers (`5.`), and `.match` ignores any text after the unit.
- **Energy units are never converted:** the unit string is stored as given, so a value in keV would be labelled keV and not rescaled. The body of `_context.format` was not inspected.
- **No cross-check with the VAMAS axis:** nothing compares `energy_start`, `energy_end`, `step_size` and `number_steps` with the VAMAS axis (`abscissa_start`, `abscissa_step`, `num`). One would expect `centre = (start + end)/2` and `width = |end − start|` (assumption).
- **Defaults of `0.0` look like real values (`data_model.py` l. 55-65):** a missing field can't be told apart from a real 0 eV.

## Scanner findings

- **Medium:** empty `_parse` (`parser.py` l. 54).
- **Low/info:** silent `except ValueError` (l. 97), 6 TODO/FIXME markers, 1 hit for keys spelled differently.
