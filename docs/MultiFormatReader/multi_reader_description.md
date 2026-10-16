# Line-by-line walkthrough of `multi/reader.py`

Source: `src/pynxtools/dataconverter/readers/multi/reader.py`

## 1. Header and imports

- **Lines 1-5**: SPDX license and copyright comments.
- **Module docstring**: describes the file as the base class for readers that dispatch on file format.
- `ast`: safely parses list-like strings in config values (`literal_eval`).
- `logging`, `os`, `re`: logging, file-extension handling and the prefix regex.
- `Callable`, `Any`, `Union`: type hints (`Union` is unused, since the code uses `X | None` syntax).
- `BaseReader`: the parent class every pynxtools reader must extend.
- `is_boolean`, `is_integer`, `is_number`, `to_bool`: string-to-type checks and conversions.
- `parse_flatten_json`, `parse_yml`: load the config file (JSON, flattened to path keys) and ELN YAML/JSON files.
- `Template`: the dict-like object the converter fills with NeXus paths and values.
- `logger = logging.getLogger("pynxtools")`: the shared package logger.

## 2. `fill_wildcard_data_indices(config_file_dict, key, value, dims)`

This expands a config entry containing `*` into one entry per dimension name. For example, `AXISNAME[*]` with `@data:*.data` becomes entries for `x` and `y`.

- `get_vals_on_same_level(key)` is a generator. It cuts `key` at its last `/` to get the parent group, then yields every config value whose key starts with that parent path. It is used to detect values that already exist in the same group.
- `dim_dict = {}` collects the new entries.
- For each `dim`, `new_key` is `key` with `*` replaced by the dim name.
- `new_val` is built by type. A string gets `*` replaced. A list gets `*` replaced in each element, which assumes all elements are strings. Anything else is kept as is.
- The entry is added only if two things hold: the key is not already explicitly defined in the config, and the value is not already used by a sibling in the same group. The second check stops duplicate entries.
- It returns the new entries. The original `*` entry is not part of the result.

## 3. `ParseJsonCallbacks`

This class bundles the callbacks that resolve the `@`-tokens.

- **Docstring**: documents the four token types: `@attrs` (instrument metadata), `@link`, `@data` (measurement data) and `@eln` (ELN data).
- **Class annotations**: declare `special_key_map`, `entry_name` and `dims`.
- **`__init__`**:
  - It builds `special_key_map`, which maps each token to its callback.
  - If a callback is not provided, the default is used. For `@link` that is `self.link_callback`. For the others it is `self.identity`.
  - `self.dims` defaults to a lambda returning `[]`, meaning no wildcard expansion.
  - `entry_name` defaults to `"entry"`.
- **`link_callback`**: turns `@link:/entry/foo` into `{"link": "/<entry_name>/foo"}`, so links follow the current entry name.
- **`identity`**: returns the value unchanged. With no custom callback, `@attrs:foo` simply resolves to the string `"foo"`.
- **`apply_special_key(precursor, key, value)`**: looks up the callback for the prefix, falls back to `identity`, and calls it as `callback(key, value)`.

## 4. `resolve_special_keys(...)`

This resolves one config entry into `new_entry_dict`.

**Inner `try_convert`**: tries int, then float, then bool, and otherwise returns the string. The order matters because `"1"` should become an int, not a float.

**Inner `parse_config_value`**:

- The regex `(@\w+)(?::(.*))?` captures a prefix such as `@attrs` and an optional path after the colon.
- `re.findall` returns tuples `(prefix, path)`. The path is `""` when there is no colon.
- If nothing matches, it returns `("", value)`, which marks the value as a plain constant.

**Main body**:

1. **Plain values**: if the value is not a string or has no `@`, it is stored as is and the function returns.
2. **Parsing prefixes**:
   - It tries `ast.literal_eval(value.lstrip("!"))`. If that works, the value was a list like `["@attrs:a", "@data:b"]`, which means "try these in order".
   - A single `"@attrs:a"` is not valid Python, so it raises `SyntaxError` or `ValueError`. The code catches that and parses the value as one token.
3. **Resolution loop**:
   - For each `(prefix, path)`: if the prefix is empty, the entry is a literal. It is converted with `try_convert` and the loop stops.
   - Otherwise it calls the callback via `apply_special_key`.
   - The loop stops at the first non-`None` result, which is how fallbacks work.
4. **`!` handling**: a leading `!` marks a required element. If it resolved to `None`, the parent group is computed with `rsplit("/", 1)[0]`, logged, and appended to `optional_groups_to_remove`. The function then returns. The key stays in the dict with value `None`, and `remove_none_values()` cleans it up later.
5. **Unresolved optional values**: if nothing resolved, the key is deleted and an info message is logged unless `suppress_warning` is set.
6. **Post-resolution links**: if a callback returned a string starting with `@link:`, it is converted to `{"link": ...}` by stripping the first 6 characters.

## 5. `fill_from_config(...)`

This drives `resolve_special_keys` across the whole config.

