# `MultiFormatReader` base reader and config-file filler (`pynxtools`)

## Source files reviewed

- `pynxtools/dataconverter/readers/multi/reader.py` — `fill_wildcard_data_indices()`, `ParseJsonCallbacks`, `resolve_special_keys()`, `fill_from_config()` and the `MultiFormatReader` class (570 lines).
- Inherited: `BaseReader` (`dataconverter/readers/base/reader.py`, 43 lines).
- Helpers: `parse_yml()`, `flatten_and_replace()`, `flatten_json()`, `parse_flatten_json()`, `is_integer()`, `is_number()`, `is_boolean()`, `to_bool()` (`dataconverter/readers/utils.py`, 392 lines); `Template.update()`, `Template.remove_none_values()` (`dataconverter/template.py`).
- Project docs: `docs/learn/pynxtools/multi-format-reader.md`, `docs/how-tos/pynxtools/use-multi-format-reader.md`.

**Line-number note:** References below refer to branch `pynxtools-dev`, commit `2d8d4593` (2nd October 2026), as checked out in `nomad-distro-dev/packages/pynxtools`. `reader l.` = `multi/reader.py`, `utils l.` = `readers/utils.py`, `template l.` = `template.py`.

## At a glance

| | |
|---|---|
| **Input format** | None of its own; any file whose extension a subclass registers in `self.extensions`, plus YAML/JSON ELN files and one JSON config file (reader l. 332–336, 371) |
| **Reader class** | `MultiFormatReader(BaseReader)` (reader l. 307–567); `READER = MultiFormatReader` (l. 570) |
| **Dispatch** | Lower-cased extension → handler `Callable[[str], dict]` from `self.extensions` (reader l. 527–537) |
| **Raw-data storage** | Not defined by the base class; subclasses keep parsed data on `self` (e.g. `self.data`). Base class only holds `self.eln_data` and `self.config_dict` (reader l. 367–368) |
| **Output** | `Template` (reader l. 514, 567): flat dict `/ENTRY[<name>]/…` → value, `…/@units`, or `{"link": …}` |
| **Config language** | Flattened JSON with tokens `@attrs:`, `@data:`, `@eln`, `@link:`, fallback lists `"['@attrs:a', '@eln', 'default']"`, required-child marker `!`, wildcard `*` and short notation `*{a,b}` (reader l. 59–304; utils l. 195–277) |
| **Hook methods** | `handle_objects`, `setup_template`, `post_process`, `get_attr`, `get_data`, `get_eln_data`, `get_data_dims`, `get_entry_names` (reader l. 412–496) |
| **Target definition** | Any; restricted by the subclass via `supported_nxdls` (reader l. 348) |
| **Subclasses in this workspace** | `XPSReader`, `XASReader`, `XRDReader`, `RamanReader`, `EllipsometryReader`, `IgorReader`, `JsonMapReader`, `YamlJsonReader` |
| **Project context** | See the [project repository](https://github.com/FAIRmat-NFDI/pynxtools/). The shared base of most plugin readers; behaviour here is inherited by every plugin listed above. |

**Standard behaviour.** `read()` runs a fixed six-step pipeline: in-memory objects, file dispatch by extension, static template entries, config-file parsing, post-processing, and config filling via `@`-token callbacks; `None` values are removed at the end (reader l. 498–567). The config filler resolves each config value through the callback mapped to its prefix, tries fallbacks in order, drops optional groups whose `!`-marked child is missing, and expands `*` wildcards through `get_data_dims()` (reader l. 129–304).

**Comparison with plugin parsers.** The base class does not read any instrument file and performs no unit handling; units come only from the config (`…/@units` keys) or from `parse_yml()`, which renames every `unit` key to `@units` (utils l. 182). Everything instrument-specific lives in the subclass callbacks.

## Formula / transformation

### Config: prefix parsing

**Location:** `parse_config_value()` inside `resolve_special_keys()` (reader l. 159–180).

```python
pattern = r"(@\w+)(?::(.*))?"          # l. 176
prefixes = re.findall(pattern, value)  # l. 177
return prefixes[0] if prefixes else ("", value)   # l. 178–180
```

`"@attrs:metadata/x"` → `("@attrs", "metadata/x")`; `"@eln"` → `("@eln", "")`. The pattern is not anchored: the first `@word` anywhere in the string is taken.

### Config: fallback lists

**Location:** reader l. 187–204.

```python
list_value = ast.literal_eval(value.lstrip("!"))   # l. 191
prefixes = [parse_config_value(v) for v in list_value]   # l. 192
for prefix, path in prefixes:
    if not prefix.startswith("@"):
        new_entry_dict[key] = try_convert(path); break   # l. 197–199
    new_entry_dict[key] = callbacks.apply_special_key(prefix, key, path)   # l. 200
    if new_entry_dict[key] is not None: break   # l. 203–204
```

Candidates are tried left to right; the first non-`None` callback result wins. A non-prefixed candidate is a literal default and ends the search.

### Config: literal type conversion

**Location:** `try_convert()` (reader l. 144–157), only applied to literal fallback candidates.

| Check | Regex / rule | Example | Result | Lines |
|---|---|---|---|---|
| integer | `^[+-]?\d+$` | `"003"` | `3` | reader l. 150–151; utils l. 341 |
| number | `^[+-]?(\d+([.]\d*)?([eE][+-]?\d+)?\|[.]\d+([eE][+-]?\d+)?)$` | `"1e3"` | `1000.0` | reader l. 152–153; utils l. 354–356 |
| boolean | `True\|False\|true\|false\|On\|Off\|Yes\|No` (unanchored `re.search`) | `"Yes"` | `True` | reader l. 154–155; utils l. 369, 381–392 |
| other | — | `"Al Kα"` | unchanged | reader l. 157 |

### Callback dispatch

**Location:** `ParseJsonCallbacks` (reader l. 59–126).

| Token | Default callback | `MultiFormatReader` callback | Lines |
|---|---|---|---|
| `@attrs` | `identity` | `get_attr(key, path)` → `None` | reader l. 99, 361, 438–445 |
| `@data` | `identity` | `get_data(key, path)` → `None` | reader l. 101, 362, 447–454 |
| `@eln` | `identity` | `get_eln_data(key, path)` → `self.eln_data.get(path or key)` | reader l. 102, 363, 456–466 |
| `@link` | `link_callback` → `{"link": value.replace("/entry/", f"/{entry_name}/")}` | not overridden | reader l. 100, 108–112 |
| unknown `@xyz` | `identity` → returns the path unchanged | same | reader l. 126 |

### Wildcard expansion

**Location:** `fill_wildcard_data_indices()` (reader l. 30–56), called from `fill_from_config()` (l. 279–293).

For each `dim` in `callbacks.dims(key, value)` (= `get_data_dims()`):

$$
\texttt{key}_{\text{dim}} = \texttt{key}.\text{replace}(\texttt{"*"}, \text{dim}),\qquad
\texttt{value}_{\text{dim}} = \texttt{value}.\text{replace}(\texttt{"*"}, \text{dim})
$$

(l. 43–49; element-wise for lists). The pair is skipped if `key_dim` is already a config key or `value_dim` already occurs among values with the same parent prefix (l. 51–54).

### Config flattening and short notation

**Location:** `flatten_json()` (utils l. 198–277), called via `parse_flatten_json(..., create_link_dict=False)` (reader l. 544–546; utils l. 293–311). Nested JSON objects become `/`-joined keys (l. 259–261); a key segment `*{a,b}` is expanded into one key per name, and `*` inside the nested keys and values is replaced by that name (utils l. 195, 268–274, 248–249, 263–266).

### ELN flattening

**Location:** `handle_eln_file()` (reader l. 378–394) → `parse_yml()` (utils l. 162–192) → `flatten_and_replace()` (utils l. 124–159).

- Parent key: `/ENTRY[<first entry name>]` (reader l. 387, 392).
- `CONVERT_DICT` renames single key segments (utils l. 139); `unit` → `@units` is forced (utils l. 182).
- `REPLACE_NESTED` does substring replacement on the full path (utils l. 151–152).
- `…/value` keys collapse to their parent (utils l. 154–155).
- Lists of dicts become repeated groups, uniquified with numeric suffixes; `{value, unit}` pairs inside lists become `key` + `key/@units` (utils l. 73–121).

## Standard behaviour

1. **Construction.** `__init__` builds `ParseJsonCallbacks` bound to `get_attr`, `get_data`, `get_eln_data`, `get_data_dims` (reader l. 360–365) and creates per-instance `config_dict`, `eln_data`, `extensions`, `processing_order = None` (l. 366–372). Subclasses fill `self.extensions` after `super().__init__()`.
2. **Read options.** `config_file` and `overwrite_keys` are taken from `kwargs`, else from the instance (reader l. 510–512). The incoming template is copied into a new `Template` (l. 514; deep copy in template l. 23–40).
3. **Objects.** `handle_objects(objects)` runs before any file and its result is merged (reader l. 516–518, 428–436).
4. **File order.** Files are sorted by `get_processing_order()`: extensions in `self.processing_order` first, in that order; all others after, alphabetically by extension (reader l. 521–527). Python's sort is stable, so equal extensions keep their input order.
5. **File dispatch.** Extension is `os.path.splitext(path)[1].lower()` (reader l. 528). Unknown extension → warning, skip (l. 529–533); missing file → warning, skip (l. 534–536); else the handler's return dict is merged into the template (l. 537).
6. **Built-in handlers.** `handle_eln_file` stores the flattened ELN in `self.eln_data` and returns `{}` (reader l. 378–394); `set_config_file` stores the path and warns if one was already set (l. 396–406).
7. **Static data.** `setup_template()` result is merged (reader l. 540, 412–426). By contract it must not read input data or the NXDL template (l. 421–424).
8. **Config parsing.** If `self.config_file` is set, `self.config_dict` is replaced by the flattened JSON (reader l. 543–546).
9. **Post-processing.** `post_process()` may mutate `self.config_dict`/`self.eln_data`/`self.data` and/or return entries; a truthy result is merged (reader l. 549–551, 486–496).
10. **Config fill.** If `self.config_dict` is non-empty, `fill_from_config()` runs with `get_entry_names()` and the callbacks; `suppress_warning` is popped from `kwargs` (reader l. 554–563).
11. **Per entry.** For each entry name: `!`-valued keys are processed first (stable sort, reader l. 250–259, 271); `/ENTRY/` → `/ENTRY[<name>]/` (l. 274); keys under a removed group are skipped (l. 240–248, 276–277); wildcard keys are expanded (l. 279–293); all others go through `resolve_special_keys()` (l. 295–302).
12. **Value resolution.** Non-string values and strings without `@` are copied unchanged (reader l. 183–185). Otherwise prefixes are tried (l. 187–204); a `!` value that resolves to `None` marks the parent group for removal (l. 206–213); a `None` result for any other key deletes it and logs at `INFO` unless suppressed (l. 215–221); a returned string starting with `@link:` becomes a link dict (l. 223–227).
13. **Merging.** `Template.update()` overwrites existing keys when `overwrite_keys` is true; otherwise only keys whose current value is `None` are overwritten, and a warning is logged (template l. 215–241).
14. **Finalise.** `template.remove_none_values()` drops every `None` value in all optionality dicts (reader l. 565; template l. 171–175).

## Special behaviour

1. **Precedence by pipeline order.** With `overwrite_keys = True` (default, reader l. 352) later steps win: config fill (step 6) > `post_process` > `setup_template` > files (last in sort order wins) > objects (reader l. 516–563).
2. **Config file sources.** A `config_file` kwarg overrides the constructor value (reader l. 511); a `.json` file routed to `set_config_file` then overrides the kwarg, with a warning (l. 403–405).
3. **`config_dict` without a config file.** If no config file is set, `self.config_dict` is not reset (reader l. 543), so a dict built in a handler or in `post_process()` is still filled (l. 554).
4. **Links.** The config is flattened with `create_link_dict=False` (reader l. 545) so that `@link:` goes through `link_callback`, which rewrites `/entry/` to the current entry name (l. 108–112).
5. **Bare `@eln`.** Uses the template key itself as the lookup path (reader l. 466), which matches the `/ENTRY[<name>]/…` keys produced by `parse_yml` (l. 392).
6. **Multiple entries.** Every config key is resolved once per name from `get_entry_names()` (reader l. 267–302); the default is `["entry"]` (l. 484).
7. **`!` marker.** Only works on string values (reader l. 257–259); the removed group affects only config keys processed later, not entries already merged from files, `setup_template()` or `post_process()` (l. 276).
8. **Wildcards without dims.** With the default `get_data_dims()` returning `[]` (reader l. 475), a `*` key produces nothing and no message.
9. **Template copy.** A `Template` passed in is deep-copied (template l. 23–29), so the caller's template is not mutated.
10. **Return value of handlers.** All handlers and hooks must return a mapping; `template.update()` iterates `.items()` (template l. 232).

## Behaviour to investigate

1. **Unanchored boolean check.** `is_boolean()` uses `re.search` without anchors (utils l. 369). A literal fallback such as `"['@attrs:x', 'Nominal']"` matches `No`, `to_bool("Nominal")` returns `None` (utils l. 392), and the key is deleted with only an `INFO` message (reader l. 215–221). Also affects `Nothing`, `Yesterday`, `Off-axis`, `Online`. Verified locally.
2. **Unanchored prefix regex.** Any plain config string containing `@` goes through prefix parsing (reader l. 183, 176–177). `"user@example.com"` yields prefix `@example` with empty path; the unknown prefix falls back to `identity` (l. 126) and writes `""`. Verified locally.
3. **Unknown prefixes are silent.** A typo such as `"@atrs:foo"` writes the literal `"foo"` (reader l. 126) instead of failing or warning. Verified locally.
4. **Group removal by string prefix.** `has_missing_main()` uses `key.startswith(optional_group)` without a trailing `/` (reader l. 245–247). Removing `/ENTRY[entry]/src` also drops `/ENTRY[entry]/src_probe/…`. Verified locally.
5. **Wildcard override check.** `fill_wildcard_data_indices()` compares the already-substituted key (`/ENTRY[entry]/…`, reader l. 274) against raw config keys and values that still contain `/ENTRY/` (l. 37–38, 51), so an explicit `AXISNAME[x]` does not suppress the wildcard result. Which value survives depends on JSON key order. Verified locally.
6. **Fallback lists with non-strings.** `ast.literal_eval` can return a list with numbers (reader l. 191); `parse_config_value(5)` then raises `TypeError` in `re.findall` (l. 177), which is not caught (l. 193). `literal_eval` returning a non-list (e.g. a tuple or dict) is iterated as-is.
7. **Multi-entry ELN lookup.** `handle_eln_file()` flattens under the first entry name only (reader l. 387, 392); bare `@eln` for any further entry looks up `/ENTRY[<other>]/…` (l. 466) and misses. `get_entry_names()` is also called during file dispatch, before all data files may have been read.
8. **Extension case and compound extensions.** Dispatch lower-cases the extension (reader l. 528) but `get_processing_order()` does not (l. 522), so `.XML` is sorted as unknown. `splitext` returns only the last suffix, so handlers registered for `.spm.txt` or `.nxs.h5` never match.
9. **Missing-file check order.** The extension is checked before existence (reader l. 529–536); both only warn, and a run with no readable file still returns a template.
10. **`kwargs` mutation.** `kwargs.pop("suppress_warning")` (reader l. 555) also mutates `self.kwargs` (same object, l. 510), and only runs when `config_dict` is non-empty.
11. **Overwrite semantics when disabled.** With `overwrite_keys = False`, a key whose current value is `None` is still overwritten silently (template l. 222, 233); check whether `None` placeholders from earlier steps are intended to be fillable.
12. **Forced `unit` mapping.** `parse_yml()` sets `convert_dict["unit"] = "@units"` (utils l. 182), overriding a subclass `CONVERT_DICT["unit"]` entry.
13. **`REPLACE_NESTED` is substring-based** (utils l. 151–152); a short pattern can rewrite unintended path segments.
14. **Log level.** Unresolved keys and removed groups are logged at `INFO` (reader l. 208, 218); a misspelt config path is easy to miss in a normal run.
15. **Docs drift.** `docs/learn/pynxtools/multi-format-reader.md` shows `Template(overwrite_keys=...)` (docs l. 62), `handle_objects` after `setup_template` (docs l. 112, 131) and `self.post_process()` with its return value discarded (docs l. 179). Current code uses `Template(template=template, ...)` (reader l. 514), runs objects first (l. 516–518) and merges the `post_process()` result (l. 549–551).

## Scanner findings

No scanner run was performed for `pynxtools` / `MultiFormatReader`. The "Verified locally" items were reproduced with direct calls to `fill_from_config()` in the `nomad-distro-dev` virtual environment.
