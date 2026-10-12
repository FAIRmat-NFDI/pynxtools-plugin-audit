# SPECS XML parser

Source: `pynxtools_xps/parsers/specs/xml/parser.py`, in the method whose docstring (about l. 641-644) says it "computes the binding-energy axis and channel-deinterleaved counts" (code l. 655-749). Metadata mappings are in `metadata.py`. Line numbers refer to `parser.py` unless a file is named.

The parser always builds a **binding-energy** axis from `hν − KE` and sums the MCD channels.

## At a glance

| | |
|---|---|
| **Input format** | SpecsLab 2 files from SPECS GmbH (`.xml`). |
| **URL (source code)** | [specs/xml](https://github.com/FAIRmat-NFDI/pynxtools-xps/tree/main/src/pynxtools_xps/parsers/specs/xml/) |
| **Documentation** | [Data from SPECS instruments](https://fairmat-nfdi.github.io/pynxtools-xps/reference/specs.html) |
| **Metadata map** | [metadata.py](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/parsers/specs/xml/metadata.py), [config_specs_xml.json](https://github.com/FAIRmat-NFDI/pynxtools-xps/blob/main/src/pynxtools_xps/config/config_specs_xml.json) |

**Standard behaviour.** Reads the SPECS XML. Per region it collects `excitation_energy`, `kinetic_energy`, `kinetic_energy_base`, `pass_energy`, `scan_delta`, MCD shifts/head/tail and the scan mode. The binding-energy axis is computed, not read. Counts are de-interleaved per channel (`scan_counts[row::mcd_num]`) and stored as `(cycle, scan, energy)` summed, plus `(cycle, scan, channel, energy)` raw.

**Special behaviour.**

- FAT mode: channels are only trimmed (`mcd_head`/`mcd_tail`) and summed; no per-channel shift or interpolation.
- Non-FAT modes: each channel starts at index `offset_id = round(offset/scan_delta)` (minus 1 if > 0), the first N points are taken, then summed.
- The common axis is the last channel's axis (offset 0). The axis is rounded to 8 decimals. Most metadata/unit mappings are commented out in `metadata.py`.

## Formula / transformation

**Step 1: top of the energy axis (l. 665-667)**

```
BE_upper = hν − KE + KE_base + 1
```

- `hν` is `excitation_energy`, `KE` is `kinetic_energy`, `KE_base` is `kinetic_energy_base`, all read from the XML region (l. 585-607, 659-664).
- `hν − KE` is the standard binding-energy relation. `+ KE_base` is an extra offset from the file. `+ 1` is hard-coded with no comment.
- The work function φ is not subtracted anywhere.
- This is the starting BE of the scan, which is its highest BE since the axis runs downward.

**Step 2: per-channel energy offset (l. 669-675)**

```
offset_c = (shift_last − shift_c) · E_pass
```

`mcd_shifts` holds one calibrated shift per MCD channel, apparently as a fraction of the pass energy. Multiplying by `E_pass` gives eV. Each channel is measured relative to the last one, so `offset_last = 0`.

**Step 3: per-channel axis (l. 682-691)**

```
start_c = BE_upper − offset_c
end_c   = start_c − N·scan_delta          (N = values_per_scan)
axis_c  = linspace(start_c, end_c, N)     rounded to 8 decimals
```

The axis descends from `start_c`. `linspace` includes its endpoint, so spanning N points up to `start − N·Δ` gives an actual step of `N·Δ/(N−1)`, slightly larger than `scan_delta`. The span probably should be `(N−1)·Δ`.

**Step 4: the axis that is stored (l. 692)**

```
BE = axis_last = linspace(BE_upper, BE_upper − N·scan_delta, N)
```

Because `offset_last = 0`, the stored axis is the last channel's axis, which equals the unshifted axis. The other channels' axes are computed but never stored. It is written as `coords={"energy": binding_energy}` (l. 743-749).

**Step 5: channel sum (l. 728, 735, 737)**

```
counts_sum[i] = Σ_c counts_c[i]
```

Row 0 of `channel_counts` accumulates every channel and is saved into `data_arr` (l. 737). This is a sum, not an average. Per-channel counts are kept in `raw_arr` (l. 739).

**Worked example for the offsets (my own numbers, not from a file)**

- `E_pass = 20`, `shifts = [0.0, 0.03, 0.05]` (last channel is the reference), `scan_delta = 0.1`.
- Offsets: `(0.05 − 0.0)·20 = 1.0`, `(0.05 − 0.03)·20 = 0.4`, `0.0` eV.
- Start indices `round(offset/Δ) = [10, 4, 0]`; minus 1 when greater than 0 gives `[9, 3, 0]`. This shows the effect of the `− 1`.

## Special behaviour

1. **De-interleaving channels (l. 722, 732).** `scan_counts` is one flat array in which the channels alternate. The slice `scan_counts[row::mcd_num]` picks every `mcd_num`-th sample starting at `row`, which isolates one channel.
2. **FAT mode: trim only (l. 720-728).** Each channel is cut with `[mcd_head : −mcd_tail]` (or `[mcd_head:]` if the tail is 0) and then added to the sum. No `mcd_shifts` offset and no interpolation is applied to the data. The head/tail trim may be how this mode aligns channels, but the inspected code does not show that. This differs from the SLE parser, which shifts each channel and interpolates onto a common grid.
3. **Non-FAT modes: index-shift alignment (l. 676-677, 729-735).** For each channel `offset_id = round(offset_c / scan_delta)`, and the code subtracts 1 when `offset_id > 0` (l. 677). The channel is read from `scan_counts[offset_id::mcd_num]` and cut to the first N values. No interpolation; the offset is rounded to the nearest point.
4. **Cycle/scan structure (l. 700-711).** Scan names are matched with `cycle(\d+)_scan(\d+)`. `n_cycles = max cycle + 1` and `n_scans = max scan + 1`. Output shapes are `(n_cycles, n_scans, N)` summed and `(n_cycles, n_scans, mcd_num, N)` per channel. Regions with no scans, or whose first scan is all zeros, are skipped with `continue` (l. 695-698).
5. **Scan mode default (l. 660).** `scan_mode` defaults to `'fixed_analyzer_transmission'` when absent.
6. **Metadata (`metadata.py` l. 27-53).** The mappings for `work_function`, `excitation_energy`, `start_energy` and the eV units are commented out. The values come from hard-coded key matching in `parser.py` (l. 585-607).

## Behaviour to investigate

Each point says what the code does, why it may matter and how to check it.

1. **Hard-coded `+ 1` in the binding-energy axis (l. 665-667).** If it is not a real physical offset, every energy value is shifted (probably by 1 eV).
2. **Work function is not applied (`metadata.py` l. 40).** The mapping `eff._workfunction` → `work_function` is commented out. Look in the XML for a work-function field and check whether `KE_base` already includes it.
3. **Energy step might be slightly shifted (l. 683-691).** With N = 101 and `scan_delta = 0.1`, the real step is 0.101 and the axis is 10.1 eV long instead of 10.0 eV (my own numbers). The error grows with distance from the start. Compare `np.diff(binding_energy)` with `scan_delta`; the span should probably be `(N−1)·scan_delta`.
4. **Channels not aligned in FAT mode (l. 720-728).** If channels are offset in energy, the summed peak is broadened or shifted. Plot the individual channels (`raw_arr`) for a sharp peak and see whether they line up.
5. **Odd index offset in non-FAT modes (l. 676-677).** The `− 1` is applied only to non-zero offsets and is unexplained. Rounding to whole points can misalign a channel by up to half a step. Find out whether the `− 1` is intentional and compare alignment with and without it.
6. **Binding energy always assumed.** The axis is built from `hν − KE` and no handling of `energy/@type` was seen. A scan recorded in kinetic energy would be labelled as binding. Test one if available.
7. **Metadata and unit mappings commented out (`metadata.py` l. 27-53).** Units or metadata may be missing from the output, and a differently named key could be missed. Inspect the generated NeXus file. Where this parser sets units was not seen.

## Scanner findings

- **Medium:** `matches_file` swallows `Exception` (l. 69).
- **Low/info:** silent fallback `.get('scan_mode', 'fixed_analyzer_transmission')` (l. 660); `np.zeros` allocations (l. 686, 713, 714, 718); rounding to 8 decimals (l. 691); 3 NeXus path literals in code; 7 exact string comparisons; 2 hits for keys spelled differently.

## Not verified

- Items 4 and 6 come from grep and `sed` output only.
