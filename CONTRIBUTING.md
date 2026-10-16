# Contributing

Thanks for helping. This repo records what each pynxtools reader or parser actually does with the data, based on evidence from the code. Corrections, extra evidence, new parsers, and confirming or refuting open items are all welcome.

## Rules

1. **Pin the version.** Say which plugin, branch and commit you read. Line numbers only apply to that version.
2. **Cite evidence.** Point to a file and lines (`rod.py l. 322–329`), a test, or upstream docs.
3. **Separate fact from inference.** Write what the code does as fact. Mark everything else as "inferred" or "not read".
4. **Say what you ran.** State whether a finding comes from reading the code, the scanner, or running the parser. Don't call something confirmed if you didn't run it.
5. **No private data.** Use small synthetic files, not real measurements you can't share.

## Adding or editing a parser document

Copy a similar document from `docs/` (`docs/spm/bruker_txt.md`, or `docs/mpes/mpes-reader.md` for reader-only plugins) and keep its sections:

1. Source files reviewed (with the commit and line-number note)
2. At a glance
3. Formula / transformation
4. Standard behaviour
5. Special behaviour
6. Behaviour to investigate
7. Scanner findings (or "No scanner run was performed")

Give each item under *Behaviour to investigate* a status: `open`, `confirmed`, `refuted` or `reported upstream` (with a link). Don't delete resolved items, change their status.

If you add or rename a document, update the Contents and "Parsers at a glance" tables in that plugin's `README.md`, and the plugin table in the main README.

## Scanner

`audit_scan.py` is a review aid, not proof of a bug. Run it from the plugin root:

```bash
python /path/to/audit_scan.py --min-severity low
```

Save results as `results/audit_<plugin>.csv` and review them before committing.

## Reporting a bug upstream

Open an issue in the plugin's repository with the file, lines, what happens, and a minimal example. Then link the issue from the item here and set it to `reported upstream`.

## Pull requests

Keep each pull request to one plugin or topic, and say which commit you checked. Before opening it, check that line numbers match, claims are marked as fact or inferred, and links and tables are consistent.

## License

Not decided yet. By contributing you agree to the license the maintainer chooses.
