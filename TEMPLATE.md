# <Format name> parser (`pynxtools-<plugin>`)

<!--
Copy this file to docs/<plugin>/<parser>.md and fill it in.
Delete the comments and any section that does not apply, but keep the order.
For a plugin that is one reader with no separate parsers, see docs/mpes/mpes-reader.md.
-->

## Source files reviewed

- `src/<package>/parsers/<file>.py` — `<ClassName>` and helper functions (<N> lines).
- Inherited, **not read**: `<BaseClass>` (`<path>`). Its behaviour below is inferred from how `<file>.py` uses it.
- Companion mapping, **not read**: `<config>.json`.
- External libraries: `<library>`.
- Project: [<plugin> repository](<url>).

**Line-number note:** References below refer to branch `<branch>`, commit `<hash>` (<date>). `<abbr> l.` = `<file>.py`.

## At a glance

| | |
|---|---|
| **Input format** | <file type, extension, vendor / instrument> |
| **Parser class** | `<ClassName>` (<abbr> l. <from>–<to>) |
| **Reader** | <library or own code> (<abbr> l. <n>) |
| **Raw-data storage** | <attributes or variables that hold the data> |
| **Output from parser** | <keys, types, units> |
| **Config** | `<config>.json` |
| **Target definition** | `<NXdefinition>` |
| **Project context** | <what is special about this parser> |

**Standard behaviour.** <Two or three sentences: detection, reading, mapping.>

**Comparison with `<sibling parser>`.** <One or two sentences.>

## Formula / transformation

### <Name of the calculation>

**Location:** `<function>()` (<abbr> l. <from>–<to>).

$$
<formula>
$$

<Units, assumptions, and a worked example if the formula is easy to misread.>

<!-- Repeat for each calculation: axes, offsets, scaling, unit conversion, reshaping, defaults. -->

## Standard behaviour

1. **<Step>.** <What happens> (<abbr> l. <n>).
2. **<Step>.** <What happens> (<abbr> l. <n>).

## Special behaviour

1. **<Quirk or fallback>.** <What the code does on purpose> (<abbr> l. <n>).

## Behaviour to investigate

Status: `open`, `confirmed`, `refuted`, or `reported upstream` (add the link).

1. `open` **<Short title>.** <What happens, with lines, and the input that triggers it> (<abbr> l. <n>).
2. `open` **<Short title>.** <...>

## Scanner findings

<Findings from `audit_scan.py` for this file, or:>

No scanner run was performed for `<plugin>`.