- **`has_missing_main(key)`**: returns True if the key starts with the path of any group scheduled for removal.
- **`dict_sort_key`**: returns `False` for string values starting with `!` and `True` for everything else. Since `False < True`, `!` entries sort first. They are processed first so that groups are marked for removal before their children are processed. Python's sort is stable, so the original order is otherwise kept.
- **Default callbacks**: if no callbacks are given, a default `ParseJsonCallbacks()` is created.
- **Per-entry loop**: for each entry name:
  - It sets `callbacks.entry_name`.
  - It sorts the config.
  - For each key it reads the value and replaces `/ENTRY/` with `/ENTRY[name]/`.
  - It skips the key if its group was removed.
  - **Wildcards**: if the key contains `*`, it gets the dimension names from `callbacks.dims`, expands the entry with `fill_wildcard_data_indices`, resolves every expanded entry into a temporary `dim_data`, merges that into the result, and continues.
  - **Normal keys**: it calls `resolve_special_keys` directly.
- It returns the resolved dict.

> **Things to be aware of:** `optional_groups_to_remove` is created once, outside the entry loop, so removals from one entry carry over to later entries. The prefix match is also a plain `startswith`, so `/ENTRY[e]/a` would also match `/ENTRY[e]/ab`.

## 6. `MultiFormatReader`

### Docstring

It documents the six pipeline steps and the built-in handlers and callbacks. Those are described below, where they are implemented.

### Class attributes

- `supported_nxdls`: whitelist of NXDL application definitions the reader accepts. Subclasses must set it.
- `extensions`: only annotated, so each instance gets its own dict in `__init__`.
- `kwargs`: stores the keyword arguments from `read`.
- `overwrite_keys = True`: controls whether template values may be overwritten.
- `config_file`: path to the JSON config.
- `CONVERT_DICT` and `REPLACE_NESTED`: mappings used by `handle_eln_file`, meant to be overridden at class level.

### `__init__`

- Creates `self.callbacks`, wiring the instance's own `get_attr`, `get_data`, `get_eln_data` and `get_data_dims`. This is why overriding those methods is enough to customize resolution.
- Stores `config_file`, and initializes `config_dict` and `eln_data` as empty dicts.
- Creates an instance-level `extensions` dict. The comment notes this avoids a shared mutable class attribute.
- Sets `processing_order = None`.

### Built-in file handlers

- **`handle_eln_file`**:
  - It takes the first entry name from `get_entry_names()`.
  - It calls `parse_yml` with copies of `CONVERT_DICT` and `REPLACE_NESTED`, and `parent_key=f"/ENTRY[{entry_name}]"`.
  - The result is stored in `self.eln_data`.
  - It returns `{}` because the data is used later through `@eln` tokens, not written to the template directly.
- **`set_config_file`**: stores the config path. If one was already set, it logs a warning and replaces it. It returns `{}`.

### Hook methods (override as needed)

- **`setup_template`**: returns static entries. The docstring spells out the contract: it must not touch the NXDL structure or data read from files.
- **`handle_objects`**: handles in-memory Python objects. It is called before file dispatch.
- **`get_attr`** and **`get_data`**: return `None` by default. `key` is the resolved template path and `path` is the part after the token.
- **`get_eln_data`**: returns nothing if `eln_data` is empty. Otherwise it looks up `path`, falling back to `key` for a bare `@eln`. The `or` also catches an empty string.
- **`get_data_dims`**: returns `[]`, meaning no wildcard expansion unless overridden.
- **`get_entry_names`**: returns `["entry"]`. Override it for multi-entry output.
- **`post_process`**: runs after files are read and the config is parsed. It may modify instance state and may return extra template entries.

### `read(...)`: the pipeline

- **Setup**:
  - `self.kwargs = kwargs` stores the arguments.
  - `config_file` and `overwrite_keys` can be overridden from kwargs.
  - A `Template` is built from the incoming template.
- **Step 1, objects**: if objects were passed, `handle_objects` is called and its result is merged in.
- **Step 2, files**:
  - `get_processing_order` returns `(0, index)` for extensions listed in `processing_order`, and `(1, ext)` for all others. Listed extensions therefore come first, in the listed order, and the rest are sorted alphabetically.
  - For each file, the extension is lowercased and looked up in `self.extensions`.
  - Unsupported extensions and missing files get a warning and are skipped.
  - Otherwise the registered handler is called and its dict is merged into the template.
  - Note that the lookup uses the lowercased extension, but the processing-order check uses the original case.
- **Step 3, static data**: `setup_template()` is merged in.
- **Step 4, config**: if a config file is set, `parse_flatten_json(..., create_link_dict=False)` flattens it into `self.config_dict`.
- **Step 5, post-processing**: `post_process()` is called, and its non-empty result is merged in.
- **Step 6, fill from config**:
  - If `config_dict` is non-empty, `suppress_warning` is popped from kwargs.
  - `fill_from_config` is called with the config, entry names and callbacks, and the result is merged into the template.
- **Finish**: `template.remove_none_values()` strips the `None` entries left over from required-but-missing values. The template is returned.

### `READER = MultiFormatReader`

This is the module-level name the dataconverter's reader discovery looks for.
