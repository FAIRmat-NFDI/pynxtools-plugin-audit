# Reconstruction and measurement file wrapper (`ifes_apt_tc_data_modeling`) for `pynxtools-apm`

## Source files reviewed

- `pynxtools_apm/…/ifes_reconstruction.py` — `IfesReconstructionParser` and eleven `extract_data_from_*` functions (1011 lines). The exact folder was not stated.
- Imported: the `ifes_apt_tc_data_modeling` readers `ReadPosFileFormat`, `ReadEposFileFormat`, `ReadAptFileFormat`, `ReadAtoFileFormat`, `ReadCsvFileFormat`, `ReadPyccaptCalibrationFileFormat`, `ReadCamecaHfiveFileFormat`, `ReadOpsFileFormat`, `ReadStuttgartApytRawFileFormat`, `ReadStuttgartApytSpectrumAlignFileFormat`, `ReadStuttgartApytReconstructionFileFormat`; `pynxtools_apm` constants (`DEFAULT_COMPRESSION_LEVEL`, `FAST_COMPRESSION_FILTER`, `SEPARATOR`) and `VALID_FILE_NAME_SUFFIX_RECON`; `prioritized_axes_heuristic`.
- Project: [pynxtools-apm repository](https://github.com/FAIRmat-NFDI/pynxtools-apm).

**Line-number note:** References below refer to the file in the main branch on 15th October 2026. `recon l.` = `ifes_reconstruction.py`.

## At a glance

| | |
|---|---|
| **Input format** | Reconstructed / measured atom-probe datasets: `.apt`, `.epos`, `.pos`, `.ato`, `.csv`, `.h5` (pyccapt calibration), `.hdf5` (Cameca), `.ops`, `.raw` (Stuttgart), `_trimmed.txt`, `_xyz.txt` (recon l. 980–1009) |
| **Parser class** | `IfesReconstructionParser` (recon l. 947–1010) |
| **Reader** | One third-party reader per format; accessor methods return `pint` quantities or `None` |
| **Raw-data storage** | `self.meta = {file_format, file_path, entry_id}` (recon l. 956–960) |
| **Output from parser** | Template entries; each array is a dict `{"compress": ndarray, "filter": FAST_COMPRESSION_FILTER, "strength": DEFAULT_COMPRESSION_LEVEL, "chunks": …}` with a sibling `…/@units` string |
| **Target definition** | `NXapm` (reconstruction, hit finding, voltage and bowl, pulser, stage, detector) |
| **Project context** | Largest file in the audit; mostly repetitive per-format blocks. Complements `ifes_ranging.py` and the Oasis/ELN parsers. |

**Standard behaviour.** Each function creates a reader, reads a set of named quantities, writes the present ones into the template (float32 arrays by default), warns on `None`, and `del`s the array to free memory. `parse()` chooses the function from the file suffix (recon l. 970–1010).

**Comparison with `ifes_ranging.py`.** There is no shared writer; each format writes its own subset, so which quantities exist depends on the format (table below).

## Formula / transformation

### Parser: quantity map per format

| Template target (under `/ENTRY[entry<id>]/`) | pos | epos | apt | ato | csv | pyc | cameca | ops | raw |
|---|---|---|---|---|---|---|---|---|---|
| `atom_probeID[atom_probe]/reconstruction/reconstructed_positions` (N×3) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `…/mass_to_charge_conversion/mass_to_charge` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `measurement/eventID[event1]/instrument/pulser/standing_voltage` | | ✓ | ✓ | | | ✓ | | | ✓ |
| `…/pulser/pulse_voltage` | | ✓ | ✓ | | | ✓ | | | ✓ |
| `…/voltage_and_bowl/raw_tof` | | ✓ | | | | ✓ | | | ✓ |
| `…/voltage_and_bowl/calibrated_tof` | | | | | | ✓ | | | |
| `…/hit_finding/hit_positions` (N×2) | | ✓ | ✓ | | | ✓ | | | |
| `…/hit_finding/epos_ions_per_pulse`, `epos_number_of_pulses` (uint32) | | ✓ | | | | | | | |
| `…/pulser/pulse_frequency`, `reflectron/voltage`, `detection_rate`, `sourceID[source1]/power`, `stage/temperature_sensor`, `analysis_chamber/pressure_sensor` | | | ✓ | | | | | | |
| `start_time`, `measurement/DATA[voltage_curve]/` | | | | | | | | ✓ | |

Line ranges: pos recon l. 47–83; epos 86–219; apt 222–471; ato 474–513; csv 516–553; pyc 556–675; cameca 678–717; ops 720–801; Stuttgart raw 804–859.

### Parser: APT named quantities

**Location:** recon l. 240–467. `get_named_quantity` names: `Position`, `Mass`, `Voltage`, `Vap` or `Pulse Voltage` (first present), `freq`, `Vref`, `XDet_mm` + `YDet_mm`, `erate`, `laserpower`, `Temp`, `Pres`. Detector x and y are stacked into an N×2 float32 array if shapes and units agree (recon l. 347–371).

### Parser: PoSAP voltage curve

**Location:** `extract_data_from_ops_file()` (recon l. 720–801).

$$
V(i) = V_{\text{standing}}(i) + V_{\text{pulse}}(i)
$$

An NXdata `measurement/DATA[voltage_curve]/` with `@signal = voltage`, `@axes = axis_evaporation_id`, and the axis values taken from `next_hit_group_offset` (uint32). Requires all three voltage arrays, equal shapes and equal units; otherwise a warning and an early return (recon l. 736–755).

### Parser: Stuttgart mass spectrum

**Location:** `extract_data_from_stuttgart_apyt_mass_spectrum_file()` (recon l. 862–918). `get_complete_spectrum()` returns (m/z axis, counts); writes `ranging/mass_to_charge_distribution/{min_mass_to_charge, max_mass_to_charge, n_mass_to_charge}` and a `mass_spectrum` NXdata with a title naming the bin width `round(m_z[1] − m_z[0], 3)` (recon l. 888–890).

## Standard behaviour

1. **Suffix detection.** First suffix in `VALID_FILE_NAME_SUFFIX_RECON` that the lower-cased path ends with (recon l. 961–968).
2. **Prefix.** `/ENTRY[entry<id>]` (recon l. 978).
3. **Dispatch.** Eleven independent `if` statements (recon l. 980–1009); only one can be true.
4. **Each quantity.** Read → if not `None`: `template[trg] = {compress, filter, strength, chunks}` and `template[trg/@units] = f"{q.units}"`; else `logger.warning(...)`; then `del` (e.g. recon l. 52–66).
5. **Chunking.** `prioritized_axes_heuristic(array, (0, 1))` for matrices, `(0,)` for vectors.
6. **APT section log.** Section names and metadata are logged at `info` (recon l. 227–235).

## Special behaviour

1. **Everything is cast to float32** (positions, m/z, voltages, times); integer counters to uint32 (recon l. 191, 206, 782–796).
2. **Memory management.** Arrays are deleted explicitly after being copied into the template (recon l. 66, 82, …).
3. **Commented-out plots.** A default detection-rate plot is disabled because hundreds of millions of values overload H5Web (recon l. 386–414); a similar remark applies to `ops` (recon l. 729–735).
4. **Multiplicity data not yet added.** Comments at recon l. 217–218, 469, 511, 673.
5. **Cameca `.hdf5` means different things here and in `ifes_ranging.py`** (reconstruction vs ranging).

## Behaviour to investigate

1. **Mass-spectrum min/max.** `min_mass_to_charge` and `max_mass_to_charge` are both set to `np.float32(m_z[0].magnitude)`, the whole axis array, not a minimum and a maximum (recon l. 879–882). They should be scalar `min()` / `max()` (or first/last).
2. **Spectrum counts to uint32.** Counts are cast with `np.uint32` (recon l. 895); fractional or negative counts would be truncated or wrap.
3. **Uniform-bin assumption.** The bin width uses the first two m/z values only (recon l. 889, 916).
4. **Axis is not an evaporation ID.** In the `ops` plot the axis is `next_hit_group_offset` (recon l. 782–799, marked `TODO`).
5. **`ops` start time unparsed.** `ops_file.instrument["time_stamp"]` is written as is (recon l. 725–727), without ISO 8601 or time-zone handling.
6. **Pint unit strings.** `@units` come from pint formatting (e.g. recon l. 63); check that they match NXDL-accepted unit strings such as `nm` or `Da`.
7. **Precision.** Casting positions and times to float32 loses precision for sources stored as float64 (recon l. 56, 159).
8. **Misleading warning.** For `Vap` / `Pulse Voltage` a warning is logged for `Vap` even if `Pulse Voltage` is then found (recon l. 293–309). The `try/except NameError` around `del voltage` (recon l. 310–313) can never trigger because the loop always assigns it.
9. **Ambiguous suffixes.** `.csv` is always treated as a reconstruction table, `.h5` as pyccapt calibration, `.hdf5` as Cameca (recon l. 988–995); `.raw` and `.ops` likewise.
10. **Name clash across modules.** `extract_data_from_cameca_hfive_file` exists here with the signature `(file_path, prefix, template)` and in `ifes_ranging.py` with `(file_path, template, entry_id)` (recon l. 678; rng l. 320). A wrong import would mix up arguments silently.
11. **Repetition.** The block "read → cast → chunk → units → warn → del" appears about 45 times; the file itself suggests parameterising it (recon l. 237–238).
12. **`ifelse` chain.** Independent `if` instead of `elif` (recon l. 980–1009).
13. **Placeholder f-strings and long commented blocks** (recon l. 438, 386–414).
14. **Missing quantities only logged.** A format that returns `None` for positions yields a valid template without reconstruction, producing a validation error later instead of at the source (e.g. recon l. 65).
15. **`SEPARATOR` in log messages** (recon l. 232) only for `apt`.

## Scanner findings

No scanner run was performed for `pynxtools-apm`.
